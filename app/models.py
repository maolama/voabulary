from datetime import datetime, date
from .extensions import db # Make sure this matches your app's structure

# Many-to-Many association table for Words and Tags
word_tags = db.Table('word_tags',
    db.Column('tag_id', db.Integer, db.ForeignKey('tags.id'), primary_key=True),
    db.Column('word_id', db.Integer, db.ForeignKey('saved_words.id'), primary_key=True)
)

class Tag(db.Model):
    __tablename__ = 'tags'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False, index=True)

class SavedWord(db.Model):
    __tablename__ = 'saved_words'
    id = db.Column(db.Integer, primary_key=True)
    word = db.Column(db.String(100), unique=True, nullable=False, index=True)
    
    # SRS Fields (SuperMemo-2 style)
    next_review_date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    interval = db.Column(db.Integer, default=0)
    repetitions = db.Column(db.Integer, default=0)
    ease_factor = db.Column(db.Float, default=2.5)
    
    # Analytics & Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_reviewed_at = db.Column(db.DateTime, nullable=True)
    total_reviews = db.Column(db.Integer, default=0)
    lapses = db.Column(db.Integer, default=0)
    
    # --- Relationships ---
    tags = db.relationship('Tag', secondary=word_tags, lazy='subquery',
        backref=db.backref('words', lazy=True))
        
    # NEW: A word can have multiple pinned dictionary meanings. 
    # cascade="all, delete-orphan" means if you delete the SavedWord, its saved HTML snippets vanish too!
    senses = db.relationship('SavedSense', backref='saved_word', cascade="all, delete-orphan", lazy=True)

# ==========================================
# NEW: The Pinned Dictionary Snippets Model
# ==========================================
class SavedSense(db.Model):
    __tablename__ = 'saved_senses'

    id = db.Column(db.Integer, primary_key=True)
    word_id = db.Column(db.Integer, db.ForeignKey('saved_words.id'), nullable=False)
    
    dict_name = db.Column(db.String(100), nullable=False)
    
    # NEW: Store the specific HTML ID (e.g., "oald-verb-2") 
    # so we can use it for CSS filtering later.
    sense_id = db.Column(db.String(100), nullable=True) 
    
    html_content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'word_id': self.word_id,
            'dict_name': self.dict_name,
            'sense_id': self.sense_id,
            'html_content': self.html_content,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }


class StudyActivity(db.Model):
    """Tracks daily statistics for the GitHub-style Heatmap and XP"""
    __tablename__ = 'study_activity'
    id = db.Column(db.Integer, primary_key=True)
    activity_date = db.Column(db.Date, unique=True, nullable=False, default=date.today, index=True)
    reviews_completed = db.Column(db.Integer, default=0)
    new_words_added = db.Column(db.Integer, default=0)
    xp_earned = db.Column(db.Integer, default=0)

class UserProfile(db.Model):
    """Singleton table to store global user stats like total XP"""
    __tablename__ = 'user_profile'
    id = db.Column(db.Integer, primary_key=True)
    total_xp = db.Column(db.Integer, default=0)
    level = db.Column(db.Integer, default=1)
    
    # NEW: Added streak tracking for gamification
    current_streak = db.Column(db.Integer, default=0)
    longest_streak = db.Column(db.Integer, default=0)
    last_study_date = db.Column(db.Date, nullable=True)
    
    # Let's say 100 XP per level
    def update_level(self):
        self.level = (self.total_xp // 100) + 1