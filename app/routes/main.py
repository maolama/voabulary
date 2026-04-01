import os
import sqlite3
import urllib.parse
import subprocess # <-- Add this at the top
from datetime import date, timedelta, datetime
from flask import Blueprint, render_template, Response, request
from sqlalchemy import func
from ..models import SavedWord
from ..services.gamification import GamificationService
from ..services.review.engine import DojoEngine # NEW: Added for Watering Can capacity calculation
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
    
    # NEW: Calculate the watering can capacity for the Garden HUD
    remaining_capacity = DojoEngine.get_remaining_daily_capacity()
    
    return render_template('dashboard.html', 
                           total_words=total_words, 
                           due_today=due_today, 
                           overdue=overdue,
                           mastered=mastered,
                           due_words=due_words,
                           profile=profile,
                           heatmap=heatmap,
                           remaining_capacity=remaining_capacity) # NEW: Passed to template

@bp.route('/search')
def search_page():
    return render_template('search.html')

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
    
    if target_dict and target_dict in dict_service.active_dictionaries:
        dicts_to_search.append((target_dict, dict_service.active_dictionaries[target_dict]))
        
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
                if row: break
                
            conn.close()
            
            if row:
                db_filepath, data = row
                db_ext = os.path.splitext(db_filepath)[1].lower()
                
                if db_ext == '.spx':
                    mp3_data = transcode_spx_to_mp3(data)
                    if mp3_data:
                        return Response(mp3_data, mimetype='audio/mpeg')
                    else:
                        return "Audio transcoding failed", 500

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
    words = SavedWord.query.order_by(SavedWord.next_review_date.asc(), SavedWord.id.desc()).all()
    return render_template('words.html', words=words)

@bp.route('/word/<int:word_id>')
def word_detail(word_id):
    """Deep dive into a specific word's stats and dictionary entries."""
    word_obj = SavedWord.query.get_or_404(word_id)
    results = dict_service.search_word(word_obj.word)
    return render_template('word_detail.html', word=word_obj, results=results)

@bp.route('/settings')
def settings_page():
    """Settings page for TTS Voice selection and Garden Control."""
    from ..services.gamification import GamificationService
    profile = GamificationService.get_or_create_profile()
    return render_template('settings.html', profile=profile)

@bp.route('/aggregate/<query>')
def aggregate_view(query):
    aggregated_data = dict_service.get_aggregated_features(query)
    
    if not aggregated_data or not aggregated_data.get('pos_blocks'):
        return render_template('aggregate.html', data=None, query=query)
        
    return render_template('aggregate.html', data=aggregated_data)


# ==========================================
# NEW: THE GARDEN PLANNER ROUTE
# ==========================================
@bp.route('/planner')
def garden_planner():
    """Serves the 11-Day Kanban Garden Planner."""
    from datetime import date, timedelta, datetime
    from ..models import UserProfile, SavedWord
    
    target_date_str = request.args.get('date')
    if target_date_str:
        try:
            target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
        except ValueError:
            target_date = date.today()
    else:
        target_date = date.today()

    # 1. Base the core week from Saturday
    days_since_saturday = (target_date.weekday() + 2) % 7
    start_of_core_week = target_date - timedelta(days=days_since_saturday)
    
    # 2. The 11-Day Window: 2 days before, 8 days after (total 11)
    start_of_view = start_of_core_week - timedelta(days=2) # Thursday
    end_of_view = start_of_core_week + timedelta(days=8)   # Sunday
    
    view_dates = [start_of_view + timedelta(days=i) for i in range(11)]

    # 3. Fetch words in this 11-day range
    words_in_range = SavedWord.query.filter(
        SavedWord.next_review_date >= start_of_view,
        SavedWord.next_review_date <= end_of_view
    ).all()

    words_by_date = {d.strftime('%Y-%m-%d'): [] for d in view_dates}
    for w in words_in_range:
        words_by_date[w.next_review_date.strftime('%Y-%m-%d')].append(w)

    # 4. Overdue safety net (Catch forgotten words and put them on 'Today')
    today = date.today()
    if start_of_view <= today <= end_of_view:
        overdue_words = SavedWord.query.filter(SavedWord.next_review_date < start_of_view).all()
        words_by_date[today.strftime('%Y-%m-%d')].extend(overdue_words)

    # 5. Build the view data
    calendar_data = []
    for d in view_dates:
        day_words = words_by_date[d.strftime('%Y-%m-%d')]
        day_words.sort(key=lambda w: w.mastery_level)
        
        # Identify if this day is part of the "core" week or the edges
        is_core_week = start_of_core_week <= d < (start_of_core_week + timedelta(days=7))
        
        calendar_data.append({
            'date_str': d.strftime('%Y-%m-%d'),
            'day_name': d.strftime('%A')[:3], # Short name: 'Thu', 'Fri', 'Sat'
            'day_num': d.strftime('%d'),
            'is_today': d == today,
            'is_past': d < today,
            'is_core': is_core_week,
            'words': day_words,
            'count': len(day_words)
        })

    prev_week = start_of_core_week - timedelta(days=7)
    next_week = start_of_core_week + timedelta(days=7)
    
    profile = UserProfile.query.first()
    daily_limit = profile.daily_review_limit if profile and profile.daily_review_limit else 50

    return render_template('planner.html',
                           calendar_data=calendar_data,
                           current_month_name=start_of_core_week.strftime('%B %Y'),
                           prev_week_str=prev_week.strftime('%Y-%m-%d'),
                           next_week_str=next_week.strftime('%Y-%m-%d'),
                           daily_limit=daily_limit)

# --- HELPER FUNCTION ---
def transcode_spx_to_mp3(spx_data):
    """Converts SPX binary data to MP3 binary data in memory using FFmpeg."""
    try:
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