from datetime import datetime, timedelta
from ..models import SavedWord
from ..extensions import db, logger
from .gamification import GamificationService # NEW IMPORT

class SRSService:
    @staticmethod
    def process_review(word_obj: SavedWord, passed: bool):
        grade = 5 if passed else 1
        
        if grade >= 3:
            if word_obj.repetitions == 0: word_obj.interval = 1
            elif word_obj.repetitions == 1: word_obj.interval = 6
            else: word_obj.interval = round(word_obj.interval * word_obj.ease_factor)
            word_obj.repetitions += 1
            # NEW: Award XP for a successful review
            GamificationService.log_activity('review_passed')
        else:
            word_obj.repetitions = 0
            word_obj.interval = 1
            word_obj.lapses += 1
            
        word_obj.ease_factor = max(1.3, word_obj.ease_factor + (0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02)))
        word_obj.next_review_date = (datetime.utcnow() + timedelta(days=word_obj.interval)).date()
        word_obj.last_reviewed_at = datetime.utcnow()
        word_obj.total_reviews += 1
        
        db.session.commit()
        return word_obj