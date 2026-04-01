import os
from flask import Flask
from .extensions import db, logger, migrate
from .services.dictionary import DictionaryService

# Global dictionary service instance
dict_service = DictionaryService()

def create_app():
    app = Flask(__name__)
    
    # Configuration
    current_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(current_dir) # Goes up one level to the root folder
    
    data_dir = os.path.join(base_dir, 'data')
    os.makedirs(data_dir, exist_ok=True)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(data_dir, 'user_data.db')}"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    
    # Initialize our Dictionary Service (Compiles MDX/MDD to SQLite if needed)
    dict_dir = os.path.join(base_dir, 'dict')
    dict_service.initialize(dict_dir)
    
    # Register Blueprints (Routes)
    from .routes.main import bp as main_bp
    from .routes.api import bp as api_bp
    from .routes.data import bp as data_bp
    from .routes.review import bp as review_bp # NEW: Our Active Dojo API

    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(data_bp, url_prefix='/data')
    app.register_blueprint(review_bp, url_prefix='/api/review') # NEW: Registered here!
    
    # Create database tables
    with app.app_context():
        db.create_all()
        logger.info("Application initialized and database verified.")
        
    return app