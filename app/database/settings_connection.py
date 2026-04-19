from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

DB_NAME = "settings.db"
DB_PATH = os.path.join(os.path.dirname(__file__), DB_NAME)

SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

# We can use standard SQLite settings without WAL here since it's low traffic, 
# but WAL is nice. Let's keep it simple.
engine_settings = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocalSettings = sessionmaker(autocommit=False, autoflush=False, bind=engine_settings)

BaseSettings = declarative_base()

def get_settings_db():
    db = SessionLocalSettings()
    try:
        yield db
    finally:
        db.close()
