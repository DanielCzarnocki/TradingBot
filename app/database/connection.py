from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# Root of the project is where main.py is (BOT/)
# Database is in app/database/mexc_data.db
DB_NAME = "mexc_data.db"
DB_PATH = os.path.join(os.path.dirname(__file__), DB_NAME)

SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

from sqlalchemy import event

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
