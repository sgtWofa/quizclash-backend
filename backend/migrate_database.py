"""
Database migration script to add subject_id to questions table
"""
import sqlite3
import os
from backend.database import DATABASE_URL

def migrate_database():
    """Add subject_id column to questions table if it doesn't exist"""
    
    # Extract database path from URL
    db_path = DATABASE_URL.replace("sqlite:///", "")
    
    if not os.path.exists(db_path):
        print("Database doesn't exist yet, will be created with new schema")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if subject_id column exists
        cursor.execute("PRAGMA table_info(questions)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'subject_id' not in columns:
            print("Adding subject_id column to questions table...")
            cursor.execute("ALTER TABLE questions ADD COLUMN subject_id INTEGER")
            
            # Update existing questions to have subject_id based on their topic's subject
            cursor.execute("""
                UPDATE questions 
                SET subject_id = (
                    SELECT topics.subject_id 
                    FROM topics 
                    WHERE topics.id = questions.topic_id
                )
                WHERE questions.topic_id IS NOT NULL
            """)
            
            conn.commit()
            print("Migration completed successfully!")
        else:
            print("subject_id column already exists")
            
    except Exception as e:
        print(f"Migration error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()
