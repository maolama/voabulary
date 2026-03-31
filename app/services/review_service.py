import random
from datetime import date
from ..models import SavedWord

class DojoEngine:
    # Our finalized roster of strict active modes
    MODES = [
        'cloze_hybrid',       # Multiple choice + typing
        'verb_conjugation',   # Grammar inflection typing
        'proofreader',        # Spot the typo
        'vowel_void',         # Type the missing vowels
        'typo_trap',          # Visual discrimination
        'audio_dictation',    # Hear and type (Progressive)
        'blindfolded'         # Type hidden
    ]

    @staticmethod
    def get_due_words():
        """Fetches all words due for review today or earlier."""
        today = date.today()
        # Order by oldest review date first, so forgotten words take priority
        return SavedWord.query.filter(SavedWord.next_review_date <= today).order_by(SavedWord.next_review_date).all()

    @staticmethod
    def assign_mode(word):
        """
        Mode Roulette: The core logic that decides the best practice mode 
        based on the word's stats and mastery level.
        """
        # 1. NEW WORDS: If it's brand new (interval 0), establish context or basic listening
        if word.interval == 0:
            return random.choice(['cloze_hybrid', 'audio_dictation'])
        
        # 2. THE VERB CHECK: If it's a verb, occasionally force the conjugation challenge
        if word.primary_pos == 'verb' and random.random() < 0.3:
            return 'verb_conjugation'
            
        # 3. WEAKNESS TARGETING: If you keep failing dictation/spelling, force basic audio/vowel practice
        if word.dictation_streak < 2 or word.spelling_streak < 2:
            return random.choice(['audio_dictation', 'vowel_void'])
            
        # 4. MASTERY CHECK: If you know it really well (interval > 14 days), deploy the hardest modes
        if word.interval > 14:
            return random.choice(['blindfolded', 'typo_trap'])

        # 5. STANDARD ROTATION: Pick any mode EXCEPT the one you played last time
        available = [m for m in DojoEngine.MODES if m != word.last_mode_played]
        
        # Failsafe just in case available is empty
        if not available: 
            return random.choice(DojoEngine.MODES)
            
        return random.choice(available)

    @staticmethod
    def generate_session(max_words=20):
        """
        Creates the daily queue. 
        Returns a list of dicts with the word_id and the assigned mode.
        """
        due_words = DojoEngine.get_due_words()
        
        # Take the top N due words, but shuffle them so the session is unpredictable
        session_queue = due_words[:max_words]
        random.shuffle(session_queue)
        
        queue_data = []
        for w in session_queue:
            mode = DojoEngine.assign_mode(w)
            queue_data.append({
                'word_id': w.id,
                'word_text': w.word,
                'mode': mode
            })
            
        return {
            'total_due': len(due_words),
            'session_queue': queue_data
        }