from datetime import datetime, timedelta
from ...models import SavedWord
from ...extensions import db
from ..gamification import GamificationService

class DojoGrader:
    """Handles grading, mastery leveling, and spaced repetition scheduling."""

    @staticmethod
    def grade_answer(word_obj: SavedWord, is_correct: bool, mode: str, typing_time_ms: int = None, is_last_encounter: bool = True) -> dict:
        now = datetime.utcnow()
        today = now.date()
        
        # Did we already push this word to the future today? (e.g., from a failure earlier in the session)
        already_processed_today = word_obj.next_review_date > today
            
        word_obj.last_reviewed_at = now
        word_obj.last_mode_played = mode
        
        current_mastery = getattr(word_obj, 'mastery_level', 1)

        # --- FLUIDITY TRACKING (Updates on every encounter) ---
        if typing_time_ms and is_correct:
            current_avg = word_obj.avg_typing_fluidity or typing_time_ms
            word_obj.avg_typing_fluidity = (current_avg * 0.7) + (typing_time_ms * 0.3)
        
        slow_typing_penalty = (typing_time_ms and typing_time_ms > 5000)

        if is_correct:
            word_obj.total_reviews += 1
            
            # --- MICRO STATS: Update every encounter ---
            if mode in ['audio_dictation', 'blindfolded']:
                word_obj.dictation_streak += 1
            else:
                word_obj.spelling_streak += 1
                
            GamificationService.log_activity('review_passed')

            # --- MACRO STATS: Only update when the entire daily playlist is complete! ---
            if is_last_encounter and not already_processed_today:
                word_obj.mastery_level = min(9, current_mastery + 1)
                
                grade = 3 if slow_typing_penalty else 5
                
                if word_obj.repetitions == 0:
                    word_obj.interval = 1
                elif word_obj.repetitions == 1:
                    word_obj.interval = 6
                else:
                    growth_modifier = 0.8 if slow_typing_penalty else 1.0
                    word_obj.interval = round(word_obj.interval * word_obj.ease_factor * growth_modifier)
                
                word_obj.repetitions += 1
                word_obj.ease_factor = max(1.3, word_obj.ease_factor + (0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02)))
                
                # Push the date to the future!
                word_obj.next_review_date = (now + timedelta(days=word_obj.interval)).date()

        else:
            # FAILURE: Punish immediately, but ONLY if we haven't already punished it today.
            # (This prevents a word's ease_factor from tanking 3 times in one session)
            if not already_processed_today:
                word_obj.mastery_level = max(1, current_mastery - 1)
                word_obj.lapses += 1
                word_obj.repetitions = 0
                word_obj.interval = 1
                word_obj.ease_factor = max(1.3, word_obj.ease_factor - 0.15)
                
                # Push to tomorrow so it leaves today's queue
                word_obj.next_review_date = (now + timedelta(days=1)).date()
            
            # Streaks break on every failure
            if mode in ['audio_dictation', 'blindfolded']:
                word_obj.dictation_streak = 0
            else:
                word_obj.spelling_streak = 0
        
        db.session.commit()
        
        return {
            'word_id': word_obj.id,
            'is_correct': is_correct,
            'new_interval': word_obj.interval,
            'new_mastery_level': word_obj.mastery_level,
            'slow_penalty_applied': slow_typing_penalty
        }