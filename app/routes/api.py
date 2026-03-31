import os
import hashlib
from flask import send_file, current_app
from ..services.tts import tts_manager
from flask import Blueprint, request, render_template, jsonify, make_response
from ..models import SavedWord, SavedSense
from ..extensions import db, logger
from app import dict_service # Import the global instance
from ..models import ManualSynonym, ManualAntonym

bp = Blueprint('api', __name__)

@bp.route('/search', methods=['POST'])
def htmx_search():
    query = request.form.get('query', '').strip()
    if not query: return ""
    print(f"DEBUG [api/search]: Searching for word: '{query}'") # LOG
    
    # 1. Search dictionary databases
    results = dict_service.search_word(query)
    
    # 2. Look for the word in your SavedWord table
    # We use .lower() to ensure match consistency
    saved_word = SavedWord.query.filter_by(word=query.lower()).first()
    
    # 3. Explicitly extract the ID
    word_id = saved_word.id if saved_word else None
    print(f"DEBUG [api/search]: Saved status: {saved_word is not None}, Word ID: {word_id}") # LOG
    
    # DEBUG: print(f"Search for {query}: word_id is {word_id}") # Check your console!

    return render_template('components/word_card.html', 
                           query=query, 
                           results=results, 
                           is_saved=(saved_word is not None),
                           word_id=word_id) # <-- This MUST be passed

@bp.route('/save_word', methods=['POST'])
def save_word():
    word_text = request.form.get('word', '').strip().lower()
    if not word_text:
        return "No word provided", 400

    try:
        new_word = SavedWord.query.filter_by(word=word_text).first()
        if not new_word:
            new_word = SavedWord(word=word_text)
            db.session.add(new_word)
            db.session.commit()
            
        # We import dict_service locally here to avoid circular import issues
        from app import dict_service 
        
        # Fetch the dictionaries that have this word
        results = dict_service.search_word(word_text)
        
        # Render and return the exact same card, but now with the DB ID attached!
        # Note: If your word_card.html is in a subfolder like 'components/', 
        # change this to 'components/word_card.html'
        return render_template('components/word_card.html', 
                               query=word_text, 
                               results=results, 
                               is_saved=True,
                               word_id=new_word.id)
                               
    except Exception as e:
        db.session.rollback()
        print(f"Error saving word: {e}")
        return str(e), 500

from flask import make_response # Make sure this is imported at the top!

@bp.route('/suggest', methods=['POST'])
def suggest_words():
    """Returns an HTML dropdown of autocomplete suggestions."""
    prefix = request.form.get('query', '').strip()
    
    # Don't waste resources suggesting words if they only typed 1 letter
    if len(prefix) < 2:
        return "" 
        
    suggestions = dict_service.get_suggestions(prefix, limit=8)
    return render_template('components/suggestions.html', suggestions=suggestions)

# ==========================================
# DEVELOPMENT TOGGLE: Set to True for production, False for testing
# ==========================================
ENABLE_TTS_CACHE = False

@bp.route('/tts/voices', methods=['GET'])
def get_backend_voices():
    """Returns all available Python server voices."""
    return jsonify(tts_manager.get_all_voices())

@bp.route('/tts/generate', methods=['GET'])
def generate_tts():
    text = request.args.get('text', '').strip()
    provider_id = request.args.get('provider')
    voice_id = request.args.get('voice_id')

    if not text or not provider_id or not voice_id:
        return "Missing parameters", 400

    filename_hash = hashlib.md5(f"{text}_{provider_id}_{voice_id}".encode()).hexdigest()
    output_filename = f"{filename_hash}.wav"
    
    cache_dir = os.path.join(current_app.root_path, 'static', 'audio_cache')
    os.makedirs(cache_dir, exist_ok=True)
    output_path = os.path.join(cache_dir, output_filename)

    # 1. Check if we have a valid file
    file_exists_and_valid = os.path.exists(output_path) and os.path.getsize(output_path) > 0

    # 2. Logic: If cache is disabled OR file doesn't exist/is corrupted, FORCE GENERATE
    if not ENABLE_TTS_CACHE or not file_exists_and_valid:
        # This will overwrite the file if it exists
        success = tts_manager.generate(text, provider_id, voice_id, output_path)
        if not success:
            return "TTS Generation Failed", 500

    # 3. Serve the file safely
    response = make_response(send_file(output_path, mimetype='audio/wav'))
    
    # 4. If testing, force the browser to NOT cache the audio secretly
    if not ENABLE_TTS_CACHE:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'

    return response

@bp.route('/save_sense', methods=['POST'])
def save_sense():
    data = request.get_json()
    word_id = data.get('word_id')
    dict_name = data.get('dict_name')
    html_content = data.get('html_content')
    sense_id = data.get('sense_id')

    if not word_id or not html_content:
        return jsonify({'status': 'error', 'message': 'Missing word_id or content'}), 400

    try:
        word = SavedWord.query.get(word_id)
        if not word:
            return jsonify({'status': 'error', 'message': 'Save this word first!'}), 404

        # FIX: Check if it's already pinned
        existing_sense = SavedSense.query.filter_by(word_id=word_id, dict_name=dict_name, sense_id=sense_id).first()
        
        if existing_sense:
            # UNPIN logic
            db.session.delete(existing_sense)
            db.session.commit()
            return jsonify({'status': 'success', 'action': 'unpinned'})
        else:
            # PIN logic
            new_sense = SavedSense(
                word_id=word_id,
                dict_name=dict_name,
                sense_id=sense_id,
                html_content=html_content
            )
            db.session.add(new_sense)
            db.session.commit()
            return jsonify({'status': 'success', 'action': 'pinned'})
            
    except Exception as e:
        db.session.rollback()
        print(f"DEBUG [api/save_sense]: ERROR: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@bp.route('/dictionaries/config', methods=['GET'])
def get_dict_config():
    """Fetches the current dictionary display order, colors, and enabled status."""
    from app import dict_service
    return jsonify(dict_service.get_config())

@bp.route('/dictionaries/config', methods=['POST'])
def update_dict_config():
    """Saves the updated dictionary preferences."""
    from app import dict_service
    data = request.json
    try:
        dict_service.update_config(data)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    

@bp.route('/word/<int:word_id>/relations', methods=['GET'])
def get_relations(word_id):
    word_obj = SavedWord.query.get_or_404(word_id)
    
    # 1. Get Auto-Extracted
    auto_rels = dict_service.get_word_relations(word_obj.word)
    
    # 2. Get Manual DB
    manual_syns = [{"id": s.id, "word": s.synonym} for s in word_obj.manual_synonyms]
    manual_ants = [{"id": a.id, "word": a.antonym} for a in word_obj.manual_antonyms]
    
    return jsonify({
        "status": "success",
        "data": {
            "auto_synonyms": auto_rels['synonyms'],
            "auto_antonyms": auto_rels['antonyms'],
            "manual_synonyms": manual_syns,
            "manual_antonyms": manual_ants
        }
    })

@bp.route('/word/<int:word_id>/relations', methods=['POST'])
def add_relation(word_id):
    data = request.json
    rel_type = data.get('type') # 'synonym' or 'antonym'
    word_val = data.get('word', '').strip().lower()
    
    if not word_val: return jsonify({"status": "error"}), 400
    
    try:
        if rel_type == 'synonym':
            new_rel = ManualSynonym(word_id=word_id, synonym=word_val)
        else:
            new_rel = ManualAntonym(word_id=word_id, antonym=word_val)
            
        db.session.add(new_rel)
        db.session.commit()
        return jsonify({"status": "success", "id": new_rel.id, "word": word_val})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/word/relations/<int:rel_id>', methods=['DELETE'])
def delete_relation(rel_id):
    rel_type = request.args.get('type')
    try:
        obj = ManualSynonym.query.get(rel_id) if rel_type == 'synonym' else ManualAntonym.query.get(rel_id)
        if obj:
            db.session.delete(obj)
            db.session.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500