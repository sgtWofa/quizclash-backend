"""
Database Migration Script for Multimedia Question Support
Adds multimedia fields to existing questions table
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import sys
import os

# Add the backend directory to Python path
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_dir)

from database import get_database_url, Base
from models import Question


def run_multimedia_migration():
    """Run migration to add multimedia support to questions table"""
    
    print("Starting multimedia migration for questions table...")
    
    # Get database URL
    database_url = get_database_url()
    engine = create_engine(database_url)
    
    # Create session
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    try:
        # Check if multimedia columns already exist
        result = session.execute(text("PRAGMA table_info(questions)"))
        columns = [row[1] for row in result.fetchall()]
        
        multimedia_columns = ['media_type', 'media_url', 'media_metadata']
        missing_columns = [col for col in multimedia_columns if col not in columns]
        
        if not missing_columns:
            print("✅ Multimedia columns already exist in questions table")
            return True
        
        print(f"Adding missing columns: {missing_columns}")
        
        # Add multimedia columns if they don't exist
        if 'media_type' not in columns:
            session.execute(text("ALTER TABLE questions ADD COLUMN media_type VARCHAR(20) DEFAULT 'text'"))
            print("✅ Added media_type column")
        
        if 'media_url' not in columns:
            session.execute(text("ALTER TABLE questions ADD COLUMN media_url VARCHAR(500)"))
            print("✅ Added media_url column")
        
        if 'media_metadata' not in columns:
            session.execute(text("ALTER TABLE questions ADD COLUMN media_metadata JSON"))
            print("✅ Added media_metadata column")
        
        # Commit changes
        session.commit()
        
        # Update existing questions to have default media_type
        session.execute(text("UPDATE questions SET media_type = 'text' WHERE media_type IS NULL"))
        session.commit()
        
        print("✅ Migration completed successfully!")
        print("📝 All existing questions now support multimedia content")
        
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        session.rollback()
        return False
        
    finally:
        session.close()


def create_media_directories():
    """Create necessary media directories"""
    
    print("Creating media directories...")
    
    media_dirs = [
        "assets/media",
        "assets/media/questions",
        "assets/media/images",
        "assets/media/audio", 
        "assets/media/video"
    ]
    
    for directory in media_dirs:
        try:
            os.makedirs(directory, exist_ok=True)
            print(f"✅ Created directory: {directory}")
        except Exception as e:
            print(f"❌ Failed to create directory {directory}: {e}")


def verify_migration():
    """Verify that the migration was successful"""
    
    print("Verifying multimedia migration...")
    
    database_url = get_database_url()
    engine = create_engine(database_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    try:
        # Check table structure
        result = session.execute(text("PRAGMA table_info(questions)"))
        columns = {row[1]: row[2] for row in result.fetchall()}
        
        required_columns = {
            'media_type': 'VARCHAR(20)',
            'media_url': 'VARCHAR(500)', 
            'media_metadata': 'JSON'
        }
        
        all_present = True
        for col_name, col_type in required_columns.items():
            if col_name in columns:
                print(f"✅ Column {col_name} exists")
            else:
                print(f"❌ Column {col_name} missing")
                all_present = False
        
        if all_present:
            print("✅ All multimedia columns are present")
            
            # Check default values
            result = session.execute(text("SELECT COUNT(*) FROM questions WHERE media_type = 'text'"))
            text_questions = result.fetchone()[0]
            
            result = session.execute(text("SELECT COUNT(*) FROM questions"))
            total_questions = result.fetchone()[0]
            
            print(f"📊 Questions with text media type: {text_questions}/{total_questions}")
            
            return True
        else:
            print("❌ Migration verification failed")
            return False
            
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False
        
    finally:
        session.close()


if __name__ == "__main__":
    print("🚀 QuizClash Multimedia Migration")
    print("=" * 40)
    
    # Run migration
    if run_multimedia_migration():
        # Create directories
        create_media_directories()
        
        # Verify migration
        if verify_migration():
            print("\n🎉 Multimedia support successfully added to QuizClash!")
            print("📝 You can now create questions with images, audio, and video content")
        else:
            print("\n❌ Migration verification failed")
    else:
        print("\n❌ Migration failed")
