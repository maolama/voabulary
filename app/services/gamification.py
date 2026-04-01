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
    def check_and_repair_streak():
        """
        NEW: The 'Automated Sprinklers' Logic.
        Checks if the user missed yesterday. If so, consumes a sprinkler token 
        to save the streak. Otherwise, resets the streak if missed.
        """
        profile = GamificationService.get_or_create_profile()
        today = date.today()

        if profile.last_study_date:
            days_missed = (today - profile.last_study_date).days

            # If they missed days, but have enough sprinkler tokens
            if days_missed > 1:
                tokens_needed = days_missed - 1
                current_tokens = getattr(profile, 'sprinkler_tokens', 0)
                
                if current_tokens >= tokens_needed:
                    profile.sprinkler_tokens -= tokens_needed
                    logger.info(f"Sprinkler activated! Consumed {tokens_needed} tokens.")
                else:
                    # Not enough tokens. The garden withered.
                    profile.current_streak = 0
                    logger.info("Garden withered. Streak reset to 0.")
                
        db.session.commit()

    @staticmethod
    def log_activity(action_type):
        """Logs daily activity, awards XP, and manages streaks/sprinklers."""
        today = date.today()
        
        # Check for missed days and trigger sprinklers before logging today
        GamificationService.check_and_repair_streak()
        
        activity = StudyActivity.query.filter_by(activity_date=today).first()
        
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
            if activity.reviews_completed is None: activity.reviews_completed = 0
            activity.reviews_completed += 1
            xp_reward = 5
        elif action_type == 'word_added':
            if activity.new_words_added is None: activity.new_words_added = 0
            activity.new_words_added += 1
            xp_reward = 10
            
        if activity.xp_earned is None: activity.xp_earned = 0
        activity.xp_earned += xp_reward
        
        profile = GamificationService.get_or_create_profile()
        
        # Update Total XP and Level
        if profile.total_xp is None: profile.total_xp = 0
        profile.total_xp += xp_reward
        profile.update_level()
        
        # Update Streak and Earn Sprinklers
        if profile.last_study_date != today:
            profile.current_streak += 1
            if profile.current_streak > profile.longest_streak:
                profile.longest_streak = profile.current_streak
            
            # Earn a Sprinkler Token for every 3 days of consistent study
            if profile.current_streak > 0 and profile.current_streak % 3 == 0:
                if not hasattr(profile, 'sprinkler_tokens') or profile.sprinkler_tokens is None:
                    profile.sprinkler_tokens = 0
                profile.sprinkler_tokens += 1
                
        profile.last_study_date = today
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