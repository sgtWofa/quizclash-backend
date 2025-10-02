"""
Database configuration and session management for QuizClash
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not available in packaged executable - use environment variables directly
    pass

# Database URL - handle PyInstaller bundled path and production deployment
import sys

# Check if DATABASE_URL is provided (production deployment)
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    # Production database (PostgreSQL/MySQL)
    # Fix for Heroku/Railway postgres URL format
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    print(f"Using production database: {DATABASE_URL.split('@')[0]}...")
else:
    # Local development or PyInstaller bundle
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Running as PyInstaller bundle - use AppData for writable database location
        app_data_dir = os.path.join(os.environ.get('APPDATA', os.path.dirname(sys.executable)), 'QuizClash')
        os.makedirs(app_data_dir, exist_ok=True)
        db_path = os.path.join(app_data_dir, "quizclash.db")
        DATABASE_URL = f"sqlite:///{db_path}"
        print(f"Using bundled database: {db_path}")
    else:
        # Running as script
        DATABASE_URL = "sqlite:///./quizclash.db"
        print("Using local database: ./quizclash.db")

# Create SQLAlchemy engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for models
Base = declarative_base()

def get_db():
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_tables():
    """Create all database tables"""
    Base.metadata.create_all(bind=engine)
