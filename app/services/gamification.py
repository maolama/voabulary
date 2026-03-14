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
        
        if not activity:
            activity = StudyActivity(activity_date=today)
            db.session.add(activity)

        xp_reward = 0
        if action_type == 'review_passed':
            activity.reviews_completed += 1
            xp_reward = 5
        elif action_type == 'word_added':
            activity.new_words_added += 1
            xp_reward = 10
            
        activity.xp_earned += xp_reward
        
        profile = GamificationService.get_or_create_profile()
        profile.total_xp += xp_reward
        profile.update_level()
        
        db.session.commit()

    @staticmethod
    def get_heatmap_data():
        """Returns data for the last 364 days (52 weeks) for the heatmap."""
        today = date.today()
        start_date = today - timedelta(days=364)
        
        # Fetch all activity in the last year
        activities = StudyActivity.query.filter(StudyActivity.activity_date >= start_date).all()
        activity_map = {a.activity_date: a.reviews_completed + a.new_words_added for a in activities}
        
        # Generate the full grid of dates
        heatmap = []
        current_date = start_date
        while current_date <= today:
            count = activity_map.get(current_date, 0)
            # Determine intensity (0 to 4) for Tailwind coloring
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