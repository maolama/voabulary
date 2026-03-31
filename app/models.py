from datetime import datetime, date
from .extensions import db 

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
        
    senses = db.relationship('SavedSense', backref='saved_word', cascade="all, delete-orphan", lazy=True)
    # NEW: Semantic Relationships
    manual_synonyms = db.relationship('ManualSynonym', backref='saved_word', cascade="all, delete-orphan", lazy=True)
    manual_antonyms = db.relationship('ManualAntonym', backref='saved_word', cascade="all, delete-orphan", lazy=True)


    # ==========================================
    # NEW: ACTIVE DOJO & FSRS TRACKING
    # ==========================================
    # Advanced FSRS parameters for strict scheduling
    stability = db.Column(db.Float, default=0.0) 
    difficulty = db.Column(db.Float, default=0.0)
    
    # NEW: Memrise-style Mastery Level (1 to 9). 
    # Levels 1-3 (Planting), 4-6 (Watering), 7-9 (Forging)
    mastery_level = db.Column(db.Integer, default=1)
    
    # Crucial for triggering the new "Verb Conjugation" mode
    primary_pos = db.Column(db.String(50), nullable=True) 
    
    # Skill tracking: Forces scaffolding if you keep failing dictation/spelling
    spelling_streak = db.Column(db.Integer, default=0)
    dictation_streak = db.Column(db.Integer, default=0)
    
    # Micro-SRS: Average milliseconds between keystrokes.
    avg_typing_fluidity = db.Column(db.Float, nullable=True) 
    
    # Remembers the last challenge you faced so we can cycle through modes dynamically
    last_mode_played = db.Column(db.String(50), nullable=True)


# ==========================================
# The Pinned Dictionary Snippets Model
# ==========================================
class SavedSense(db.Model):
    __tablename__ = 'saved_senses'

    id = db.Column(db.Integer, primary_key=True)
    word_id = db.Column(db.Integer, db.ForeignKey('saved_words.id'), nullable=False)
    
    dict_name = db.Column(db.String(100), nullable=False)
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
    
    current_streak = db.Column(db.Integer, default=0)
    longest_streak = db.Column(db.Integer, default=0)
    last_study_date = db.Column(db.Date, nullable=True)
    
    def update_level(self):
        self.level = (self.total_xp // 100) + 1

# ==========================================
# The Semantic Relationship Models
# ==========================================
class ManualSynonym(db.Model):
    __tablename__ = 'manual_synonyms'
    id = db.Column(db.Integer, primary_key=True)
    word_id = db.Column(db.Integer, db.ForeignKey('saved_words.id'), nullable=False)
    synonym = db.Column(db.String(100), nullable=False)

class ManualAntonym(db.Model):
    __tablename__ = 'manual_antonyms'
    id = db.Column(db.Integer, primary_key=True)
    word_id = db.Column(db.Integer, db.ForeignKey('saved_words.id'), nullable=False)
    antonym = db.Column(db.String(100), nullable=False)