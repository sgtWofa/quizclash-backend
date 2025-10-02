"""
Seed database with questions from the questions bank folder
"""
import json
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from backend.database import SessionLocal, engine
from backend.models import Base, Subject, Topic, Question, User

def convert_answer_to_index(answer):
    """Convert answer format to 0-based index"""
    if isinstance(answer, int):
        return answer
    elif isinstance(answer, str):
        if answer.upper() in ['A', 'B', 'C', 'D']:
            return ord(answer.upper()) - ord('A')
        try:
            return int(answer)
        except:
            return 0
    return 0

def parse_commerce_format(data, subject_name):
    """Parse Commerce/Geography/History format: {"topic": [[question, [options], answer_index], ...]}"""
    parsed_data = {}
    
    for topic_name, questions in data.items():
        parsed_questions = []
        
        for question_data in questions:
            if len(question_data) >= 3:
                question_text = question_data[0]
                options = question_data[1]
                correct_answer = convert_answer_to_index(question_data[2])
                
                # Clean up question text (remove numbering)
                question_text = question_text.split('. ', 1)[-1] if '. ' in question_text else question_text
                
                # Clean up options (remove A., B., etc.)
                clean_options = []
                for option in options:
                    clean_option = option
                    if option.startswith(('A. ', 'B. ', 'C. ', 'D. ')):
                        clean_option = option[3:]
                    clean_options.append(clean_option)
                
                parsed_questions.append({
                    "text": question_text,
                    "options": clean_options,
                    "correct_answer": correct_answer,
                    "difficulty": "medium"
                })
        
        if parsed_questions:
            parsed_data[topic_name] = parsed_questions
    
    return {subject_name: {"topics": parsed_data}}

def parse_mcq_4000_format(data):
    """Parse mcq_4000.json format with nested subjects and topics"""
    parsed_data = {}
    
    topics_data = data.get("topics", {})
    
    for subject_name, subject_topics in topics_data.items():
        if subject_name not in parsed_data:
            parsed_data[subject_name] = {"topics": {}}
        
        for topic_name, questions in subject_topics.items():
            parsed_questions = []
            
            for question_data in questions:
                if isinstance(question_data, dict):
                    question_text = question_data.get("question", "")
                    options_dict = question_data.get("options", {})
                    answer = question_data.get("answer", "A")
                    
                    # Convert options dict to list
                    options = [options_dict.get(key, "") for key in ['A', 'B', 'C', 'D']]
                    correct_answer = convert_answer_to_index(answer)
                    
                    parsed_questions.append({
                        "text": question_text,
                        "options": options,
                        "correct_answer": correct_answer,
                        "difficulty": "medium"
                    })
            
            if parsed_questions:
                parsed_data[subject_name]["topics"][topic_name] = parsed_questions
    
    return parsed_data

def load_questions_from_files():
    """Load and parse all question files"""
    questions_dir = "assets/questions bank"
    all_data = {}
    
    # File mappings
    file_mappings = {
        "Commerce_MCQ_Full_50_each.json": "Commerce",
        "Geography_MCQ_Full_50_each.json": "Geography", 
        "History_MCQ_Full_50_each.json": "History",
        "Literature_MCQ_Full_50_each.json": "Literature",
        "religion_mcq_350.json": "Religion",
        "mcq_4000.json": None  # Special handling for multiple subjects
    }
    
    for filename, subject_name in file_mappings.items():
        filepath = os.path.join(questions_dir, filename)
        
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                if filename == "mcq_4000.json":
                    # Special parsing for mcq_4000.json
                    parsed = parse_mcq_4000_format(data)
                    for subj, subj_data in parsed.items():
                        if subj not in all_data:
                            all_data[subj] = {"topics": {}}
                        all_data[subj]["topics"].update(subj_data["topics"])
                else:
                    # Standard parsing for other files
                    parsed = parse_commerce_format(data, subject_name)
                    for subj, subj_data in parsed.items():
                        if subj not in all_data:
                            all_data[subj] = {"topics": {}}
                        all_data[subj]["topics"].update(subj_data["topics"])
                
                print(f"Loaded {filename}")
                
            except Exception as e:
                print(f"Error loading {filename}: {e}")
    
    return all_data

def migrate_database():
    """Add subject_id column to questions table if it doesn't exist"""
    import sqlite3
    from backend.database import DATABASE_URL
    
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

def seed_database():
    """Seed database with questions bank data"""
    
    # Run migration first
    migrate_database()
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    try:
        # Create admin user if not exists
        admin_user = db.query(User).filter(User.username == "admin").first()
        if not admin_user:
            admin_user = User(
                username="admin",
                email="admin@quizclash.com",
                password_hash="hashed_password",
                role="admin"
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
        
        # Load questions data
        print("Loading questions from files...")
        questions_data = load_questions_from_files()
        
        # Subject descriptions
        subject_descriptions = {
            "Commerce": "Business, marketing, economics and commercial activities",
            "Geography": "Physical and human geography, countries, capitals and landmarks",
            "History": "World history, historical events and important figures",
            "Literature": "Classic and modern literature, poetry and literary analysis",
            "Religion": "Major world religions, beliefs and religious practices",
            "Science": "Physics, chemistry, biology and scientific concepts",
            "Sports & Entertainment": "Sports, movies, music and entertainment",
            "Technology": "Computer science, programming and technological innovations"
        }
        
        total_questions = 0
        
        # Create subjects, topics, and questions
        for subject_name, subject_data in questions_data.items():
            print(f"\nProcessing subject: {subject_name}")
            
            # Create or get subject
            subject = db.query(Subject).filter(Subject.name == subject_name).first()
            if not subject:
                subject = Subject(
                    name=subject_name,
                    description=subject_descriptions.get(subject_name, f"{subject_name} related questions"),
                    created_by=admin_user.id
                )
                db.add(subject)
                db.commit()
                db.refresh(subject)
            
            # Process topics
            for topic_name, questions in subject_data["topics"].items():
                print(f"  Processing topic: {topic_name} ({len(questions)} questions)")
                
                # Create or get topic
                topic = db.query(Topic).filter(
                    Topic.name == topic_name,
                    Topic.subject_id == subject.id
                ).first()
                
                if not topic:
                    topic = Topic(
                        name=topic_name,
                        description=f"{topic_name} questions in {subject_name}",
                        subject_id=subject.id,
                        question_count=len(questions)
                    )
                    db.add(topic)
                    db.commit()
                    db.refresh(topic)
                
                # Add questions
                existing_questions = db.query(Question).filter(
                    Question.topic_id == topic.id,
                    Question.subject_id == subject.id
                ).count()
                
                if existing_questions == 0:  # Only add if no questions exist for this topic
                    for question_data in questions:
                        question = Question(
                            text=question_data["text"],
                            topic_id=topic.id,
                            subject_id=subject.id,
                            options=question_data["options"],
                            correct_answer=question_data["correct_answer"],
                            difficulty=question_data["difficulty"],
                            explanation=f"This question is from {topic_name} in {subject_name}"
                        )
                        db.add(question)
                        total_questions += 1
                    
                    # Update topic question count
                    topic.question_count = len(questions)
                    db.commit()
        
        print(f"\n✅ Database seeded successfully!")
        print(f"📊 Total questions added: {total_questions}")
        print(f"📚 Subjects: {len(questions_data)}")
        
        # Print summary
        subjects = db.query(Subject).all()
        for subject in subjects:
            topic_count = db.query(Topic).filter(Topic.subject_id == subject.id).count()
            question_count = db.query(Question).filter(Question.subject_id == subject.id).count()
            print(f"  {subject.name}: {topic_count} topics, {question_count} questions")
        
    except Exception as e:
        print(f"❌ Error seeding database: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
