import math
from datetime import datetime, timedelta
from ...models import SavedWord
from ...extensions import db
from ..gamification import GamificationService

class DojoGrader:
    """Handles grading, mastery leveling, and strict FSRS spaced repetition scheduling."""

    # FSRS v4 Default Weights (Optimized for vocabulary acquisition)
    W = [0.4, 0.6, 2.4, 5.8, 4.93, 0.94, 0.86, 0.01, 1.49, 0.14, 0.94, 2.18, 0.05, 0.34, 1.26, 0.29, 2.61]

    @staticmethod
    def calculate_fsrs(stability, difficulty, grade, days_elapsed):
        """Pure FSRS Algorithm: Calculates next Interval, Stability, and Difficulty."""
        # FSRS Grade mapping: 1=Again(Fail), 2=Hard, 3=Good, 4=Easy
        
        # 1. First time seeing the word
        if stability <= 0: 
            next_d = max(1.0, min(10.0, DojoGrader.W[4] - DojoGrader.W[5] * (grade - 3)))
            next_s = max(0.1, DojoGrader.W[grade - 1])
            return max(1, round(next_s)), next_s, next_d

        # 2. Retrievability (The probability you remember it right now based on decay)
        retrievability = math.pow(1 + days_elapsed / (9 * stability), -1)

        # 3. Update Difficulty
        next_d = difficulty - DojoGrader.W[6] * (grade - 3)
        next_d = DojoGrader.W[7] * DojoGrader.W[4] + (1 - DojoGrader.W[7]) * next_d
        next_d = max(1.0, min(10.0, next_d))

        # 4. Update Stability (How much stronger the memory gets)
        if grade == 1: # Lapse (Failed)
            next_s = DojoGrader.W[11] * math.pow(next_d, -DojoGrader.W[12]) * math.pow(stability + 1, DojoGrader.W[13]) * math.exp((1 - retrievability) * DojoGrader.W[14])
            next_s = max(0.1, min(stability, next_s)) # Stability drops, but never below 0.1
        else: # Success
            hard_pen = DojoGrader.W[15] if grade == 2 else 1
            easy_bon = DojoGrader.W[16] if grade == 4 else 1
            growth = math.exp(DojoGrader.W[8]) * (11 - next_d) * math.pow(stability, -DojoGrader.W[9]) * (math.exp((1 - retrievability) * DojoGrader.W[10]) - 1)
            next_s = stability * (1 + growth * hard_pen * easy_bon)

        # Target interval is mapped directly to the new stability
        next_interval = max(1, round(next_s))
        return next_interval, next_s, next_d

    @staticmethod
    def grade_answer(word_obj: SavedWord, is_correct: bool, mode: str, typing_time_ms: int = None, is_last_encounter: bool = True) -> dict:
        now = datetime.utcnow()
        today = now.date()
        
        already_processed_today = word_obj.next_review_date > today
        
        # Calculate days elapsed BEFORE updating last_reviewed_at
        days_elapsed = (now - word_obj.last_reviewed_at).days if word_obj.last_reviewed_at else 0
        days_elapsed = max(0, days_elapsed)
            
        word_obj.last_reviewed_at = now
        word_obj.last_mode_played = mode
        
        current_mastery = getattr(word_obj, 'mastery_level', 1)

        # --- FLUIDITY TRACKING (Strictly for UI Analytics, NO PENALTIES) ---
        if typing_time_ms and is_correct:
            current_avg = getattr(word_obj, 'avg_typing_fluidity', None) or typing_time_ms
            word_obj.avg_typing_fluidity = (current_avg * 0.7) + (typing_time_ms * 0.3)

        if is_correct:
            word_obj.total_reviews += 1
            
            if mode in ['audio_dictation', 'blindfolded']:
                word_obj.dictation_streak += 1
            else:
                word_obj.spelling_streak += 1
                
            GamificationService.log_activity('review_passed')

            # --- MACRO STATS: FSRS UPDATE ---
            if is_last_encounter and not already_processed_today:
                word_obj.mastery_level = min(9, current_mastery + 1)
                
                # FSRS Grade Mapping: ALL correct answers get a fair 'Good' (3) now!
                new_interval, new_s, new_d = DojoGrader.calculate_fsrs(
                    stability=word_obj.stability or 0.0,
                    difficulty=word_obj.difficulty or 0.0,
                    grade=3,
                    days_elapsed=days_elapsed
                )
                
                # Apply FSRS math to database
                word_obj.stability = new_s
                word_obj.difficulty = new_d
                word_obj.interval = new_interval
                word_obj.repetitions += 1
                
                # Push the date to the future!
                word_obj.next_review_date = (now + timedelta(days=new_interval)).date()

        else:
            # FAILURE: Punish immediately
            if not already_processed_today:
                word_obj.mastery_level = max(1, current_mastery - 1)
                word_obj.lapses += 1
                
                # FSRS Grade 1 (Again)
                new_interval, new_s, new_d = DojoGrader.calculate_fsrs(
                    stability=word_obj.stability or 0.0,
                    difficulty=word_obj.difficulty or 0.0,
                    grade=1,
                    days_elapsed=days_elapsed
                )
                
                word_obj.stability = new_s
                word_obj.difficulty = new_d
                word_obj.interval = new_interval
                
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
            'slow_penalty_applied': False # Disabled permanently!
        }