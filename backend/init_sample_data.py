"""
Initialize database with sample subjects, topics, and questions
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from backend.database import SessionLocal, engine
from backend.models import Base, Subject, Topic, Question, User
from backend.auth import get_password_hash
import json

def create_sample_data():
    """Create sample subjects, topics, and questions"""
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    try:
        # Check if data already exists
        if db.query(Subject).count() > 0 and db.query(Topic).count() > 0:
            print("Sample data already exists")
            return
        
        # Create admin user if not exists
        admin_user = db.query(User).filter(User.username == "admin").first()
        if not admin_user:
            admin_user = User(
                username="admin",
                email="admin@quizclash.com",
                password_hash=get_password_hash("admin123"),  # Default password: admin123
                role="admin"
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
            print("Created admin user - Username: admin, Password: admin123")
        
        # Sample data structure
        sample_data = {
            "Mathematics": {
                "description": "Mathematical concepts and problem solving",
                "topics": {
                    "Algebra": [
                        {
                            "text": "What is the value of x in the equation 2x + 5 = 15?",
                            "options": ["5", "10", "7", "3"],
                            "correct_answer": 0,
                            "difficulty": "easy",
                            "explanation": "Solve: 2x + 5 = 15, so 2x = 10, therefore x = 5"
                        },
                        {
                            "text": "Simplify: (x + 3)(x - 2)",
                            "options": ["x² + x - 6", "x² - x + 6", "x² + 5x - 6", "x² - 5x + 6"],
                            "correct_answer": 0,
                            "difficulty": "medium",
                            "explanation": "Use FOIL: x² - 2x + 3x - 6 = x² + x - 6"
                        }
                    ],
                    "Geometry": [
                        {
                            "text": "What is the area of a circle with radius 5?",
                            "options": ["25π", "10π", "5π", "15π"],
                            "correct_answer": 0,
                            "difficulty": "easy",
                            "explanation": "Area = πr² = π(5)² = 25π"
                        },
                        {
                            "text": "In a right triangle, if one angle is 30°, what is the other acute angle?",
                            "options": ["60°", "45°", "30°", "90°"],
                            "correct_answer": 0,
                            "difficulty": "easy",
                            "explanation": "In a triangle, angles sum to 180°. With 90° and 30°, the third is 60°"
                        }
                    ]
                }
            },
            "Science": {
                "description": "Physics, Chemistry, and Biology",
                "topics": {
                    "Physics": [
                        {
                            "text": "What is the speed of light in vacuum?",
                            "options": ["3×10⁸ m/s", "3×10⁶ m/s", "3×10¹⁰ m/s", "3×10⁴ m/s"],
                            "correct_answer": 0,
                            "difficulty": "medium",
                            "explanation": "The speed of light in vacuum is approximately 299,792,458 m/s ≈ 3×10⁸ m/s"
                        }
                    ],
                    "Chemistry": [
                        {
                            "text": "What is the chemical symbol for gold?",
                            "options": ["Au", "Ag", "Go", "Gd"],
                            "correct_answer": 0,
                            "difficulty": "easy",
                            "explanation": "Gold's symbol Au comes from its Latin name 'aurum'"
                        }
                    ],
                    "Biology": [
                        {
                            "text": "What is the powerhouse of the cell?",
                            "options": ["Mitochondria", "Nucleus", "Ribosome", "Chloroplast"],
                            "correct_answer": 0,
                            "difficulty": "easy",
                            "explanation": "Mitochondria produce ATP, the cell's energy currency"
                        }
                    ]
                }
            },
            "History": {
                "description": "World history and historical events",
                "topics": {
                    "World History": [
                        {
                            "text": "In which year did World War II end?",
                            "options": ["1945", "1944", "1946", "1943"],
                            "correct_answer": 0,
                            "difficulty": "easy",
                            "explanation": "World War II ended in 1945 with Japan's surrender in September"
                        }
                    ],
                    "Ancient History": [
                        {
                            "text": "Who was the first emperor of Rome?",
                            "options": ["Augustus", "Julius Caesar", "Nero", "Trajan"],
                            "correct_answer": 0,
                            "difficulty": "medium",
                            "explanation": "Augustus (originally Octavian) became the first Roman emperor in 27 BCE"
                        }
                    ]
                }
            },
            "Geography": {
                "description": "World geography and locations",
                "topics": {
                    "World Capitals": [
                        {
                            "text": "What is the capital of Australia?",
                            "options": ["Canberra", "Sydney", "Melbourne", "Perth"],
                            "correct_answer": 0,
                            "difficulty": "medium",
                            "explanation": "Canberra is Australia's capital, though Sydney and Melbourne are larger cities"
                        }
                    ],
                    "Physical Geography": [
                        {
                            "text": "Which is the longest river in the world?",
                            "options": ["Nile", "Amazon", "Mississippi", "Yangtze"],
                            "correct_answer": 0,
                            "difficulty": "easy",
                            "explanation": "The Nile River is approximately 6,650 km long"
                        }
                    ]
                }
            }
        }
        
        # Create subjects, topics, and questions
        for subject_name, subject_info in sample_data.items():
            # Create subject
            subject = Subject(
                name=subject_name,
                description=subject_info["description"],
                created_by=admin_user.id
            )
            db.add(subject)
            db.commit()
            db.refresh(subject)
            
            # Create topics and questions
            for topic_name, questions_data in subject_info["topics"].items():
                # Create topic
                topic = Topic(
                    name=topic_name,
                    description=f"{topic_name} related questions",
                    subject_id=subject.id
                )
                db.add(topic)
                db.commit()
                db.refresh(topic)
                
                # Create questions
                for question_data in questions_data:
                    question = Question(
                        text=question_data["text"],
                        topic_id=topic.id,
                        subject_id=subject.id,  # Add subject_id
                        options=question_data["options"],
                        correct_answer=question_data["correct_answer"],
                        difficulty=question_data["difficulty"],
                        explanation=question_data["explanation"]
                    )
                    db.add(question)
                
                db.commit()
        
        print("Sample data created successfully!")
        
    except Exception as e:
        print(f"Error creating sample data: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_sample_data()
