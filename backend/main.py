"""
FastAPI main application for QuizClash backend
"""
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, func
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel
import time
import uvicorn
import json
import os

from backend.database import get_db, create_tables
from backend.models import User, Subject, Topic, Question, GameSession, GameAnswer, Achievement, Leaderboard, PowerupPurchase
from backend.tournament_models import Tournament, TournamentParticipant, TournamentSession, TournamentAnswer, TournamentPrize
from backend.tournament_api import router as tournament_router
from backend.audio_settings_api import router as audio_settings_router
from backend.backup_api import router as backup_router
from backend.achievements_api import router as achievements_router
from backend.schemas import (
    UserCreate, UserLogin, Token, UserResponse, 
    SubjectResponse, TopicResponse, QuestionResponse,
    GameSessionCreate, GameSessionResponse, GameAnswerCreate,
    UserUpdate, UserStatusUpdate, QuestionCreate, QuestionUpdate,
    SubjectCreate, SubjectUpdate, TopicCreate, TopicUpdate,
    APIResponse, UserStats
)
from backend.auth import (
    authenticate_user, create_access_token, get_current_active_user, get_current_user,
    get_admin_user, get_password_hash, verify_password, ACCESS_TOKEN_EXPIRE_MINUTES
)

# Create FastAPI app
app = FastAPI(
    title="QuizClash API",
    description="Modern quiz game backend with role-based access and multiplayer support",
    version="1.0.0"
)

# Add request logging middleware
@app.middleware("http")
async def log_requests(request, call_next):
    print(f"DEBUG: {request.method} {request.url.path}")
    if "admin/questions" in str(request.url.path):
        print(f"DEBUG: Headers: {dict(request.headers)}")
    response = await call_next(request)
    if "admin/questions" in str(request.url.path):
        print(f"DEBUG: Response status: {response.status_code}")
    return response

# Simple in-memory cache for question generation
question_cache = {}
CACHE_DURATION = 300  # 5 minutes

# Pre-warm popular question sets on startup
def pre_warm_cache():
    """Pre-warm cache with popular question combinations"""
    print("DEBUG: Pre-warming question cache...")
    try:
        from backend.database import get_db
        db = next(get_db())
        
        # Popular combinations to pre-cache
        popular_combos = [
            ("Current Affairs", ["Global Politics", "World Economy & Finance"], "Medium", 10),
            ("Science", ["Physics Basics", "Chemistry Elements"], "Easy", 5),
            ("History", ["World Wars", "Ancient Civilizations"], "Medium", 10),
            ("Geography", ["World Capitals", "Major Rivers"], "Easy", 5),
        ]
        
        for subject, topics, difficulty, count in popular_combos:
            try:
                # Simulate a request to cache it
                cache_key = f"{subject}_{sorted(topics)}_{difficulty}_{count}"
                
                # Quick database check
                subject_obj = db.query(Subject).filter(Subject.name == subject).first()
                if subject_obj:
                    topic_objs = db.query(Topic).filter(
                        Topic.subject_id == subject_obj.id,
                        Topic.name.in_(topics)
                    ).limit(2).all()
                    
                    if len(topic_objs) >= 1:
                        questions = db.query(Question).filter(
                            Question.topic_id.in_([t.id for t in topic_objs])
                        ).limit(count).all()
                        
                        if questions:
                            # Cache sample result
                            sample_questions = [{
                                "id": q.id,
                                "text": q.text,
                                "options": q.options,
                                "correct_answer": q.correct_answer,
                                "hint": "Pre-cached question",
                                "subject": subject,
                                "difficulty": difficulty,
                                "points": 100
                            } for q in questions[:count]]
                            
                            question_cache[cache_key] = ({"questions": sample_questions}, time.time())
                            print(f"DEBUG: Pre-cached {len(sample_questions)} questions for {subject}")
            except Exception as e:
                print(f"DEBUG: Failed to pre-cache {subject}: {e}")
        
        print(f"DEBUG: Pre-warming completed. Cache has {len(question_cache)} entries")
    except Exception as e:
        print(f"DEBUG: Pre-warming failed: {e}")

# Schedule aggressive pre-warming after startup
import threading
def delayed_pre_warm():
    time.sleep(1)  # Reduced wait time
    pre_warm_cache()
    # Additional warm-up for common requests
    time.sleep(2)
    pre_warm_cache()  # Run twice for better coverage

threading.Thread(target=delayed_pre_warm, daemon=True).start()

# CORS middleware - Production ready with environment-based configuration
allowed_origins = [
    "http://localhost:3000",  # Local development
    "http://127.0.0.1:8000",  # Local API
    os.getenv("FRONTEND_URL", "*")  # Production frontend URL
]

# If in production, only allow specific origins
if os.getenv("ENVIRONMENT") == "production":
    allowed_origins = [origin for origin in allowed_origins if origin != "*"]
else:
    allowed_origins = ["*"]  # Allow all in development

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include tournament router
app.include_router(tournament_router)

# Include audio settings router
app.include_router(audio_settings_router)

# Include backup router
app.include_router(backup_router)

# Include achievements router
app.include_router(achievements_router)
@app.get("/")
async def root():
    """Health check endpoint for application startup"""
    return {"message": "QuizClash API is running!", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    """Fast health check endpoint to warm up the server"""
    return {"status": "healthy", "cache_entries": len(question_cache)}

@app.get("/warm-up")
async def warm_up_server(db: Session = Depends(get_db)):
    """Endpoint to warm up the server and database connections"""
    try:
        # Quick database query to warm up connection
        subject_count = db.query(Subject).count()
        return {
            "status": "warmed",
            "subjects": subject_count,
            "cache_entries": len(question_cache)
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Create tables on startup
@app.on_event("startup")
async def startup_event():
    create_tables()
    # Create default admin user if not exists
    db = next(get_db())
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
    db.close()


# Authentication endpoints
@app.post("/auth/register", response_model=APIResponse)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user"""
    # Check if user already exists
    existing_user = db.query(User).filter(
        (User.username == user_data.username) | (User.email == user_data.email)
    ).first()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered"
        )
    
    # Create new user
    hashed_password = get_password_hash(user_data.password)
    db_user = User(
        username=user_data.username,
        email=user_data.email,
        password_hash=hashed_password,
        role=user_data.role
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return APIResponse(
        success=True,
        message="User registered successfully",
        data={"user_id": db_user.id, "username": db_user.username}
    )


# Bulk upload endpoint
@app.post("/admin/questions/bulk")
async def bulk_upload_questions(
    upload_data: dict,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Bulk upload questions from file data"""
    questions = upload_data.get("questions", [])
    skip_duplicates = upload_data.get("skip_duplicates", True)
    validate_data = upload_data.get("validate_data", True)
    
    success_count = 0
    error_count = 0
    errors = []
    
    for i, question_data in enumerate(questions):
        try:
            # Validate required fields
            if validate_data:
                required_fields = ["text", "options", "correct_answer", "topic_id"]
                missing_fields = [field for field in required_fields if field not in question_data]
                if missing_fields:
                    error_count += 1
                    errors.append(f"Question {i+1}: Missing fields: {', '.join(missing_fields)}")
                    continue
            
            # Check for duplicates if enabled
            if skip_duplicates:
                existing = db.query(Question).filter(Question.text == question_data["text"]).first()
                if existing:
                    continue  # Skip duplicate
            
            # Verify topic exists
            topic = db.query(Topic).filter(Topic.id == question_data["topic_id"]).first()
            if not topic:
                error_count += 1
                errors.append(f"Question {i+1}: Invalid topic_id: {question_data['topic_id']}")
                continue
            
            # Create question
            db_question = Question(
                text=question_data["text"],
                options=question_data["options"],
                correct_answer=question_data["correct_answer"],
                difficulty=question_data.get("difficulty", "easy"),
                topic_id=question_data["topic_id"],
                subject_id=topic.subject_id,  # Auto-set from topic
                explanation=question_data.get("explanation")
            )
            
            db.add(db_question)
            success_count += 1
            
        except Exception as e:
            error_count += 1
            errors.append(f"Question {i+1}: {str(e)}")
            continue
    
    # Commit all successful questions
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        return {"success_count": 0, "error_count": len(questions), "errors": [f"Database error: {str(e)}"]}
    
    return {
        "success_count": success_count,
        "error_count": error_count,
        "errors": errors[:10]  # Return first 10 errors only
    }


# Admin endpoints
@app.get("/admin/users", response_model=List[UserResponse])
async def get_all_users(
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Get all users (admin only)"""
    users = db.query(User).all()
    
    # Fix any null values with proper defaults
    for user in users:
        if user.role is None:
            user.role = "user"
        if user.is_active is None:
            user.is_active = True
        if user.total_score is None:
            user.total_score = 0
        if user.games_played is None:
            user.games_played = 0
        if user.achievements_count is None:
            user.achievements_count = 0
    
    # Commit the fixes to database
    db.commit()
    
    return users


@app.post("/admin/users", response_model=UserResponse)
async def create_user_admin(
    user_data: UserCreate,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Create a new user (admin only)"""
    # Check if user already exists
    if db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    if db.query(User).filter(User.username == user_data.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")
    
    # Create new user
    db_user = User(
        username=user_data.username,
        email=user_data.email,
        password_hash=get_password_hash(user_data.password),
        role=getattr(user_data, 'role', 'user')
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return db_user


@app.put("/admin/users/{user_id}", response_model=UserResponse)
async def update_user_admin(
    user_id: int,
    user_data: UserUpdate,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Update user (admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check for duplicate username/email (excluding current user)
    if db.query(User).filter(User.email == user_data.email, User.id != user_id).first():
        raise HTTPException(status_code=400, detail="Email already in use")
    if db.query(User).filter(User.username == user_data.username, User.id != user_id).first():
        raise HTTPException(status_code=400, detail="Username already in use")
    
    # Update user fields
    user.username = user_data.username
    user.email = user_data.email
    user.role = user_data.role
    
    db.commit()
    db.refresh(user)
    
    return user


@app.patch("/admin/users/{user_id}/status")
async def update_user_status(
    user_id: int,
    status_data: UserStatusUpdate,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Update user active status (admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_active = status_data.is_active
    db.commit()
    
    return {"message": f"User {'activated' if status_data.is_active else 'deactivated'} successfully"}


# Admin Questions endpoints
@app.get("/admin/questions")
async def get_all_questions(
    subject_id: Optional[int] = None,
    topic_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 50,
    limit: Optional[int] = None,
    search: Optional[str] = None,
    difficulty: Optional[str] = None,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Get questions with pagination and optional filtering (admin only)"""
    # Use page_size if provided, otherwise fall back to limit
    actual_limit = page_size if page_size else (limit if limit else 50)
    
    query = db.query(Question).join(Topic).join(Subject)
    
    if subject_id:
        query = query.filter(Subject.id == subject_id)
    if topic_id:
        query = query.filter(Topic.id == topic_id)
    if search:
        query = query.filter(Question.text.ilike(f"%{search}%"))
    if difficulty:
        query = query.filter(Question.difficulty == difficulty)
    
    # Get total count for pagination
    total_count = query.count()
    
    # Apply pagination
    offset = (page - 1) * actual_limit
    questions = query.offset(offset).limit(actual_limit).all()
    
    # Format response with subject and topic names + multimedia fields
    result = []
    for q in questions:
        result.append({
            "id": q.id,
            "text": q.text,
            "options": q.options if isinstance(q.options, list) else [],
            "correct_answer": q.correct_answer,
            "difficulty": q.difficulty,
            "explanation": q.explanation,
            "topic_id": q.topic_id,
            "topic_name": q.topic.name,
            "subject_id": q.topic.subject.id,  # FIXED: Added missing subject_id
            "subject_name": q.topic.subject.name,
            "times_asked": q.times_asked,
            "times_correct": q.times_correct,
            # FIXED: Added missing multimedia fields
            "media_type": getattr(q, 'media_type', 'text'),
            "media_url": getattr(q, 'media_url', None),
            "media_metadata": getattr(q, 'media_metadata', None)
        })
    
    return {
        "questions": result,
        "total_count": total_count,
        "page": page,
        "page_size": actual_limit,
        "total_pages": (total_count + actual_limit - 1) // actual_limit
    }


@app.post("/admin/questions", response_model=QuestionResponse)
async def create_question_admin(
    question_data: QuestionCreate,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Create a new question (admin only)"""
    # Verify topic exists
    topic = db.query(Topic).filter(Topic.id == question_data.topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    # Create new question
    db_question = Question(
        text=question_data.text,
        topic_id=question_data.topic_id,
        subject_id=topic.subject_id,  # Set subject_id from topic
        options=question_data.options,
        correct_answer=question_data.correct_answer,
        difficulty=question_data.difficulty,
        explanation=question_data.explanation,
        media_type=question_data.media_type,
        media_url=question_data.media_url,
        media_metadata=question_data.media_metadata
    )
    
    db.add(db_question)
    db.commit()
    db.refresh(db_question)
    
    return db_question


@app.put("/admin/questions/{question_id}", response_model=QuestionResponse)
async def update_question_admin(
    question_id: int,
    question_data: QuestionUpdate,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Update question (admin only)"""
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    # Verify topic exists if topic_id is being updated
    if question_data.topic_id is not None:
        topic = db.query(Topic).filter(Topic.id == question_data.topic_id).first()
        if not topic:
            raise HTTPException(status_code=404, detail="Topic not found")
    
    # Update question fields
    if question_data.text is not None:
        question.text = question_data.text
    if question_data.topic_id is not None:
        question.topic_id = question_data.topic_id
        # Update subject_id when topic changes
        topic = db.query(Topic).filter(Topic.id == question_data.topic_id).first()
        if topic:
            question.subject_id = topic.subject_id
    if question_data.options is not None:
        question.options = question_data.options
    if question_data.correct_answer is not None:
        question.correct_answer = question_data.correct_answer
    if question_data.difficulty is not None:
        question.difficulty = question_data.difficulty
    if question_data.explanation is not None:
        question.explanation = question_data.explanation
    if question_data.media_type is not None:
        question.media_type = question_data.media_type
    if question_data.media_url is not None:
        question.media_url = question_data.media_url
    if question_data.media_metadata is not None:
        question.media_metadata = question_data.media_metadata
    
    db.commit()
    db.refresh(question)
    
    return question


@app.delete("/admin/questions/{question_id}")
async def delete_question(
    question_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Delete question (admin only)"""
    try:
        print(f"DEBUG: Attempting to delete question {question_id}")
        
        question = db.query(Question).filter(Question.id == question_id).first()
        if not question:
            print(f"DEBUG: Question {question_id} not found")
            raise HTTPException(status_code=404, detail="Question not found")
        
        print(f"DEBUG: Found question {question_id}: {question.text[:50]}...")
        
        # First, delete all related records to maintain referential integrity
        print(f"DEBUG: Starting foreign key cleanup for question {question_id}")
        
        # 1. Delete game_answers records
        game_answers_count = db.query(GameAnswer).filter(GameAnswer.question_id == question_id).count()
        print(f"DEBUG: Found {game_answers_count} game_answers for question {question_id}")
        
        if game_answers_count > 0:
            deleted_count = db.query(GameAnswer).filter(GameAnswer.question_id == question_id).delete()
            print(f"DEBUG: Deleted {deleted_count} game_answers records")
        
        # 2. Delete tournament_answers records
        try:
            from backend.tournament_models import TournamentAnswer
            tournament_answers_count = db.query(TournamentAnswer).filter(TournamentAnswer.question_id == question_id).count()
            print(f"DEBUG: Found {tournament_answers_count} tournament_answers for question {question_id}")
            
            if tournament_answers_count > 0:
                deleted_count = db.query(TournamentAnswer).filter(TournamentAnswer.question_id == question_id).delete()
                print(f"DEBUG: Deleted {deleted_count} tournament_answers records")
        except Exception as e:
            print(f"DEBUG: Could not clean tournament_answers: {e}")
        
        # 3. Delete tournament_questions association records
        try:
            from sqlalchemy import text
            tournament_questions_count = db.execute(
                text("SELECT COUNT(*) FROM tournament_questions WHERE question_id = :question_id"),
                {"question_id": question_id}
            ).scalar()
            print(f"DEBUG: Found {tournament_questions_count} tournament_questions associations for question {question_id}")
            
            if tournament_questions_count > 0:
                db.execute(
                    text("DELETE FROM tournament_questions WHERE question_id = :question_id"),
                    {"question_id": question_id}
                )
                print(f"DEBUG: Deleted tournament_questions associations")
        except Exception as e:
            print(f"DEBUG: Could not clean tournament_questions associations: {e}")
        
        print(f"DEBUG: Foreign key cleanup completed for question {question_id}")
        
        # Now safely delete the question
        print(f"DEBUG: Deleting question {question_id}")
        db.delete(question)
        db.commit()
        print(f"DEBUG: Successfully deleted question {question_id}")
        
        return {"message": f"Question deleted successfully (cleaned up {game_answers_count} related game answers)"}
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        print(f"ERROR: Failed to delete question {question_id}: {str(e)}")
        print(f"ERROR: Exception type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# Admin Topics and Subjects endpoints
@app.get("/admin/topics")
async def get_all_topics(
    subject_id: Optional[int] = None,
    page: int = 1,
    limit: int = 1000,
    search: Optional[str] = None,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Get topics with pagination and optional filtering (admin only)"""
    query = db.query(Topic).join(Subject)
    
    if subject_id:
        query = query.filter(Subject.id == subject_id)
    if search:
        query = query.filter(Topic.name.ilike(f"%{search}%"))
    
    # Get total count for pagination
    total_count = query.count()
    
    # Apply pagination
    offset = (page - 1) * limit
    topics = query.offset(offset).limit(limit).all()
    
    # Format response with subject names and complete data
    result = []
    for topic in topics:
        # Calculate actual question count from database instead of using stored field
        actual_question_count = db.query(Question).filter(Question.topic_id == topic.id).count()
        
        result.append({
            "id": topic.id,
            "name": topic.name,
            "description": topic.description,
            "subject_id": topic.subject_id,
            "subject_name": topic.subject.name,
            "question_count": actual_question_count,  # Use actual count from database
            "is_active": topic.is_active,
            "created_at": topic.created_at.isoformat() if topic.created_at else None
        })
    
    return {
        "topics": result,
        "total_count": total_count,
        "page": page,
        "limit": limit,
        "total_pages": (total_count + limit - 1) // limit
    }


@app.post("/admin/subjects", response_model=SubjectResponse)
async def create_subject_admin(
    subject_data: SubjectCreate,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Create a new subject (admin only)"""
    # Check if subject name already exists
    if db.query(Subject).filter(Subject.name == subject_data.name).first():
        raise HTTPException(status_code=400, detail="Subject name already exists")
    
    db_subject = Subject(
        name=subject_data.name,
        description=subject_data.description,
        icon=subject_data.icon,
        created_by=current_user.id
    )
    
    db.add(db_subject)
    db.commit()
    db.refresh(db_subject)
    
    return db_subject


@app.put("/admin/subjects/{subject_id}", response_model=SubjectResponse)
async def update_subject_admin(
    subject_id: int,
    subject_data: SubjectUpdate,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Update subject (admin only)"""
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    # Check for duplicate name (excluding current subject)
    if db.query(Subject).filter(Subject.name == subject_data.name, Subject.id != subject_id).first():
        raise HTTPException(status_code=400, detail="Subject name already exists")
    
    subject.name = subject_data.name
    subject.description = subject_data.description
    subject.icon = subject_data.icon
    
    db.commit()
    db.refresh(subject)
    
    return subject


@app.delete("/admin/subjects/{subject_id}")
async def delete_subject_admin(
    subject_id: int,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Delete subject and all associated topics/questions (admin only)"""
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    # Delete all questions in topics of this subject
    topics = db.query(Topic).filter(Topic.subject_id == subject_id).all()
    for topic in topics:
        db.query(Question).filter(Question.topic_id == topic.id).delete()
    
    # Delete all topics of this subject
    db.query(Topic).filter(Topic.subject_id == subject_id).delete()
    
    # Delete the subject
    db.delete(subject)
    db.commit()
    
    return {"message": "Subject and all associated data deleted successfully"}


@app.post("/admin/topics", response_model=TopicResponse)
async def create_topic_admin(
    topic_data: TopicCreate,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Create a new topic (admin only)"""
    # Verify subject exists
    subject = db.query(Subject).filter(Subject.id == topic_data.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    # Check if topic name already exists in this subject
    if db.query(Topic).filter(Topic.name == topic_data.name, Topic.subject_id == topic_data.subject_id).first():
        raise HTTPException(status_code=400, detail="Topic name already exists in this subject")
    
    db_topic = Topic(
        name=topic_data.name,
        subject_id=topic_data.subject_id,
        description=topic_data.description
    )
    
    db.add(db_topic)
    db.commit()
    db.refresh(db_topic)
    
    return db_topic


@app.put("/admin/topics/{topic_id}", response_model=TopicResponse)
async def update_topic_admin(
    topic_id: int,
    topic_data: TopicUpdate,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Update topic (admin only)"""
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    # Verify subject exists
    subject = db.query(Subject).filter(Subject.id == topic_data.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    # Check for duplicate name in the same subject (excluding current topic)
    if db.query(Topic).filter(
        Topic.name == topic_data.name, 
        Topic.subject_id == topic_data.subject_id,
        Topic.id != topic_id
    ).first():
        raise HTTPException(status_code=400, detail="Topic name already exists in this subject")
    
    topic.name = topic_data.name
    topic.subject_id = topic_data.subject_id
    topic.description = topic_data.description
    
    db.commit()
    db.refresh(topic)
    
    return topic


@app.delete("/admin/topics/{topic_id}")
async def delete_topic_admin(
    topic_id: int,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Delete topic and all associated questions (admin only)"""
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    # Delete all questions in this topic
    db.query(Question).filter(Question.topic_id == topic_id).delete()
    
    # Delete the topic
    db.delete(topic)
    db.commit()
    
    return {"message": "Topic and all associated questions deleted successfully"}


@app.post("/auth/login", response_model=Token)
async def login(user_credentials: UserLogin, db: Session = Depends(get_db)):
    """Authenticate user and return access token"""
    user = authenticate_user(db, user_credentials.username, user_credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if user account is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Please contact an administrator for assistance.",
        )
    
    # Update last login
    user.last_login = datetime.utcnow()
    db.commit()
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse.from_orm(user)
    )


@app.get("/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """Get current user information"""
    return UserResponse.from_orm(current_user)


# Subject endpoints
@app.post("/subjects", response_model=SubjectResponse)
async def create_subject(
    subject_data: SubjectCreate,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Create a new subject (admin only)"""
    db_subject = Subject(**subject_data.dict(), created_by=current_user.id)
    db.add(db_subject)
    db.commit()
    db.refresh(db_subject)
    return SubjectResponse.from_orm(db_subject)


@app.get("/subjects/list", response_model=List[SubjectResponse])
async def get_subjects_list(
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get all subjects with optional search (for admin panel)"""
    query = db.query(Subject).filter(Subject.is_active == True)
    
    if search:
        query = query.filter(Subject.name.contains(search))
    
    subjects = query.offset(skip).limit(limit).all()
    return [SubjectResponse.from_orm(subject) for subject in subjects]


@app.get("/subjects/{subject_id}", response_model=SubjectResponse)
async def get_subject(subject_id: int, db: Session = Depends(get_db)):
    """Get a specific subject by ID"""
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return SubjectResponse.from_orm(subject)


@app.put("/subjects/{subject_id}", response_model=SubjectResponse)
async def update_subject(
    subject_id: int,
    subject_data: SubjectUpdate,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Update a subject (admin only)"""
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    for field, value in subject_data.dict(exclude_unset=True).items():
        setattr(subject, field, value)
    
    db.commit()
    db.refresh(subject)
    return SubjectResponse.from_orm(subject)


@app.delete("/subjects/{subject_id}")
async def delete_subject(
    subject_id: int,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Delete a subject (admin only)"""
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    db.delete(subject)
    db.commit()
    return APIResponse(success=True, message="Subject deleted successfully")


# Topic endpoints
@app.post("/topics", response_model=TopicResponse)
async def create_topic(
    topic_data: TopicCreate,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Create a new topic (admin only)"""
    # Verify subject exists
    subject = db.query(Subject).filter(Subject.id == topic_data.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    db_topic = Topic(**topic_data.dict())
    db.add(db_topic)
    db.commit()
    db.refresh(db_topic)
    return TopicResponse.from_orm(db_topic)


@app.get("/topics", response_model=List[TopicResponse])
async def get_topics(
    subject_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get topics, optionally filtered by subject"""
    query = db.query(Topic).filter(Topic.is_active == True)
    
    if subject_id:
        query = query.filter(Topic.subject_id == subject_id)
    
    topics = query.offset(skip).limit(limit).all()
    return [TopicResponse.from_orm(topic) for topic in topics]


# Question endpoints
@app.post("/questions", response_model=QuestionResponse)
async def create_question(
    question_data: QuestionCreate,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Create a new question (admin only)"""
    # Verify topic exists
    topic = db.query(Topic).filter(Topic.id == question_data.topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    db_question = Question(**question_data.dict())
    db.add(db_question)
    
    # Update topic question count
    topic.question_count += 1
    
    db.commit()
    db.refresh(db_question)
    return QuestionResponse.from_orm(db_question)


@app.patch("/questions/{question_id}")
async def update_question_media(
    question_id: int,
    media_data: dict,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Update question media information (admin only)"""
    db_question = db.query(Question).filter(Question.id == question_id).first()
    if not db_question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    # Update media fields
    if "media_url" in media_data:
        db_question.media_url = media_data["media_url"]
    if "media_metadata" in media_data:
        db_question.media_metadata = json.dumps(media_data["media_metadata"])
    
    db.commit()
    db.refresh(db_question)
    return {"message": "Question media updated successfully", "id": question_id}


@app.get("/questions", response_model=List[QuestionResponse])
async def get_questions(
    topic_id: Optional[int] = None,
    topic_ids: Optional[str] = None,
    subject_id: Optional[int] = None,
    difficulty: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get questions with optional filters"""
    query = db.query(Question)
    
    # Handle filtering logic - topic_ids takes precedence over subject_id
    try:
        if topic_ids:
            try:
                topic_id_list = [int(tid.strip()) for tid in topic_ids.split(',') if tid.strip()]
                if topic_id_list:
                    query = query.filter(Question.topic_id.in_(topic_id_list))
                    print(f"DEBUG Backend: Filtering by topic_ids: {topic_id_list}")
            except ValueError as e:
                print(f"DEBUG Backend: Invalid topic_ids format: {e}")
                raise HTTPException(status_code=400, detail="Invalid topic_ids format")
        elif topic_id:
            query = query.filter(Question.topic_id == topic_id)
            print(f"DEBUG Backend: Filtering by single topic_id: {topic_id}")
        elif subject_id:
            # Only filter by subject_id if no topic filters are applied
            try:
                # Use subquery to avoid join issues
                topic_ids_for_subject = db.query(Topic.id).filter(Topic.subject_id == subject_id).all()
                fallback_topic_list = [t[0] for t in topic_ids_for_subject]
                if fallback_topic_list:
                    query = query.filter(Question.topic_id.in_(fallback_topic_list))
                print(f"DEBUG Backend: Filtering by subject_id using subquery: {subject_id}")
            except Exception as e:
                print(f"DEBUG Backend: Query error: {e}")
                raise HTTPException(status_code=500, detail="Unable to filter questions by subject")
    except Exception as e:
        print(f"DEBUG Backend: Unexpected filtering error: {e}")
        raise HTTPException(status_code=500, detail=f"Question filtering error: {str(e)}")
    
    # Debug logging
    print(f"DEBUG Backend: topic_ids={topic_ids}, subject_id={subject_id}")
    print(f"DEBUG Backend: Final query filters applied")
    
    if difficulty:
        query = query.filter(Question.difficulty == difficulty)
    
    try:
        questions = query.offset(skip).limit(limit).all()
        print(f"DEBUG Backend: Found {len(questions)} questions")
        
        # Filter out corrupted questions and convert to response format
        valid_questions = []
        corrupted_count = 0
        
        for question in questions:
            try:
                # Validate question data before creating response
                if (isinstance(question.options, list) and 
                    isinstance(question.correct_answer, int) and 
                    0 <= question.correct_answer < len(question.options)):
                    valid_questions.append(QuestionResponse.from_orm(question))
                else:
                    corrupted_count += 1
                    print(f"DEBUG Backend: Skipping corrupted question {question.id}: options={type(question.options)}, correct_answer={type(question.correct_answer)}")
            except Exception as e:
                corrupted_count += 1
                print(f"DEBUG Backend: Skipping invalid question {question.id}: {e}")
        
        if corrupted_count > 0:
            print(f"DEBUG Backend: Skipped {corrupted_count} corrupted questions")
        
        return valid_questions
    except Exception as e:
        print(f"DEBUG Backend: Query execution error: {e}")
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")


# Game session endpoints
@app.post("/game/start", response_model=GameSessionResponse)
async def start_game(
    game_data: GameSessionCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Start a new game session"""
    # Verify subject exists
    subject = db.query(Subject).filter(Subject.id == game_data.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    # Create game session without topic_ids (not a field in GameSession model)
    session_data = game_data.dict()
    topic_ids = session_data.pop('topic_ids', None)  # Remove topic_ids from dict
    
    db_session = GameSession(
        user_id=current_user.id,
        **session_data
    )
    
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return GameSessionResponse.from_orm(db_session)


@app.get("/game/{session_id}/questions")
async def get_game_questions(
    session_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get questions for a game session"""
    session = db.query(GameSession).filter(
        GameSession.id == session_id,
        GameSession.user_id == current_user.id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Game session not found")
    
    # Get random questions from the subject
    questions = db.query(Question).join(Topic).filter(
        Topic.subject_id == session.subject_id,
        Question.difficulty == session.difficulty
    ).order_by(func.random()).limit(session.total_questions).all()
    
    # Check if we have enough questions
    if not questions:
        raise HTTPException(status_code=404, detail="No questions found for this subject and difficulty")
    
    # Return questions without correct answers for security
    return [
        {
            "id": q.id,
            "text": q.text,
            "options": q.options if isinstance(q.options, list) else [],
            "difficulty": q.difficulty
        }
        for q in questions
    ]


@app.post("/game/{session_id}/answer")
async def submit_answer(
    session_id: int,
    answer_data: GameAnswerCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Submit an answer for a question in a game session"""
    session = db.query(GameSession).filter(
        GameSession.id == session_id,
        GameSession.user_id == current_user.id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Game session not found")
    
    question = db.query(Question).filter(Question.id == answer_data.question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    # Check if answer is correct
    is_correct = answer_data.selected_answer == question.correct_answer
    points_earned = 10 if is_correct else 0
    
    # Create game answer record
    db_answer = GameAnswer(
        game_session_id=session_id,
        question_id=answer_data.question_id,
        selected_answer=answer_data.selected_answer,
        is_correct=is_correct,
        time_taken=answer_data.time_taken,
        points_earned=points_earned
    )
    
    db.add(db_answer)
    
    # Update session stats
    session.questions_answered += 1
    session.total_score += points_earned
    if is_correct:
        session.correct_answers += 1
    
    # Update question stats
    question.times_asked += 1
    if is_correct:
        question.times_correct += 1
    
    db.commit()
    
    return {
        "is_correct": is_correct,
        "correct_answer": question.correct_answer,
        "points_earned": points_earned,
        "explanation": question.explanation
    }


# Leaderboard endpoints
@app.get("/leaderboard", response_model=List[dict])
async def get_leaderboard(
    category: Optional[str] = None,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """Get leaderboard entries with optional subject filtering"""
    try:
        if category and category != "All":
            # Get subject-specific leaderboard
            subject = db.query(Subject).filter(Subject.name == category).first()
            if not subject:
                # If subject not found, return overall leaderboard
                return await get_overall_leaderboard(limit, db)
            
            # Calculate subject-specific scores from game sessions
            # Join with Subject table to filter by subject name
            user_scores = db.query(
                User.id,
                User.username,
                func.sum(GameSession.total_score).label('total_score'),
                func.count(GameSession.id).label('games_played'),
                User.achievements_count
            ).join(
                GameSession, User.id == GameSession.user_id
            ).join(
                Subject, GameSession.subject_id == Subject.id
            ).filter(
                Subject.name == category
            ).group_by(
                User.id, User.username, User.achievements_count
            ).order_by(
                func.sum(GameSession.total_score).desc()
            ).limit(limit).all()
            
            return [
                {
                    "rank": idx + 1,
                    "username": user.username,
                    "total_score": int(user.total_score or 0),
                    "games_played": int(user.games_played or 0),
                    "achievements_count": user.achievements_count or 0
                }
                for idx, user in enumerate(user_scores)
            ]
        else:
            # Overall leaderboard
            return await get_overall_leaderboard(limit, db)
            
    except Exception as e:
        print(f"Error in leaderboard: {e}")
        return await get_overall_leaderboard(limit, db)

async def get_overall_leaderboard(limit: int, db: Session):
    """Get overall leaderboard based on total scores"""
    users = db.query(User).order_by(User.total_score.desc()).limit(limit).all()
    
    return [
        {
            "rank": idx + 1,
            "username": user.username,
            "total_score": user.total_score or 0,
            "games_played": user.games_played or 0,
            "achievements_count": user.achievements_count or 0
        }
        for idx, user in enumerate(users)
    ]


# User stats endpoint
@app.get("/users/{user_id}/stats", response_model=UserStats)
async def get_user_stats(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get detailed user statistics"""
    # Users can only view their own stats unless they're admin
    if current_user.id != user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Calculate additional stats
    sessions = db.query(GameSession).filter(GameSession.user_id == user_id).all()
    total_questions = sum(s.questions_answered for s in sessions)
    total_correct = sum(s.correct_answers for s in sessions)
    
    # Calculate favorite subject
    favorite_subject = None
    if sessions:
        subject_counts = {}
        for session in sessions:
            if session.subject_id:
                # Get subject name from database
                subject = db.query(Subject).filter(Subject.id == session.subject_id).first()
                if subject:
                    subject_name = subject.name
                    subject_counts[subject_name] = subject_counts.get(subject_name, 0) + 1
        if subject_counts:
            favorite_subject = max(subject_counts, key=subject_counts.get)
    
    return UserStats(
        total_games=user.games_played,
        total_score=user.total_score,
        average_score=user.total_score / max(user.games_played, 1),
        best_score=max([s.total_score for s in sessions] + [0]),
        total_correct=total_correct,
        total_questions=total_questions,
        overall_accuracy=total_correct / max(total_questions, 1) * 100,
        favorite_subject=favorite_subject,
        achievements_count=user.achievements_count,
        current_streak=0,  # TODO: Implement streak calculation
        best_streak=0  # TODO: Implement streak calculation
    )

@app.get("/users/{user_id}/activity")
async def get_user_activity(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get user activity timeline (admin only or own activity)"""
    # Check if user is admin or requesting their own activity
    if current_user.role != "admin" and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    activities = []
    
    # Get recent game sessions
    recent_sessions = db.query(GameSession).filter(
        GameSession.user_id == user_id
    ).order_by(GameSession.started_at.desc()).limit(10).all()
    
    for session in recent_sessions:
        # Get subject name
        subject_name = "Unknown Subject"
        if session.subject_id:
            subject = db.query(Subject).filter(Subject.id == session.subject_id).first()
            if subject:
                subject_name = subject.name
        
        activities.append({
            "type": "game_session",
            "description": f"Played {subject_name} quiz",
            "details": f"Score: {session.total_score}, Mode: {session.mode}",
            "timestamp": session.started_at.isoformat(),
            "icon": "🎮",
            "color": "#3498db"
        })
    
    # Get recent tournament participations
    from backend.tournament_models import TournamentParticipant, Tournament
    recent_tournaments = db.query(TournamentParticipant, Tournament).join(
        Tournament, TournamentParticipant.tournament_id == Tournament.id
    ).filter(
        TournamentParticipant.user_id == user_id
    ).order_by(TournamentParticipant.registered_at.desc()).limit(5).all()
    
    for participant, tournament in recent_tournaments:
        if participant.has_played:
            activities.append({
                "type": "tournament_completed",
                "description": f"Completed tournament: {tournament.title}",
                "details": f"Score: {participant.score or 0}, Rank: {participant.rank or 'N/A'}",
                "timestamp": participant.registered_at.isoformat(),
                "icon": "🏆",
                "color": "#f39c12"
            })
        else:
            activities.append({
                "type": "tournament_joined",
                "description": f"Joined tournament: {tournament.title}",
                "details": f"Subject: {tournament.subject}",
                "timestamp": participant.registered_at.isoformat(),
                "icon": "📝",
                "color": "#9b59b6"
            })
    
    # Add account creation
    activities.append({
        "type": "account_created",
        "description": "Account created",
        "details": f"Role: {user.role}",
        "timestamp": user.created_at.isoformat() if user.created_at else None,
        "icon": "👤",
        "color": "#27ae60"
    })
    
    # Sort activities by timestamp (most recent first)
    activities.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    
    return activities[:10]  # Return top 10 most recent activities

@app.get("/users/me")
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information"""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role,
        "is_active": current_user.is_active,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        "games_played": current_user.games_played or 0,
        "total_score": current_user.total_score or 0,
        "achievements_count": current_user.achievements_count or 0,
        "level": current_user.level or 1
    }

# User Profile Update Models
class UserProfileUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    current_password: str
    new_password: Optional[str] = None

class PasswordResetRequest(BaseModel):
    current_password: str
    new_password: str

@app.put("/users/me")
async def update_user_profile(
    profile_data: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update user profile"""
    try:
        # Verify current password
        if not verify_password(profile_data.current_password, current_user.password_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        
        # Check if username is already taken (if changing username)
        if profile_data.username and profile_data.username != current_user.username:
            existing_user = db.query(User).filter(User.username == profile_data.username).first()
            if existing_user:
                raise HTTPException(status_code=400, detail="Username already taken")
        
        # Check if email is already taken (if changing email)
        if profile_data.email and profile_data.email != current_user.email:
            existing_user = db.query(User).filter(User.email == profile_data.email).first()
            if existing_user:
                raise HTTPException(status_code=400, detail="Email already taken")
        
        # Update user fields
        if profile_data.username:
            current_user.username = profile_data.username
        
        if profile_data.email:
            current_user.email = profile_data.email
        
        # Update password if provided
        if profile_data.new_password:
            if len(profile_data.new_password) < 6:
                raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
            current_user.password_hash = get_password_hash(profile_data.new_password)
        
        # Save changes
        db.commit()
        db.refresh(current_user)
        
        # Return updated user data
        return {
            "id": current_user.id,
            "username": current_user.username,
            "email": current_user.email,
            "role": current_user.role,
            "is_active": current_user.is_active,
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"ERROR: Failed to update user profile: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update profile: {str(e)}")

@app.put("/users/me/password")
async def reset_user_password(
    password_data: PasswordResetRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reset user password"""
    try:
        # Verify current password
        if not verify_password(password_data.current_password, current_user.password_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        
        # Validate new password
        if len(password_data.new_password) < 6:
            raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
        
        # Update password
        current_user.password_hash = get_password_hash(password_data.new_password)
        
        # Save changes
        db.commit()
        
        return {"message": "Password reset successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"ERROR: Failed to reset password: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reset password: {str(e)}")

@app.get("/users/stats")
async def get_user_stats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get user statistics"""
    try:
        print(f"DEBUG: Fetching stats for user {current_user.id}")
        
        # Calculate stats from game sessions (more accurate than user table)
        game_sessions = db.query(GameSession).filter(GameSession.user_id == current_user.id).all()
        
        if game_sessions:
            scores = [session.total_score for session in game_sessions if session.total_score is not None]
            correct_answers = sum(session.correct_answers for session in game_sessions if session.correct_answers is not None)
            total_questions = sum(session.total_questions for session in game_sessions if session.total_questions is not None)
            
            user_stats = {
                "games_played": len(game_sessions),
                "total_score": sum(scores) if scores else 0,
                "best_score": max(scores) if scores else 0,
                "games_won": sum(1 for session in game_sessions if session.total_score and session.total_score > 0),
                "win_rate": (correct_answers / total_questions * 100) if total_questions > 0 else 0.0,
                "avg_score": sum(scores) / len(scores) if scores else 0,
                "achievements_count": current_user.achievements_count or 0,
                "level": current_user.level or 1
            }
        else:
            user_stats = {
                "games_played": 0,
                "total_score": 0,
                "best_score": 0,
                "games_won": 0,
                "win_rate": 0.0,
                "avg_score": 0,
                "achievements_count": 0,
                "level": current_user.level or 1
            }
        
        print(f"DEBUG: Returning user stats: {user_stats}")
        return user_stats
        
    except Exception as e:
        print(f"ERROR: Failed to get user stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get user stats: {str(e)}")

class PointDeductionRequest(BaseModel):
    points_to_deduct: int

@app.patch("/users/{user_id}/points")
async def deduct_user_points(
    user_id: int,
    point_data: PointDeductionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Deduct points from user for powerup purchases"""
    try:
        # Verify user can only deduct their own points or admin can deduct any
        if current_user.id != user_id and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Not authorized to modify this user's points")
        
        # Get user
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Calculate current total score from game sessions
        sessions = db.query(GameSession).filter(GameSession.user_id == user_id).all()
        current_total = sum([s.total_score for s in sessions if s.total_score is not None])
        
        # Check if user has enough points
        if current_total < point_data.points_to_deduct:
            raise HTTPException(status_code=400, detail="Insufficient points")
        
        # For now, we'll create a negative score game session to represent the deduction
        # In a real system, you'd want a separate transactions table
        deduction_session = GameSession(
            user_id=user_id,
            subject_id=1,  # Dummy subject
            mode="powerup_purchase",  # Special mode for powerup purchases
            total_questions=0,
            questions_answered=0,
            correct_answers=0,
            total_score=-point_data.points_to_deduct,  # Negative score for deduction
            difficulty="powerup_purchase",  # Special marker
            is_completed=True,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow()
        )
        
        db.add(deduction_session)
        db.commit()
        
        # Return updated total
        new_total = current_total - point_data.points_to_deduct
        
        print(f"DEBUG: Deducted {point_data.points_to_deduct} points from user {user_id}. New total: {new_total}")
        
        return {
            "success": True,
            "points_deducted": point_data.points_to_deduct,
            "new_total": new_total
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR: Failed to deduct points: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to deduct points: {str(e)}")

class PowerupPurchaseRequest(BaseModel):
    powerup_id: str
    powerup_name: str
    price: int
    uses_remaining: int = 1

@app.post("/powerups/purchase")
async def purchase_powerup(
    purchase_data: PowerupPurchaseRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Purchase a powerup with proper database persistence"""
    try:
        # Deduct points first
        point_deduction = PointDeductionRequest(points_to_deduct=purchase_data.price)
        deduct_response = await deduct_user_points(current_user.id, point_deduction, current_user, db)
        
        if not deduct_response.get("success"):
            raise HTTPException(status_code=400, detail="Failed to deduct points")
        
        # Check if user already has this powerup
        existing_powerup = db.query(PowerupPurchase).filter(
            PowerupPurchase.user_id == current_user.id,
            PowerupPurchase.powerup_id == purchase_data.powerup_id
        ).first()
        
        if existing_powerup:
            # Add to existing powerup count
            existing_powerup.uses_remaining += purchase_data.uses_remaining
            existing_powerup.is_active = True  # Reactivate if was inactive
            existing_powerup.price_paid += purchase_data.price  # Track total spent
            powerup_purchase = existing_powerup
            print(f"DEBUG: Added {purchase_data.uses_remaining} uses to existing {purchase_data.powerup_name}")
        else:
            # Create new powerup purchase record
            powerup_purchase = PowerupPurchase(
                user_id=current_user.id,
                powerup_id=purchase_data.powerup_id,
                powerup_name=purchase_data.powerup_name,
                price_paid=purchase_data.price,
                uses_remaining=purchase_data.uses_remaining,
                is_active=True
            )
            db.add(powerup_purchase)
            print(f"DEBUG: Created new powerup purchase: {purchase_data.powerup_name}")
        
        db.commit()
        db.refresh(powerup_purchase)
        
        print(f"DEBUG: Powerup purchase saved to database: {purchase_data.powerup_name}")
        
        return {
            "success": True,
            "purchase_id": powerup_purchase.id,
            "new_total_points": deduct_response["new_total"],
            "powerup": {
                "id": powerup_purchase.powerup_id,
                "name": powerup_purchase.powerup_name,
                "uses_remaining": powerup_purchase.uses_remaining,
                "purchased_at": powerup_purchase.purchased_at.isoformat()
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR: Failed to purchase powerup: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to purchase powerup: {str(e)}")

@app.get("/powerups/user")
async def get_user_powerups(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's purchased powerups"""
    try:
        # Only ensure basic powerups if user has none (optimization)
        existing_count = db.query(PowerupPurchase).filter(
            PowerupPurchase.user_id == current_user.id
        ).count()
        
        if existing_count == 0:
            await _ensure_user_has_basic_powerups(current_user.id, db)
        
        powerups = db.query(PowerupPurchase).filter(
            PowerupPurchase.user_id == current_user.id,
            PowerupPurchase.is_active == True,
            PowerupPurchase.uses_remaining > 0
        ).all()
        
        return [{
            "id": p.powerup_id,
            "name": p.powerup_name,
            "uses_remaining": p.uses_remaining,
            "purchased_at": p.purchased_at.isoformat(),
            "is_active": p.is_active
        } for p in powerups]
        
    except Exception as e:
        print(f"ERROR: Failed to get user powerups: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get powerups: {str(e)}")

async def _ensure_user_has_basic_powerups(user_id: int, db: Session):
    """Ensure user has basic powerups for testing"""
    basic_powerups = [
        {"id": "fifty_fifty", "name": "🎯 50/50", "uses": 3},
        {"id": "extra_time", "name": "⏱️ Extra Time", "uses": 2},
        {"id": "hint_master", "name": "💡 Hint Master", "uses": 2},
        {"id": "score_boost", "name": "🎯 Score Boost", "uses": 2},
        {"id": "double_points", "name": "⭐ Double Points", "uses": 2},
        {"id": "time_freeze", "name": "❄️ Time Freeze", "uses": 2},
        {"id": "lucky_charm", "name": "🍀 Lucky Charm", "uses": 2},
        {"id": "quiz_god", "name": "⚡ Quiz God", "uses": 1}
    ]
    
    for powerup in basic_powerups:
        # Check if user already has this powerup
        existing = db.query(PowerupPurchase).filter(
            PowerupPurchase.user_id == user_id,
            PowerupPurchase.powerup_id == powerup["id"]
        ).first()
        
        if not existing:
            # Create new powerup entry
            new_powerup = PowerupPurchase(
                user_id=user_id,
                powerup_id=powerup["id"],
                powerup_name=powerup["name"],
                price_paid=0,  # Free for testing
                uses_remaining=powerup["uses"],
                is_active=True
            )
            db.add(new_powerup)
        elif existing.uses_remaining <= 0:
            # Refill uses for testing
            existing.uses_remaining = powerup["uses"]
            existing.is_active = True
    
    db.commit()

@app.post("/powerups/{powerup_id}/use")
async def use_powerup(
    powerup_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Use one instance of a powerup"""
    try:
        # Find the powerup
        powerup = db.query(PowerupPurchase).filter(
            PowerupPurchase.user_id == current_user.id,
            PowerupPurchase.powerup_id == powerup_id,
            PowerupPurchase.is_active == True,
            PowerupPurchase.uses_remaining > 0
        ).first()
        
        if not powerup:
            raise HTTPException(status_code=404, detail="Powerup not found or no uses remaining")
        
        # Decrease uses
        powerup.uses_remaining -= 1
        
        # If no uses left, deactivate
        if powerup.uses_remaining <= 0:
            powerup.is_active = False
        
        db.commit()
        
        return {
            "message": "Powerup used successfully",
            "powerup_id": powerup_id,
            "uses_remaining": powerup.uses_remaining,
            "is_active": powerup.is_active
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR: Failed to use powerup: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to use powerup: {str(e)}")

@app.get("/users/detailed-stats")
async def get_detailed_user_stats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get detailed user statistics"""
    try:
        print(f"DEBUG: Fetching detailed stats for user {current_user.id}")
        
        # Get user's game sessions
        sessions = db.query(GameSession).filter(GameSession.user_id == current_user.id).all()
        
        if sessions:
            # Calculate detailed stats
            scores = [s.total_score for s in sessions if s.total_score is not None]
            total_correct = sum([s.correct_answers for s in sessions if s.correct_answers is not None])
            total_questions = sum([s.total_questions for s in sessions if s.total_questions is not None])
            
            detailed_stats = {
                "avg_score": sum(scores) / len(scores) if scores else 0,
                "best_score": max(scores) if scores else 0,
                "total_correct": total_correct,
                "total_questions": total_questions,
                "overall_accuracy": (total_correct / total_questions * 100) if total_questions > 0 else 0.0,
                "achievements_count": current_user.achievements_count or 0,
                "current_streak": 0,  # TODO: Implement streak calculation
                "best_streak": 0,  # TODO: Implement streak calculation
                "total_points": sum(scores) if scores else 0
            }
        else:
            detailed_stats = {
                "avg_score": 0,
                "best_score": 0,
                "total_correct": 0,
                "total_questions": 0,
                "overall_accuracy": 0.0,
                "achievements_count": 0,
                "current_streak": 0,
                "best_streak": 0,
                "total_points": 0
            }
        
        print(f"DEBUG: Returning detailed stats: {detailed_stats}")
        return detailed_stats
        
    except Exception as e:
        print(f"ERROR: Failed to get detailed stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get detailed stats: {str(e)}")

@app.get("/users/recent-games")
async def get_recent_games(
    limit: int = 10,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get recent games for current user with detailed information"""
    try:
        sessions = db.query(GameSession).filter(
            GameSession.user_id == current_user.id
        ).order_by(GameSession.completed_at.desc()).limit(limit).all()
        
        result = []
        for session in sessions:
            # Get subject name
            subject = db.query(Subject).filter(Subject.id == session.subject_id).first()
            subject_name = subject.name if subject else "Unknown"
            
            # Get topics for this session (from game answers)
            topics = db.query(Topic.name).join(
                Question, Topic.id == Question.topic_id
            ).join(
                GameAnswer, Question.id == GameAnswer.question_id
            ).filter(
                GameAnswer.game_session_id == session.id
            ).distinct().all()
            
            topic_names = [topic[0] for topic in topics] if topics else []
            
            result.append({
                "id": session.id,
                "subject": subject_name,
                "topics": topic_names,
                "total_questions": session.total_questions,
                "questions_answered": session.questions_answered,
                "score": session.total_score,
                "accuracy": round((session.correct_answers / max(session.questions_answered, 1)) * 100, 1),
                "difficulty": session.difficulty,
                "completed_at": session.completed_at.isoformat() if session.completed_at else None
            })
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching recent games: {str(e)}")

# Game Session Management endpoints
@app.post("/game-sessions")
async def create_game_session(
    session_data: dict,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a new game session"""
    try:
        # Get or create subject
        subject = db.query(Subject).filter(Subject.name == session_data.get('subject', 'General Knowledge')).first()
        if not subject:
            # Create default subject if it doesn't exist
            subject = Subject(
                name=session_data.get('subject', 'General Knowledge'),
                description=f"Questions about {session_data.get('subject', 'General Knowledge')}",
                is_active=True,
                created_by=current_user.id
            )
            db.add(subject)
            db.flush()  # Get the ID
        
        # Create game session
        game_session = GameSession(
            user_id=current_user.id,
            subject_id=subject.id,
            mode=session_data.get('mode', 'solo'),
            difficulty=session_data.get('difficulty', 'Medium'),
            total_questions=session_data.get('total_questions', 0),
            questions_answered=session_data.get('questions_answered', 0),
            correct_answers=session_data.get('correct_answers', 0),
            total_score=session_data.get('total_score', 0),
            time_spent=session_data.get('time_spent', 0),
            is_completed=session_data.get('is_completed', True),
            completed_at=datetime.utcnow() if session_data.get('is_completed', True) else None
        )
        
        db.add(game_session)
        db.commit()
        
        # Update user stats and achievements
        old_games = current_user.games_played or 0
        old_score = current_user.total_score or 0
        current_user.games_played = old_games + 1
        current_user.total_score = old_score + session_data.get('total_score', 0)
        
        # Update user level based on games played (every 5 games = 1 level)
        new_level = (current_user.games_played // 5) + 1
        old_level = current_user.level or 1
        current_user.level = new_level
        
        # Check if user leveled up
        level_up = new_level > old_level
        
        # Update achievements based on milestones
        achievements = 0
        if current_user.games_played >= 10:
            achievements += 1  # Veteran Player
        if current_user.games_played >= 50:
            achievements += 1  # Quiz Master
        if current_user.total_score >= 1000:
            achievements += 1  # High Scorer
        if current_user.total_score >= 5000:
            achievements += 1  # Score Legend
        
        current_user.achievements_count = achievements
        db.commit()
        
        print(f"DEBUG: Created game session {game_session.id} for user {current_user.username}")
        print(f"DEBUG: Updated user stats - Games: {old_games} -> {current_user.games_played}, Score: {old_score} -> {current_user.total_score}, Achievements: {achievements}")
        
        # Also update existing users' achievements retroactively
        try:
            all_users = db.query(User).all()
            for user in all_users:
                user_achievements = 0
                if (user.games_played or 0) >= 10:
                    user_achievements += 1
                if (user.games_played or 0) >= 50:
                    user_achievements += 1
                if (user.total_score or 0) >= 1000:
                    user_achievements += 1
                if (user.total_score or 0) >= 5000:
                    user_achievements += 1
                
                if user.achievements_count != user_achievements:
                    user.achievements_count = user_achievements
                    print(f"DEBUG: Updated achievements for {user.username}: {user_achievements}")
            
            db.commit()
        except Exception as e:
            print(f"WARNING: Failed to update achievements for all users: {e}")
        
        # Prepare response with level up information
        response_data = {
            "id": game_session.id, 
            "message": "Game session created successfully",
            "level_up": level_up,
            "new_level": new_level,
            "old_level": old_level,
            "games_played": current_user.games_played,
            "next_level_games": ((new_level * 5) - current_user.games_played) if current_user.games_played % 5 != 0 else 5
        }
        
        return response_data
        
    except Exception as e:
        db.rollback()
        print(f"ERROR: Failed to create game session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create game session: {str(e)}")

@app.post("/game-answers")
async def create_game_answer(
    answer_data: dict,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a game answer record"""
    try:
        # Verify the game session belongs to the current user
        session = db.query(GameSession).filter(
            GameSession.id == answer_data.get('game_session_id'),
            GameSession.user_id == current_user.id
        ).first()
        
        if not session:
            raise HTTPException(status_code=404, detail="Game session not found")
        
        # Get the question to update its statistics
        question = db.query(Question).filter(Question.id == answer_data.get('question_id')).first()
        
        # Create game answer
        game_answer = GameAnswer(
            game_session_id=answer_data.get('game_session_id'),
            question_id=answer_data.get('question_id'),
            selected_answer=answer_data.get('selected_answer'),
            is_correct=answer_data.get('is_correct', False),
            time_taken=answer_data.get('time_taken', 0),
            points_earned=answer_data.get('points_earned', 0)
        )
        
        db.add(game_answer)
        
        # Update question statistics
        if question:
            question.times_asked += 1
            if answer_data.get('is_correct', False):
                question.times_correct += 1
        
        db.commit()
        
        # Prepare response
        response_data = {
            "id": game_answer.id, 
            "message": "Game answer saved successfully",
            "game_session_id": game_answer.game_session_id,
            "question_id": game_answer.question_id,
            "is_correct": game_answer.is_correct,
            "points_earned": game_answer.points_earned
        }
        
        return response_data
        
    except Exception as e:
        db.rollback()
        print(f"ERROR: Failed to create game answer: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create game answer: {str(e)}")


# Subjects and Topics endpoints
@app.get("/subjects")
async def get_subjects(db: Session = Depends(get_db)):
    """Get all subjects with their topics and complete data"""
    subjects = db.query(Subject).filter(Subject.is_active == True).all()
    
    # Return complete subject data including description and icon
    result = []
    for subject in subjects:
        topics = db.query(Topic).filter(Topic.subject_id == subject.id).all()
        # Include question counts for each topic
        topic_list = []
        for topic in topics:
            question_count = db.query(Question).filter(Question.topic_id == topic.id).count()
            topic_list.append({
                "id": topic.id, 
                "name": topic.name,
                "question_count": question_count
            })
        
        result.append({
            "id": subject.id,
            "name": subject.name,
            "description": subject.description,
            "icon": subject.icon,
            "is_active": subject.is_active,
            "created_by": subject.created_by,
            "created_at": subject.created_at.isoformat() if subject.created_at else None,
            "topics": topic_list
        })
    
    return result

@app.get("/subjects/{subject_id}/topics")
async def get_topics_by_subject_id(subject_id: int, db: Session = Depends(get_db)):
    """Get topics for a specific subject by ID with question counts"""
    try:
        subject = db.query(Subject).filter(Subject.id == subject_id).first()
        if not subject:
            raise HTTPException(status_code=404, detail="Subject not found")
        
        topics = db.query(Topic).filter(Topic.subject_id == subject.id).all()
        
        # Add question count for each topic
        result = []
        for topic in topics:
            question_count = db.query(Question).filter(Question.topic_id == topic.id).count()
            result.append({
                "id": topic.id, 
                "name": topic.name,
                "question_count": question_count
            })
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching topics: {str(e)}")

@app.get("/subjects/{subject_name}/topics")
async def get_topics_by_subject(subject_name: str, db: Session = Depends(get_db)):
    """Get topics for a specific subject"""
    try:
        subject = db.query(Subject).filter(Subject.name == subject_name).first()
        if not subject:
            # Return sample topics if subject not found
            sample_subjects = {
                "Mathematics": [
                    {"id": 0, "name": "Algebra", "question_count": 25},
                    {"id": 0, "name": "Geometry", "question_count": 20},
                    {"id": 0, "name": "Calculus", "question_count": 15},
                    {"id": 0, "name": "Statistics", "question_count": 18},
                    {"id": 0, "name": "Trigonometry", "question_count": 12}
                ],
                "Science": [
                    {"id": 0, "name": "Physics", "question_count": 30},
                    {"id": 0, "name": "Chemistry", "question_count": 28},
                    {"id": 0, "name": "Biology", "question_count": 35},
                    {"id": 0, "name": "Earth Science", "question_count": 22},
                    {"id": 0, "name": "Astronomy", "question_count": 15}
                ],
                "History": [
                    {"id": 0, "name": "World History", "question_count": 30},
                    {"id": 0, "name": "Ancient History", "question_count": 25},
                    {"id": 0, "name": "Modern History", "question_count": 28},
                    {"id": 0, "name": "American History", "question_count": 22}
                ],
                "Literature": [
                    {"id": 0, "name": "Classic Literature", "question_count": 25},
                    {"id": 0, "name": "Modern Literature", "question_count": 20},
                    {"id": 0, "name": "Poetry", "question_count": 18},
                    {"id": 0, "name": "Drama", "question_count": 15}
                ],
                "Geography": [
                    {"id": 0, "name": "Physical Geography", "question_count": 25},
                    {"id": 0, "name": "Human Geography", "question_count": 20},
                    {"id": 0, "name": "World Capitals", "question_count": 40},
                    {"id": 0, "name": "Countries", "question_count": 35}
                ],
                "General Knowledge": [
                    {"id": 0, "name": "Current Affairs", "question_count": 30},
                    {"id": 0, "name": "Sports", "question_count": 25},
                    {"id": 0, "name": "Entertainment", "question_count": 28},
                    {"id": 0, "name": "Technology", "question_count": 22}
                ]
            }
            return sample_subjects.get(subject_name, [])
        
        topics = db.query(Topic).filter(Topic.subject_id == subject.id).all()
        
        # Add question count for each topic
        result = []
        for topic in topics:
            question_count = db.query(Question).filter(Question.topic_id == topic.id).count()
            result.append({
                "id": topic.id, 
                "name": topic.name,
                "question_count": question_count
            })
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching topics: {str(e)}")

@app.get("/topics/{topic_id}/questions")
async def get_topic_questions(topic_id: int, db: Session = Depends(get_db)):
    """Get questions for a specific topic"""
    questions = db.query(Question).filter(Question.topic_id == topic_id).all()
    return questions

@app.get("/topics/{topic_id}/questions/count")
async def get_topic_questions_count(topic_id: int, db: Session = Depends(get_db)):
    """Get count of questions for a specific topic"""
    count = db.query(Question).filter(Question.topic_id == topic_id).count()
    return {"count": count}

@app.get("/topics/{topic_id}/questions")
async def get_questions_by_topic(topic_id: int, db: Session = Depends(get_db)):
    """Get questions for a specific topic by ID"""
    try:
        topic = db.query(Topic).filter(Topic.id == topic_id).first()
        if not topic:
            raise HTTPException(status_code=404, detail="Topic not found")
        
        questions = db.query(Question).filter(Question.topic_id == topic_id).all()
        return [{
            "id": q.id, 
            "text": q.text, 
            "difficulty": q.difficulty,
            "options": q.options,  # This is already a JSON array in the database
            "correct_answer": q.correct_answer,
            "explanation": q.explanation
        } for q in questions]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching questions: {str(e)}")

class QuestionRequest(BaseModel):
    subject: str
    topics: List[str]
    count: int = 10
    difficulty: str = "Medium"

@app.post("/questions/generate")
async def generate_questions(
    request: QuestionRequest,
    db: Session = Depends(get_db)
):
    """Generate questions based on subject, topics, and difficulty - OPTIMIZED FOR SPEED"""
    try:
        print(f"DEBUG: Fast question generation - Subject: {request.subject}, Topics: {request.topics[:2] if len(request.topics) > 2 else request.topics}, Count: {request.count}")
        
        # Quick validation to fail fast
        if not request.topics or not request.subject:
            print("DEBUG: Invalid request - using sample questions")
            return generate_sample_questions(request)
        
        # OPTIMIZATION 0: Check cache first for super fast response
        cache_key = f"{request.subject}_{sorted(request.topics)}_{request.difficulty}_{request.count}"
        current_time = time.time()
        
        if cache_key in question_cache:
            cached_data, cache_time = question_cache[cache_key]
            if current_time - cache_time < CACHE_DURATION:
                print(f"DEBUG: Returning cached questions for {cache_key}")
                return cached_data
        
        # OPTIMIZATION 1: Single optimized query with joins to get everything at once
        try:
            # Get subject and topic IDs in one query
            subject_topics = db.query(
                Subject.id.label('subject_id'),
                Topic.id.label('topic_id'),
                Topic.name.label('topic_name')
            ).join(Topic, Topic.subject_id == Subject.id).filter(
                Subject.name == request.subject,
                Topic.name.in_(request.topics)
            ).all()
            
            if not subject_topics:
                print("DEBUG: No matching subject/topics found - using sample questions")
                return generate_sample_questions(request)
            
            topic_ids = [st.topic_id for st in subject_topics]
            print(f"DEBUG: Found {len(topic_ids)} topic IDs in single query")
            
            # OPTIMIZATION 2: Single query for questions with all filters applied
            questions_query = db.query(Question).filter(
                Question.topic_id.in_(topic_ids)
            ).order_by(Question.times_asked.asc())  # Order by least asked first
            
            # Apply difficulty filter directly in query for better performance
            difficulty_lower = request.difficulty.lower()
            difficulty_questions = questions_query.filter(
                func.lower(Question.difficulty) == difficulty_lower
            ).limit(request.count * 3).all()  # Get 3x needed for variety
            
            print(f"DEBUG: Found {len(difficulty_questions)} questions with difficulty '{request.difficulty}'")
            
            # If not enough with exact difficulty, get mixed difficulty
            if len(difficulty_questions) < request.count:
                print("DEBUG: Not enough exact difficulty questions, mixing difficulties")
                all_questions = questions_query.limit(request.count * 2).all()
                selected_questions = all_questions[:request.count] if len(all_questions) >= request.count else all_questions
            else:
                # OPTIMIZATION 3: Simple selection from pre-sorted (least asked first) questions
                selected_questions = difficulty_questions[:request.count]
            
            if not selected_questions:
                print("DEBUG: No database questions available - using sample questions")
                return generate_sample_questions(request)
            
            print(f"DEBUG: Selected {len(selected_questions)} questions for response")
            
            # OPTIMIZATION 4: Batch update times_asked in single operation
            question_ids = [q.id for q in selected_questions]
            try:
                db.query(Question).filter(Question.id.in_(question_ids)).update(
                    {Question.times_asked: Question.times_asked + 1},
                    synchronize_session=False
                )
                db.commit()
                print(f"DEBUG: Batch updated times_asked for {len(question_ids)} questions")
            except Exception as e:
                print(f"DEBUG: Failed to batch update: {e}")
                db.rollback()
            
            # OPTIMIZATION 5: Build response without additional queries
            questions = []
            for q in selected_questions:
                questions.append({
                    "id": q.id,
                    "text": q.text,
                    "options": q.options,
                    "correct_answer": q.correct_answer,
                    "hint": q.explanation or f"Consider the key concepts in this topic",
                    "subject": request.subject,
                    "topic": next((st.topic_name for st in subject_topics if st.topic_id == q.topic_id), "General"),
                    "difficulty": request.difficulty,
                    "points": 100 if request.difficulty == "Easy" else 150 if request.difficulty == "Medium" else 200,
                    "media_type": q.media_type,
                    "media_url": q.media_url,
                    "media_metadata": q.media_metadata
                })
            
            print(f"DEBUG: Returning {len(questions)} optimized questions")
            
            # Cache the successful result for future requests
            result = {"questions": questions}
            question_cache[cache_key] = (result, current_time)
            print(f"DEBUG: Cached questions for key: {cache_key}")
            
            return result
            
        except Exception as e:
            print(f"DEBUG: Database query failed: {e}")
            return generate_sample_questions(request)
        
    except Exception as e:
        print(f"ERROR: Critical error in question generation: {e}")
        # Always return sample questions as ultimate fallback
        return generate_sample_questions(request)

def weighted_random_selection(questions, count):
    """
    Select questions using weighted random selection that favors less-asked questions
    but still provides variety for first-time users
    """
    import random
    
    if not questions or count <= 0:
        return []
    
    if len(questions) <= count:
        random.shuffle(questions)
        return questions
    
    # Calculate weights: higher weight for questions asked fewer times
    max_times_asked = max(q.times_asked for q in questions) + 1
    weights = []
    for q in questions:
        # Inverse weight: questions asked 0 times get highest weight
        weight = max_times_asked - q.times_asked
        weights.append(weight)
    
    # Use weighted random selection
    selected = []
    available_questions = questions.copy()
    available_weights = weights.copy()
    
    for _ in range(min(count, len(available_questions))):
        if not available_questions:
            break
            
        # Select based on weights
        selected_question = random.choices(available_questions, weights=available_weights, k=1)[0]
        selected.append(selected_question)
        
        # Remove selected question from available pool
        index = available_questions.index(selected_question)
        available_questions.pop(index)
        available_weights.pop(index)
    
    return selected

def smart_question_sampling(questions, count, topic_ids):
    """
    Smart question sampling that prioritizes questions with least times_asked
    and ensures even distribution across multiple topics with randomization for variety
    """
    try:
        print(f"DEBUG: Smart sampling - {len(questions)} questions, need {count}, topics: {topic_ids}")
        
        if not questions:
            return []
        
        if len(questions) <= count:
            # If we have fewer questions than needed, return all
            print(f"DEBUG: Returning all {len(questions)} available questions")
            return questions
        
        # Quick check for enhanced randomization (simplified for performance)
        sample_size = min(20, len(questions))  # Check only first 20 questions for performance
        sample_questions = questions[:sample_size]
        zero_count = sum(1 for q in sample_questions if q.times_asked == 0)
        
        # If 70% or more of sample have times_asked = 0, use enhanced randomization
        use_enhanced_randomization = (zero_count / sample_size) >= 0.7
        print(f"DEBUG: Enhanced randomization mode: {use_enhanced_randomization} (sample: {zero_count}/{sample_size} with times_asked=0)")
        
        # Group questions by topic for even distribution
        topic_questions = {}
        for question in questions:
            topic_id = question.topic_id
            if topic_id not in topic_questions:
                topic_questions[topic_id] = []
            topic_questions[topic_id].append(question)
        
        print(f"DEBUG: Questions grouped by topic: {[(tid, len(qs)) for tid, qs in topic_questions.items()]}")
        
        # Sort questions within each topic by times_asked (ascending) with enhanced randomization
        import random
        for topic_id in topic_questions:
            if use_enhanced_randomization:
                # For first-time users, use weighted random selection favoring less-asked questions
                topic_questions[topic_id] = weighted_random_selection(topic_questions[topic_id], len(topic_questions[topic_id]))
            else:
                # Standard approach: shuffle first, then sort by times_asked
                random.shuffle(topic_questions[topic_id])
                topic_questions[topic_id].sort(key=lambda q: q.times_asked)
            
            if topic_questions[topic_id]:
                print(f"DEBUG: Topic {topic_id} - times_asked range: {topic_questions[topic_id][0].times_asked} to {topic_questions[topic_id][-1].times_asked}")
        
        selected_questions = []
        questions_per_topic = count // len(topic_questions)
        remaining_questions = count % len(topic_questions)
        
        print(f"DEBUG: Base questions per topic: {questions_per_topic}, remaining: {remaining_questions}")
        
        # Distribute questions evenly across topics
        topic_ids_list = list(topic_questions.keys())
        for i, topic_id in enumerate(topic_ids_list):
            # Calculate how many questions to take from this topic
            topic_count = questions_per_topic
            if i < remaining_questions:
                topic_count += 1
            
            # Take the least asked questions from this topic
            available_questions = topic_questions[topic_id]
            topic_selected = available_questions[:min(topic_count, len(available_questions))]
            selected_questions.extend(topic_selected)
            
            print(f"DEBUG: Topic {topic_id}: selected {len(topic_selected)} questions (times_asked: {[q.times_asked for q in topic_selected]})")
        
        # If we still need more questions (due to uneven distribution), 
        # fill from remaining questions with lowest times_asked
        if len(selected_questions) < count:
            remaining_needed = count - len(selected_questions)
            all_remaining = [q for q in questions if q not in selected_questions]
            
            if use_enhanced_randomization and all_remaining:
                # Use weighted selection for remaining questions too
                additional_questions = weighted_random_selection(all_remaining, remaining_needed)
                selected_questions.extend(additional_questions)
            else:
                # Standard approach: randomize first, then sort
                random.shuffle(all_remaining)
                all_remaining.sort(key=lambda q: q.times_asked)
                selected_questions.extend(all_remaining[:remaining_needed])
            
            print(f"DEBUG: Added {remaining_needed} additional questions to reach target count")
        
        # Final shuffle to randomize order while maintaining smart selection
        random.shuffle(selected_questions)
        
        print(f"DEBUG: Final selection: {len(selected_questions)} questions")
        print(f"DEBUG: Times asked distribution: {[q.times_asked for q in selected_questions]}")
        
        return selected_questions[:count]  # Ensure we don't exceed the requested count
        
    except Exception as e:
        print(f"ERROR: Smart sampling failed: {e}")
        import traceback
        traceback.print_exc()
        # Fallback to simple random sampling
        import random
        return random.sample(questions, min(count, len(questions)))

def generate_sample_questions(request):
    """Generate sample questions as fallback"""
    print(f"DEBUG: Generating {request.count} sample questions for {request.subject}")
    sample_questions = []
    
    for i in range(request.count):
        sample_questions.append({
            "id": i + 1,
            "text": f"Sample {request.subject} question {i + 1}: What is an important concept in {request.topics[0] if request.topics else request.subject}?",
            "options": [
                f"Correct answer for {request.subject}",
                f"Wrong answer A",
                f"Wrong answer B", 
                f"Wrong answer C"
            ],
            "correct_answer": 0,
            "hint": f"Think about the fundamental principles of {request.subject}",
            "subject": request.subject,
            "topic": request.topics[0] if request.topics else "General",
            "difficulty": request.difficulty,
            "points": 100 if request.difficulty == "Easy" else 150 if request.difficulty == "Medium" else 200,
            "media_type": "text",
            "media_url": None,
            "media_metadata": None
        })
    
    return {"questions": sample_questions}


@app.post("/shutdown")
async def shutdown_server():
    """Shutdown the server gracefully"""
    import os
    import signal
    
    def shutdown():
        os.kill(os.getpid(), signal.SIGTERM)
    
    # Schedule shutdown after response is sent
    import threading
    threading.Timer(0.5, shutdown).start()
    
    return {"message": "Server shutting down..."}


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
