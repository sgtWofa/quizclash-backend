"""
Seed data script for QuizClash application
Creates sample subjects, topics, and questions for testing
"""
import sys
import os
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent
sys.path.append(str(backend_dir.parent))

from backend.database import SessionLocal, create_tables
from backend.models import User, Subject, Topic, Question
from backend.auth import get_password_hash


def create_sample_data():
    """Create sample data for the application"""
    db = SessionLocal()
    
    try:
        # Create tables
        create_tables()
        
        # Clear existing data to reseed with expanded questions
        print("Clearing existing data...")
        db.query(Question).delete()
        db.query(Topic).delete()
        db.query(Subject).delete()
        # Don't delete users to avoid constraint issues
        db.commit()
        
        print("Creating sample data...")
        
        # Create admin user if not exists
        admin_user = db.query(User).filter(User.username == "admin").first()
        if not admin_user:
            admin_user = User(
                username="admin",
                email="admin@quizclash.com",
                password_hash=get_password_hash("admin123"),
                role="admin"
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
        
        # Create sample user if not exists
        sample_user = db.query(User).filter(User.username == "testuser").first()
        if not sample_user:
            sample_user = User(
                username="testuser",
                email="test@quizclash.com",
                password_hash=get_password_hash("password123"),
                role="user",
                total_score=150,
                games_played=5
            )
            db.add(sample_user)
        
        # Create subjects
        subjects_data = [
            {
                "name": "Mathematics",
                "description": "Mathematical concepts and problem solving",
                "icon": "🔢"
            },
            {
                "name": "Science",
                "description": "Physics, Chemistry, and Biology",
                "icon": "🔬"
            },
            {
                "name": "History",
                "description": "World history and historical events",
                "icon": "📚"
            },
            {
                "name": "Geography",
                "description": "World geography and locations",
                "icon": "🌍"
            }
        ]
        
        subjects = []
        for subject_data in subjects_data:
            subject = Subject(
                name=subject_data["name"],
                description=subject_data["description"],
                created_by=admin_user.id
            )
            db.add(subject)
            subjects.append(subject)
        
        db.commit()
        
        # Create topics and questions
        topics_and_questions = {
            "Mathematics": {
                "Arithmetic": [
                    {
                        "text": "What is 15 + 27?",
                        "options": ["40", "42", "44", "46"],
                        "correct": 1,
                        "difficulty": "easy",
                        "explanation": "15 + 27 = 42"
                    },
                    {
                        "text": "What is 8 × 7?",
                        "options": ["54", "56", "58", "60"],
                        "correct": 1,
                        "difficulty": "easy",
                        "explanation": "8 × 7 = 56"
                    },
                    {
                        "text": "What is 144 ÷ 12?",
                        "options": ["10", "11", "12", "13"],
                        "correct": 2,
                        "difficulty": "medium",
                        "explanation": "144 ÷ 12 = 12"
                    },
                    {
                        "text": "What is 25% of 80?",
                        "options": ["15", "20", "25", "30"],
                        "correct": 1,
                        "difficulty": "medium",
                        "explanation": "25% of 80 = 0.25 × 80 = 20"
                    },
                    {
                        "text": "What is 9²?",
                        "options": ["72", "81", "90", "99"],
                        "correct": 1,
                        "difficulty": "easy",
                        "explanation": "9² = 9 × 9 = 81"
                    }
                ],
                "Algebra": [
                    {
                        "text": "Solve for x: 2x + 5 = 15",
                        "options": ["3", "4", "5", "6"],
                        "correct": 2,
                        "difficulty": "medium",
                        "explanation": "2x = 10, so x = 5"
                    },
                    {
                        "text": "What is the value of x² when x = 4?",
                        "options": ["8", "12", "16", "20"],
                        "correct": 2,
                        "difficulty": "easy",
                        "explanation": "4² = 4 × 4 = 16"
                    },
                    {
                        "text": "Solve for y: 3y - 7 = 14",
                        "options": ["5", "6", "7", "8"],
                        "correct": 2,
                        "difficulty": "medium",
                        "explanation": "3y = 21, so y = 7"
                    },
                    {
                        "text": "What is the slope of the line y = 2x + 3?",
                        "options": ["1", "2", "3", "4"],
                        "correct": 1,
                        "difficulty": "medium",
                        "explanation": "In y = mx + b form, m is the slope, so slope = 2"
                    },
                    {
                        "text": "If x = -2, what is x³?",
                        "options": ["-8", "-6", "6", "8"],
                        "correct": 0,
                        "difficulty": "medium",
                        "explanation": "(-2)³ = (-2) × (-2) × (-2) = -8"
                    }
                ],
                "Geometry": [
                    {
                        "text": "What is the area of a rectangle with length 8 and width 5?",
                        "options": ["35", "40", "45", "50"],
                        "correct": 1,
                        "difficulty": "easy",
                        "explanation": "Area = length × width = 8 × 5 = 40"
                    },
                    {
                        "text": "How many degrees are in a triangle?",
                        "options": ["90", "180", "270", "360"],
                        "correct": 1,
                        "difficulty": "easy",
                        "explanation": "The sum of angles in a triangle is always 180°"
                    },
                    {
                        "text": "What is the circumference of a circle with radius 5?",
                        "options": ["10π", "15π", "20π", "25π"],
                        "correct": 0,
                        "difficulty": "medium",
                        "explanation": "Circumference = 2πr = 2π(5) = 10π"
                    },
                    {
                        "text": "What is the area of a circle with radius 3?",
                        "options": ["6π", "9π", "12π", "18π"],
                        "correct": 1,
                        "difficulty": "medium",
                        "explanation": "Area = πr² = π(3)² = 9π"
                    },
                    {
                        "text": "How many sides does a hexagon have?",
                        "options": ["5", "6", "7", "8"],
                        "correct": 1,
                        "difficulty": "easy",
                        "explanation": "A hexagon has 6 sides"
                    }
                ]
            },
            "Science": {
                "Physics": [
                    {
                        "text": "What is the speed of light in vacuum?",
                        "options": ["299,792,458 m/s", "300,000,000 m/s", "186,000 miles/s", "All of the above"],
                        "correct": 0,
                        "difficulty": "medium",
                        "explanation": "The exact speed of light is 299,792,458 meters per second"
                    },
                    {
                        "text": "What force keeps planets in orbit around the sun?",
                        "options": ["Magnetic force", "Gravitational force", "Nuclear force", "Electric force"],
                        "correct": 1,
                        "difficulty": "easy",
                        "explanation": "Gravity is the force that keeps planets orbiting the sun"
                    },
                    {
                        "text": "What is Newton's first law of motion?",
                        "options": ["F = ma", "An object at rest stays at rest", "For every action there is an equal and opposite reaction", "Energy cannot be created or destroyed"],
                        "correct": 1,
                        "difficulty": "medium",
                        "explanation": "Newton's first law states that an object at rest stays at rest unless acted upon by a force"
                    },
                    {
                        "text": "What is the unit of electrical resistance?",
                        "options": ["Volt", "Ampere", "Ohm", "Watt"],
                        "correct": 2,
                        "difficulty": "medium",
                        "explanation": "The ohm (Ω) is the unit of electrical resistance"
                    },
                    {
                        "text": "At what temperature does water boil at sea level?",
                        "options": ["90°C", "95°C", "100°C", "105°C"],
                        "correct": 2,
                        "difficulty": "easy",
                        "explanation": "Water boils at 100°C (212°F) at sea level"
                    }
                ],
                "Chemistry": [
                    {
                        "text": "What is the chemical symbol for gold?",
                        "options": ["Go", "Gd", "Au", "Ag"],
                        "correct": 2,
                        "difficulty": "medium",
                        "explanation": "Au comes from the Latin word 'aurum' meaning gold"
                    },
                    {
                        "text": "How many protons does a carbon atom have?",
                        "options": ["4", "6", "8", "12"],
                        "correct": 1,
                        "difficulty": "medium",
                        "explanation": "Carbon has 6 protons, which defines it as carbon"
                    },
                    {
                        "text": "What is the pH of pure water?",
                        "options": ["6", "7", "8", "9"],
                        "correct": 1,
                        "difficulty": "easy",
                        "explanation": "Pure water has a neutral pH of 7"
                    },
                    {
                        "text": "What gas makes up about 78% of Earth's atmosphere?",
                        "options": ["Oxygen", "Nitrogen", "Carbon dioxide", "Argon"],
                        "correct": 1,
                        "difficulty": "medium",
                        "explanation": "Nitrogen makes up about 78% of Earth's atmosphere"
                    },
                    {
                        "text": "What is the chemical formula for water?",
                        "options": ["H2O", "CO2", "NaCl", "CH4"],
                        "correct": 0,
                        "difficulty": "easy",
                        "explanation": "Water is H2O - two hydrogen atoms and one oxygen atom"
                    }
                ],
                "Biology": [
                    {
                        "text": "What is the powerhouse of the cell?",
                        "options": ["Nucleus", "Ribosome", "Mitochondria", "Chloroplast"],
                        "correct": 2,
                        "difficulty": "easy",
                        "explanation": "Mitochondria produce ATP, the cell's energy currency"
                    },
                    {
                        "text": "Which blood type is known as the universal donor?",
                        "options": ["A", "B", "AB", "O"],
                        "correct": 3,
                        "difficulty": "medium",
                        "explanation": "Type O blood can be donated to any blood type"
                    },
                    {
                        "text": "What process do plants use to make food from sunlight?",
                        "options": ["Respiration", "Photosynthesis", "Digestion", "Fermentation"],
                        "correct": 1,
                        "difficulty": "easy",
                        "explanation": "Photosynthesis converts sunlight, CO2, and water into glucose"
                    },
                    {
                        "text": "How many chambers does a human heart have?",
                        "options": ["2", "3", "4", "5"],
                        "correct": 2,
                        "difficulty": "easy",
                        "explanation": "The human heart has 4 chambers: 2 atria and 2 ventricles"
                    },
                    {
                        "text": "What is DNA short for?",
                        "options": ["Deoxyribonucleic acid", "Dinitrogen oxide", "Dextrose nucleic acid", "Dynamic nuclear acid"],
                        "correct": 0,
                        "difficulty": "medium",
                        "explanation": "DNA stands for Deoxyribonucleic acid"
                    }
                ]
            },
            "History": {
                "Ancient History": [
                    {
                        "text": "Which ancient wonder of the world was located in Alexandria?",
                        "options": ["Colossus of Rhodes", "Lighthouse of Alexandria", "Hanging Gardens", "Temple of Artemis"],
                        "correct": 1,
                        "difficulty": "medium",
                        "explanation": "The Lighthouse of Alexandria was one of the Seven Wonders"
                    },
                    {
                        "text": "Who was the first emperor of Rome?",
                        "options": ["Julius Caesar", "Augustus", "Nero", "Trajan"],
                        "correct": 1,
                        "difficulty": "medium",
                        "explanation": "Augustus (Octavian) was the first Roman Emperor"
                    },
                    {
                        "text": "Which civilization built Machu Picchu?",
                        "options": ["Aztec", "Maya", "Inca", "Olmec"],
                        "correct": 2,
                        "difficulty": "medium",
                        "explanation": "Machu Picchu was built by the Inca civilization in Peru"
                    },
                    {
                        "text": "What was the capital of the Byzantine Empire?",
                        "options": ["Rome", "Athens", "Constantinople", "Alexandria"],
                        "correct": 2,
                        "difficulty": "medium",
                        "explanation": "Constantinople (modern-day Istanbul) was the Byzantine capital"
                    },
                    {
                        "text": "Which pharaoh built the Great Pyramid of Giza?",
                        "options": ["Khufu", "Khafre", "Menkaure", "Tutankhamun"],
                        "correct": 0,
                        "difficulty": "hard",
                        "explanation": "The Great Pyramid was built for Pharaoh Khufu (Cheops)"
                    }
                ],
                "World Wars": [
                    {
                        "text": "In which year did World War II end?",
                        "options": ["1944", "1945", "1946", "1947"],
                        "correct": 1,
                        "difficulty": "easy",
                        "explanation": "World War II ended in 1945 with Japan's surrender"
                    },
                    {
                        "text": "Which event triggered the start of World War I?",
                        "options": ["Sinking of Lusitania", "Assassination of Archduke Franz Ferdinand", "German invasion of Belgium", "Russian Revolution"],
                        "correct": 1,
                        "difficulty": "medium",
                        "explanation": "The assassination in Sarajevo triggered the war"
                    },
                    {
                        "text": "What was the code name for the D-Day invasion?",
                        "options": ["Operation Barbarossa", "Operation Overlord", "Operation Market Garden", "Operation Torch"],
                        "correct": 1,
                        "difficulty": "hard",
                        "explanation": "Operation Overlord was the code name for the Normandy landings"
                    },
                    {
                        "text": "Which country was NOT part of the Axis powers?",
                        "options": ["Germany", "Italy", "Japan", "Soviet Union"],
                        "correct": 3,
                        "difficulty": "medium",
                        "explanation": "The Soviet Union was part of the Allied powers"
                    },
                    {
                        "text": "When did the United States enter World War I?",
                        "options": ["1914", "1915", "1916", "1917"],
                        "correct": 3,
                        "difficulty": "medium",
                        "explanation": "The US entered WWI in April 1917"
                    }
                ]
            },
            "Geography": {
                "World Capitals": [
                    {
                        "text": "What is the capital of Australia?",
                        "options": ["Sydney", "Melbourne", "Canberra", "Perth"],
                        "correct": 2,
                        "difficulty": "medium",
                        "explanation": "Canberra is the capital, not Sydney or Melbourne"
                    },
                    {
                        "text": "Which city is the capital of Canada?",
                        "options": ["Toronto", "Vancouver", "Montreal", "Ottawa"],
                        "correct": 3,
                        "difficulty": "easy",
                        "explanation": "Ottawa is the capital city of Canada"
                    },
                    {
                        "text": "What is the capital of Brazil?",
                        "options": ["São Paulo", "Rio de Janeiro", "Brasília", "Salvador"],
                        "correct": 2,
                        "difficulty": "medium",
                        "explanation": "Brasília is the capital of Brazil, built in the 1960s"
                    },
                    {
                        "text": "Which city is the capital of Japan?",
                        "options": ["Osaka", "Tokyo", "Kyoto", "Hiroshima"],
                        "correct": 1,
                        "difficulty": "easy",
                        "explanation": "Tokyo is the capital and largest city of Japan"
                    },
                    {
                        "text": "What is the capital of South Africa?",
                        "options": ["Johannesburg", "Cape Town", "Pretoria", "Durban"],
                        "correct": 2,
                        "difficulty": "hard",
                        "explanation": "Pretoria is the executive capital (South Africa has three capitals)"
                    }
                ],
                "Rivers and Mountains": [
                    {
                        "text": "Which is the longest river in the world?",
                        "options": ["Amazon", "Nile", "Mississippi", "Yangtze"],
                        "correct": 1,
                        "difficulty": "medium",
                        "explanation": "The Nile River is generally considered the longest"
                    },
                    {
                        "text": "What is the highest mountain in the world?",
                        "options": ["K2", "Mount Everest", "Kangchenjunga", "Lhotse"],
                        "correct": 1,
                        "difficulty": "easy",
                        "explanation": "Mount Everest is the highest peak at 8,848.86 meters"
                    },
                    {
                        "text": "Which river flows through the Grand Canyon?",
                        "options": ["Colorado River", "Mississippi River", "Rio Grande", "Columbia River"],
                        "correct": 0,
                        "difficulty": "medium",
                        "explanation": "The Colorado River carved the Grand Canyon over millions of years"
                    },
                    {
                        "text": "What is the largest desert in the world?",
                        "options": ["Sahara", "Gobi", "Antarctica", "Arabian"],
                        "correct": 2,
                        "difficulty": "hard",
                        "explanation": "Antarctica is technically the largest desert (cold desert)"
                    },
                    {
                        "text": "Which mountain range contains Mount Everest?",
                        "options": ["Andes", "Rocky Mountains", "Himalayas", "Alps"],
                        "correct": 2,
                        "difficulty": "easy",
                        "explanation": "Mount Everest is located in the Himalayas"
                    }
                ]
            }
        }
        
        # Create topics and questions
        for subject in subjects:
            if subject.name in topics_and_questions:
                topic_data = topics_and_questions[subject.name]
                
                for topic_name, questions_data in topic_data.items():
                    # Create topic
                    topic = Topic(
                        name=topic_name,
                        subject_id=subject.id,
                        description=f"{topic_name} questions in {subject.name}",
                        question_count=len(questions_data)
                    )
                    db.add(topic)
                    db.commit()
                    db.refresh(topic)
                    
                    # Create questions
                    for question_data in questions_data:
                        question = Question(
                            text=question_data["text"],
                            topic_id=topic.id,
                            options=question_data["options"],
                            correct_answer=question_data["correct"],
                            difficulty=question_data["difficulty"],
                            explanation=question_data.get("explanation", "")
                        )
                        db.add(question)
        
        db.commit()
        print("✅ Sample data created successfully!")
        print("\nSample accounts:")
        print("Admin - Username: admin, Password: admin123")
        print("User - Username: testuser, Password: password123")
        
    except Exception as e:
        print(f"❌ Error creating sample data: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    create_sample_data()
