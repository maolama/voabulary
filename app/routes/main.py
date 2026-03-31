import os
import sqlite3
import urllib.parse
import subprocess # <-- Add this at the top
from datetime import datetime
from flask import Blueprint, render_template, Response, request
from sqlalchemy import func
from ..models import SavedWord
from ..services.gamification import GamificationService
from ..extensions import db
from app import dict_service
import random


# Define the Blueprint FIRST
bp = Blueprint('main', __name__)

# --- CORE PAGES ---

@bp.route('/')
def dashboard():
    today = datetime.utcnow().date()
    
    # Analytics Queries
    total_words = SavedWord.query.count()
    due_today = SavedWord.query.filter(SavedWord.next_review_date == today).count()
    overdue = SavedWord.query.filter(SavedWord.next_review_date < today).count()
    mastered = SavedWord.query.filter(SavedWord.interval >= 21).count()
    profile = GamificationService.get_or_create_profile()
    heatmap = GamificationService.get_heatmap_data()
    # Fetch words actively due right now
    due_words = SavedWord.query.filter(SavedWord.next_review_date <= today).order_by(SavedWord.next_review_date).all()
    
    return render_template('dashboard.html', 
                           total_words=total_words, 
                           due_today=due_today, 
                           overdue=overdue,
                           mastered=mastered,
                           due_words=due_words,
                           profile=profile,
                           heatmap=heatmap)

@bp.route('/search')
def search_page():
    return render_template('search.html')

@bp.route('/review')
def review_page():
    today = datetime.utcnow().date()
    # Get the most overdue word first
    next_word = SavedWord.query.filter(SavedWord.next_review_date <= today).order_by(SavedWord.next_review_date).first()
    return render_template('review.html', word=next_word)


@bp.route('/entry/<dict_name>/<query>')
def dictionary_entry(dict_name, query):
    handler = dict_service.active_dictionaries.get(dict_name)
    if not handler:
        print(f"❌ [ERROR] Dictionary handler not found for: {dict_name}")
        return "Dictionary not found", 404

    query = urllib.parse.unquote(query)
    
    raw_word_id = request.args.get('word_id')
    print(f"🔍 [DEBUG] entry.html loading: dict={dict_name}, query={query}, raw_word_id={raw_word_id}")

    word_id = None
    pinned_ids = []

    if raw_word_id and raw_word_id != 'None' and raw_word_id != '':
        try:
            word_id = int(raw_word_id)
            from ..models import SavedSense
            senses = SavedSense.query.filter_by(word_id=word_id, dict_name=dict_name).all()
            pinned_ids = [s.sense_id for s in senses if s.sense_id]
        except ValueError:
            pass

    # FIXED: We now pass pinned_ids down to the dictionary service
    html_content = dict_service.get_full_html(dict_name, query, word_id=word_id, pinned_ids=pinned_ids)
    
    return render_template('entry.html', 
                           html_content=html_content, 
                           dict_name=dict_name, 
                           pinned_ids=pinned_ids, 
                           has_css=dict_name in dict_service.css_paths,
                           color=handler.color)

@bp.route('/entry/<dict_name>/<filename>.css')
@bp.route('/css/<dict_name>') 
def serve_css(dict_name, filename=None):
    if dict_name in dict_service.css_paths:
        css_path = dict_service.css_paths[dict_name]
        if os.path.exists(css_path):
            with open(css_path, 'rb') as f:
                return Response(f.read(), mimetype='text/css')
    return "CSS Not Found", 404

@bp.route('/<path:filename>')
def serve_media(filename):
    # 1. CHECK PHYSICAL FILES FIRST (For JS scripts)
    if filename.endswith('.js'):
        for dict_name, js_path in dict_service.js_paths.items():
            if os.path.basename(js_path).lower() == filename.lower():
                if os.path.exists(js_path):
                    with open(js_path, 'rb') as f:
                        return Response(f.read(), mimetype='application/javascript')

    # 2. THE DETECTIVE: Determine which dictionary made the request
    target_dict = None
    if request.referrer and '/entry/' in request.referrer:
        try:
            url_path = request.referrer.split('/entry/')[1]
            target_dict = urllib.parse.unquote(url_path.split('/')[0])
        except Exception:
            pass

    # 3. SETUP SMART SEARCH PATTERNS
    basename = os.path.basename(filename).lower()
    name_only, ext = os.path.splitext(basename)

    search_patterns = [
        f"/{filename}".lower(),
        f"%/{basename}"
    ]
    if ext == '.mp3':
        search_patterns.extend([f"%/{name_only}.spx", f"%/{name_only}.wav"])

    # 4. THE HYBRID QUEUE: Put target dictionary FIRST, then fallback to others
    dicts_to_search = []
    
    # Prioritize the dictionary that actually asked for the file
    if target_dict and target_dict in dict_service.active_dictionaries:
        dicts_to_search.append((target_dict, dict_service.active_dictionaries[target_dict]))
        
    # Append the rest of the dictionaries to act as a safety net
    for d_name, d_handler in dict_service.active_dictionaries.items():
        if d_name != target_dict:
            dicts_to_search.append((d_name, d_handler))

    # 5. EXECUTE THE SEARCH
    for dict_name, handler in dicts_to_search:
        try:
            conn = sqlite3.connect(handler.db_path)
            c = conn.cursor()
            
            row = None
            for pattern in search_patterns:
                c.execute("SELECT filepath, data FROM media WHERE filepath LIKE ? LIMIT 1", (pattern,))
                row = c.fetchone()
                if row: break # Found it! Stop searching this database.
                
            conn.close()
            
            if row:
                db_filepath, data = row
                db_ext = os.path.splitext(db_filepath)[1].lower()
                
                # --- SPX TRANSCODING INTERCEPTOR ---
                if db_ext == '.spx':
                    mp3_data = transcode_spx_to_mp3(data)
                    if mp3_data:
                        return Response(mp3_data, mimetype='audio/mpeg')
                    else:
                        return "Audio transcoding failed", 500

                # --- STANDARD MIME TYPES ---
                mime_type = 'application/octet-stream'
                if db_ext in ['.png']: mime_type = 'image/png'
                elif db_ext in ['.jpg', '.jpeg']: mime_type = 'image/jpeg'
                elif db_ext in ['.gif']: mime_type = 'image/gif'
                elif db_ext in ['.mp3']: mime_type = 'audio/mpeg'
                elif db_ext in ['.wav']: mime_type = 'audio/wav'
                elif db_ext in ['.css']: mime_type = 'text/css'
                
                return Response(data, mimetype=mime_type)
                
        except Exception as e:
            print(f"Database error in {dict_name}: {e}")
            
    return "File not found", 404

@bp.route('/words')
def words_list():
    """Displays the list of all saved words and their SRS statistics."""
    # Order by next review date, then by id
    words = SavedWord.query.order_by(SavedWord.next_review_date.asc(), SavedWord.id.desc()).all()
    return render_template('words.html', words=words)

@bp.route('/word/<int:word_id>')
def word_detail(word_id):
    """Deep dive into a specific word's stats and dictionary entries."""
    word_obj = SavedWord.query.get_or_404(word_id)
    # Fetch dictionary entries
    results = dict_service.search_word(word_obj.word)
    return render_template('word_detail.html', word=word_obj, results=results)

@bp.route('/practice/scramble')
def practice_scramble():
    """A mini-game that scrambles a random saved word."""
    words = SavedWord.query.all()
    if not words:
        return render_template('practice_scramble.html', word=None)
    
    target = random.choice(words)
    word_str = target.word
    chars = list(word_str)
    random.shuffle(chars)
    
    # Ensure it is actually scrambled
    while "".join(chars) == word_str and len(word_str) > 1:
        random.shuffle(chars)
        
    scrambled = "".join(chars)
    return render_template('practice_scramble.html', word=target, scrambled=scrambled)

@bp.route('/settings')
def settings_page():
    """Settings page for TTS Voice selection."""
    return render_template('settings.html')

@bp.route('/aggregate/<query>')
def aggregate_view(query):
    # Fetch the pivoted semantic feature data
    aggregated_data = dict_service.get_aggregated_features(query)
    
    # FIXED: Check for 'pos_blocks' instead of the old 'definitions' key
    if not aggregated_data or not aggregated_data.get('pos_blocks'):
        # Fallback if the word isn't found or data extraction failed
        return render_template('aggregate.html', data=None, query=query)
        
    return render_template('aggregate.html', data=aggregated_data)




# --- HELPER FUNCTION ---
def transcode_spx_to_mp3(spx_data):
    """Converts SPX binary data to MP3 binary data in memory using FFmpeg."""
    try:
        # We pipe the binary data in, and ffmpeg pipes MP3 binary data out
        process = subprocess.Popen(
            ['ffmpeg', '-i', 'pipe:0', '-f', 'mp3', 'pipe:1'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        mp3_data, err = process.communicate(input=spx_data)
        
        if process.returncode != 0:
            print(f"FFmpeg error: {err.decode('utf-8')}")
            return None
            
        return mp3_data
    except FileNotFoundError:
        print("ERROR: ffmpeg.exe was not found! Please put it in the project folder.")
        return None
    
@bp.route('/dojo')
def active_dojo():
    """Renders the Active Learning Dojo interface."""
    return render_template('review/dojo.html')