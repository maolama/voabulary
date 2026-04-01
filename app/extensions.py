from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate # NEW

import logging

# Initialize SQLAlchemy
db = SQLAlchemy()
migrate = Migrate() # NEW

# Configure standard industry logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("vocab_engine")