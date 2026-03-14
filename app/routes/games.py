import random
import re
from flask import Blueprint, render_template, request
from ..models import SavedWord
from ..extensions import db
from app import dict_service

bp = Blueprint('games', __name__)

@bp.route('/')
def games_hub():
    return render_template('games/hub.html')

# --- GAME 1: FLASHCARD SPRINT ---
@bp.route('/sprint')
def sprint_game():
    """Fetches a random unmastered word, avoiding immediate repeats."""
    exclude_id = request.args.get('exclude_id', type=int)
    
    query = SavedWord.query.filter(SavedWord.interval < 21)
    
    # If we just saw a word, exclude it from the next random draw
    if exclude_id:
        query = query.filter(SavedWord.id != exclude_id)
        
    word = query.order_by(db.func.random()).first()
    
    # Edge case: If you literally only have 1 unmastered word in your whole database, 
    # it will return None because we excluded it. Let's just return that 1 word.
    if not word and exclude_id:
        word = SavedWord.query.get(exclude_id)
        
    if not word: 
        return render_template('games/hub.html', error="No words left to practice!")
        
    return render_template('games/sprint.html', word=word)

@bp.route('/sprint/flip/<int:word_id>', methods=['POST'])
def sprint_flip(word_id):
    """HTMX endpoint to reveal the short definition."""
    word = SavedWord.query.get_or_404(word_id)
    hint = dict_service.get_short_definition(word.word)
    return render_template('games/partials/sprint_back.html', word=word, hint=hint)

# --- GAME 2: MISSING VOWELS ---
@bp.route('/missing_vowels')
def missing_vowels_game():
    # Only pick words longer than 4 letters
    words = SavedWord.query.all()
    valid_words = [w for w in words if len(w.word) > 4]
    
    if not valid_words: return render_template('games/hub.html', error="Not enough long words for this game.")
    
    word_obj = random.choice(valid_words)
    # Regex to replace vowels with underscores
    vowelless = re.sub(r'[aeiouAEIOU]', '_', word_obj.word)
    hint = dict_service.get_short_definition(word_obj.word)
    
    return render_template('games/missing_vowels.html', word=word_obj, vowelless=vowelless, hint=hint)

@bp.route('/missing_vowels/submit/<int:word_id>', methods=['POST'])
def submit_missing_vowels(word_id):
    word = SavedWord.query.get_or_404(word_id)
    user_input = request.form.get('typed_word', '').strip().lower()
    
    if user_input == word.word.lower():
        return "<div class='text-emerald-500 font-bold text-xl mb-4'>Correct!</div> <button hx-get='/games/missing_vowels' hx-target='body' class='bg-indigo-600 text-white py-2 px-6 rounded-lg'>Next Word</button>"
    return "<div class='text-rose-500 font-bold mb-4 animate-pulse'>Incorrect. Try again!</div>"

# --- GAME 3: AUDIO MATCH ---
@bp.route('/audio_match')
def audio_match_game():
    words = SavedWord.query.all()
    if len(words) < 4: return render_template('games/hub.html', error="Need at least 4 saved words to play.")
    
    # Try to find a word that actually has offline audio
    target_word = None
    audio_path = None
    random.shuffle(words)
    
    for w in words:
        path = dict_service.has_audio(w.word)
        if path:
            target_word = w
            audio_path = path
            break
            
    # Fallback to browser TTS if no offline audio is found in dictionaries
    use_tts = False
    if not target_word:
        target_word = random.choice(words)
        use_tts = True
        
    # Get 3 random distractors
    distractors = [w for w in words if w.id != target_word.id]
    options = random.sample(distractors, min(3, len(distractors)))
    options.append(target_word)
    random.shuffle(options)
    
    return render_template('games/audio_match.html', target=target_word, options=options, audio_path=audio_path, use_tts=use_tts)

@bp.route('/audio_match/submit/<int:selected_id>/<int:target_id>', methods=['POST'])
def submit_audio_match(selected_id, target_id):
    if selected_id == target_id:
        return "<div class='text-emerald-500 font-bold text-xl mt-4'>Correct!</div> <button hx-get='/games/audio_match' hx-target='body' class='mt-4 bg-indigo-600 text-white py-2 px-6 rounded-lg'>Next Word</button>"
    return "<div class='text-rose-500 font-bold mt-4 animate-pulse'>Wrong word! Listen closely.</div>"