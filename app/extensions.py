from flask_sqlalchemy import SQLAlchemy
import logging

# Initialize SQLAlchemy
db = SQLAlchemy()

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