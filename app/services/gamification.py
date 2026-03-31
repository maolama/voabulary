from datetime import datetime, date, timedelta
from ..models import StudyActivity, UserProfile
from ..extensions import db, logger

class GamificationService:
    @staticmethod
    def get_or_create_profile():
        profile = UserProfile.query.first()
        if not profile:
            profile = UserProfile(total_xp=0, level=1)
            db.session.add(profile)
            db.session.commit()
        return profile

    @staticmethod
    def log_activity(action_type):
        """Logs daily activity and awards XP."""
        today = date.today()
        activity = StudyActivity.query.filter_by(activity_date=today).first()
        
        # FIXED: Explicitly set defaults to 0 so we can safely += 1 to them
        if not activity:
            activity = StudyActivity(
                activity_date=today,
                reviews_completed=0,
                new_words_added=0,
                xp_earned=0
            )
            db.session.add(activity)

        xp_reward = 0
        if action_type == 'review_passed':
            # Failsafe: if an existing DB row somehow returned None
            if activity.reviews_completed is None: activity.reviews_completed = 0
            activity.reviews_completed += 1
            xp_reward = 5
        elif action_type == 'word_added':
            # Failsafe
            if activity.new_words_added is None: activity.new_words_added = 0
            activity.new_words_added += 1
            xp_reward = 10
            
        if activity.xp_earned is None: activity.xp_earned = 0
        activity.xp_earned += xp_reward
        
        profile = GamificationService.get_or_create_profile()
        if profile.total_xp is None: profile.total_xp = 0
        profile.total_xp += xp_reward
        profile.update_level()
        
        db.session.commit()

    @staticmethod
    def get_heatmap_data():
        """Returns data for the last 364 days (52 weeks) for the heatmap."""
        today = date.today()
        start_date = today - timedelta(days=364)
        
        activities = StudyActivity.query.filter(StudyActivity.activity_date >= start_date).all()
        # Fallback to 0 if None
        activity_map = {a.activity_date: (a.reviews_completed or 0) + (a.new_words_added or 0) for a in activities}
        
        heatmap = []
        current_date = start_date
        while current_date <= today:
            count = activity_map.get(current_date, 0)
            intensity = 0
            if count > 0: intensity = 1
            if count > 10: intensity = 2
            if count > 30: intensity = 3
            if count > 50: intensity = 4
                
            heatmap.append({
                'date': current_date.strftime('%Y-%m-%d'),
                'count': count,
                'intensity': intensity
            })
            current_date += timedelta(days=1)
            
        return heatmap