"""
SQLAlchemy models for QuizClash application
"""
from sqlalchemy import Column, Integer, String, ForeignKey, JSON, DateTime, Boolean, Text, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from backend.database import Base
from datetime import datetime


class User(Base):
    """User model for authentication and user management"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="user")  # user, admin
    is_active = Column(Boolean, default=True)
    total_score = Column(Integer, default=0)
    games_played = Column(Integer, default=0)
    level = Column(Integer, default=1)
    achievements_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    last_login = Column(DateTime)
    
    # Relationships
    game_sessions = relationship("GameSession", back_populates="user")
    achievements = relationship("Achievement", back_populates="user")
    leaderboard_entries = relationship("Leaderboard", back_populates="user")
    created_subjects = relationship("Subject", back_populates="creator")


class Subject(Base):
    """Subject model (e.g., Science, History, Mathematics)"""
    __tablename__ = "subjects"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text)
    icon = Column(String(50))  # Icon name or path
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    creator = relationship("User", back_populates="created_subjects")
    topics = relationship("Topic", back_populates="subject", cascade="all, delete-orphan")
    game_sessions = relationship("GameSession", back_populates="subject")
    leaderboard_entries = relationship("Leaderboard", back_populates="subject")


class Topic(Base):
    """Topic model under subjects (e.g., Physics under Science)"""
    __tablename__ = "topics"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    description = Column(Text)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    question_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    subject = relationship("Subject", back_populates="topics")
    questions = relationship("Question", back_populates="topic", cascade="all, delete-orphan")
    
    # Tournament relationships (defined in tournament_models.py)
    # tournaments = relationship("Tournament", secondary="tournament_topics", back_populates="topics")


class Question(Base):
    """Question model with multiple choice options and multimedia support"""
    __tablename__ = "questions"
    
    id = Column(Integer, primary_key=True, index=True)
    text = Column(Text, nullable=False)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)  # Added subject_id
    options = Column(JSON, nullable=False)  # List of 4 options with correct answer marked
    correct_answer = Column(Integer, nullable=False)  # Index of correct option (0-3)
    difficulty = Column(String(20), default="medium")  # easy, medium, hard
    explanation = Column(Text)  # Optional explanation for the answer
    times_asked = Column(Integer, default=0)
    times_correct = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    
    # Multimedia support fields
    media_type = Column(String(20), default="text")  # text, image, audio, video
    media_url = Column(String(500))  # Path or URL to media file
    media_metadata = Column(JSON)  # Additional metadata (duration, dimensions, etc.)
    
    # Relationships
    topic = relationship("Topic", back_populates="questions")
    subject = relationship("Subject")  # Added subject relationship
    game_answers = relationship("GameAnswer", back_populates="question")
    
    # Tournament relationships (defined in tournament_models.py)
    # tournaments = relationship("Tournament", secondary="tournament_questions", back_populates="questions")


class GameSession(Base):
    """Game session tracking individual games"""
    __tablename__ = "game_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    mode = Column(String(20), nullable=False)  # solo, tournament, friend, ai
    difficulty = Column(String(20), default="medium")
    total_questions = Column(Integer, nullable=False)
    questions_answered = Column(Integer, default=0)
    correct_answers = Column(Integer, default=0)
    total_score = Column(Integer, default=0)
    time_spent = Column(Integer, default=0)  # in seconds
    is_completed = Column(Boolean, default=False)
    started_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime)
    
    # Relationships
    user = relationship("User", back_populates="game_sessions")
    subject = relationship("Subject", back_populates="game_sessions")
    game_answers = relationship("GameAnswer", back_populates="game_session")


class GameAnswer(Base):
    """Individual question answers within a game session"""
    __tablename__ = "game_answers"
    
    id = Column(Integer, primary_key=True, index=True)
    game_session_id = Column(Integer, ForeignKey("game_sessions.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    selected_answer = Column(Integer)  # Index of selected option (0-3), null if not answered
    is_correct = Column(Boolean, default=False)
    time_taken = Column(Integer, default=0)  # in seconds
    points_earned = Column(Integer, default=0)
    answered_at = Column(DateTime, default=func.now())
    
    # Relationships
    game_session = relationship("GameSession", back_populates="game_answers")
    question = relationship("Question", back_populates="game_answers")


class Achievement(Base):
    """User achievements and badges"""
    __tablename__ = "achievements"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    badge_icon = Column(String(50))
    category = Column(String(50))  # score, streak, games, time, etc.
    requirement_value = Column(Integer)  # The value needed to unlock
    unlocked_at = Column(DateTime, default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="achievements")


class Leaderboard(Base):
    """Leaderboard entries for different categories"""
    __tablename__ = "leaderboards"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"))
    mode = Column(String(20))  # solo, tournament, friend, ai, or null for overall
    score = Column(Integer, nullable=False)
    accuracy = Column(Float)  # Percentage accuracy
    games_count = Column(Integer, default=1)
    last_updated = Column(DateTime, default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="leaderboard_entries")
    subject = relationship("Subject", back_populates="leaderboard_entries")


class PowerupPurchase(Base):
    """Track powerup purchases for persistence"""
    __tablename__ = "powerup_purchases"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    powerup_id = Column(String(50), nullable=False)
    powerup_name = Column(String(100), nullable=False)
    price_paid = Column(Integer, nullable=False)
    uses_remaining = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    purchased_at = Column(DateTime, default=func.now())
    
    # Relationships
    user = relationship("User")


# Tournament models moved to tournament_models.py to avoid conflicts

# Import audio settings model
from .audio_settings_model import UserAudioSettings
