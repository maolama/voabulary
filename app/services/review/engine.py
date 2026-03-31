import random
from datetime import date
from ...models import SavedWord
from .config import DojoConfig

class DojoEngine:
    """Handles the custom tiered queue generation for a review session."""

    # Map every mode to an intrinsic difficulty tier (1=Easy, 2=Medium, 3=Hard)
    MODE_DIFFICULTY = {
        # Level 1: Pure Recognition
        'word_to_def': 1, 'def_to_word': 1, 'audio_to_def': 1, 'true_false_sort': 1, 'collocation_match': 1,
        # Level 2: Recall & Spelling
        'vowel_void': 2, 'typo_trap': 2, 'cloze_hybrid': 2, 'audio_dictation': 2,
        # Level 3: Advanced Mastery
        'proofreader': 3, 'blindfolded': 3, 'verb_conjugation': 3
    }

    @staticmethod
    def get_due_words():
        today = date.today()
        return SavedWord.query.filter(SavedWord.next_review_date <= today).order_by(SavedWord.next_review_date).all()

    @staticmethod
    def build_playlist(word: SavedWord, config_data: dict) -> list:
        """Assigns a raw playlist of modes based on the word's Mastery Level and User Config."""
        level = getattr(word, 'mastery_level', 1) 
        
        if level <= 3: phase_key = "1"
        elif level <= 6: phase_key = "2"
        else: phase_key = "3"
            
        phase_config = config_data['phases'].get(phase_key, {})
        playlist = []
        
        for mode, count in phase_config.items():
            if mode == 'verb_conjugation' and getattr(word, 'primary_pos', '') != 'verb':
                continue
            for _ in range(count):
                playlist.append(mode)
                
        if not playlist:
            playlist = ['word_to_def'] # Failsafe
            
        return playlist

    @staticmethod
    def generate_session(max_words: int) -> dict:
        """Builds the session by intelligently interleaving progressive word queues."""
        config_data = DojoConfig.get_config()
        due_words = DojoEngine.get_due_words()
        session_words = due_words[:max_words]
        
        # 1. Build and sort individual queues for each word
        word_queues = {}
        for w in session_words:
            raw_playlist = DojoEngine.build_playlist(w, config_data)
            
            # Shuffle first: This ensures randomness WITHIN the same difficulty tier
            random.shuffle(raw_playlist)
            # Sort second: Python's stable sort ensures Easy -> Medium -> Hard order is strictly enforced
            raw_playlist.sort(key=lambda m: DojoEngine.MODE_DIFFICULTY.get(m, 2))
            
            detailed_playlist = []
            for i, mode in enumerate(raw_playlist):
                detailed_playlist.append({
                    'word_id': w.id,
                    'word_text': w.word,
                    'mode': mode,
                    'encounter_index': i,
                    'is_last_encounter': (i == len(raw_playlist) - 1) 
                })
            
            word_queues[w.id] = detailed_playlist

        # 2. Interleave the queues into the final session sequence
        final_queue = []
        active_word_ids = list(word_queues.keys())
        last_word_id = None
        
        while active_word_ids:
            # Try to pick a word that is DIFFERENT from the one we just appended
            candidates = [wid for wid in active_word_ids if wid != last_word_id]
            
            # If we are down to the very last word, we are forced to pick it
            if not candidates:
                candidates = active_word_ids
                
            chosen_id = random.choice(candidates)
            
            # Pop the first available practice (which is guaranteed to be the easiest remaining one for this word)
            next_practice = word_queues[chosen_id].pop(0)
            final_queue.append(next_practice)
            
            last_word_id = chosen_id
            
            # If this word's queue is empty, remove it from the active pool
            if not word_queues[chosen_id]:
                active_word_ids.remove(chosen_id)
                
        return {
            'total_due': len(due_words),
            'session_queue': final_queue 
        }