"""
Tournament system database models for QuizClash
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

# Import User model to establish relationships
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .models import User, Topic, Question

# Association table for tournament topics (many-to-many)
tournament_topics = Table(
    'tournament_topics',
    Base.metadata,
    Column('tournament_id', Integer, ForeignKey('tournaments.id'), primary_key=True),
    Column('topic_id', Integer, ForeignKey('topics.id'), primary_key=True)
)

# Association table for tournament questions (many-to-many)
tournament_questions = Table(
    'tournament_questions',
    Base.metadata,
    Column('tournament_id', Integer, ForeignKey('tournaments.id'), primary_key=True),
    Column('question_id', Integer, ForeignKey('questions.id'), primary_key=True)
)

class Tournament(Base):
    """Tournament model"""
    __tablename__ = "tournaments"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    subject = Column(String(100), nullable=False)
    difficulty = Column(String(20), nullable=False)  # Easy, Medium, Hard
    
    # Financial settings
    subscription_fee = Column(Float, default=0.0)
    prize_pool = Column(Float, default=0.0)
    first_prize = Column(Float, default=0.0)
    second_prize = Column(Float, default=0.0)
    third_prize = Column(Float, default=0.0)
    
    # Tournament settings
    min_players = Column(Integer, default=2)
    max_players = Column(Integer, default=100)
    questions_count = Column(Integer, default=10)
    time_limit = Column(Integer, default=30)  # seconds per question
    
    # Status and timing
    status = Column(String(20), default="draft")  # draft, active, completed, cancelled
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    registration_deadline = Column(DateTime, nullable=True)
    
    # Admin settings
    created_by = Column(Integer, ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    creator = relationship("User", foreign_keys=[created_by])
    topics = relationship("Topic", secondary=tournament_topics)
    questions = relationship("Question", secondary=tournament_questions)
    participants = relationship("TournamentParticipant", back_populates="tournament")
    sessions = relationship("TournamentSession", back_populates="tournament")

class TournamentParticipant(Base):
    """Tournament participant model"""
    __tablename__ = "tournament_participants"
    
    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(Integer, ForeignKey('tournaments.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    # Registration info
    registered_at = Column(DateTime, default=func.now())
    payment_status = Column(String(20), default="pending")  # pending, paid, failed
    payment_amount = Column(Float, default=0.0)
    payment_method = Column(String(20), nullable=True)  # free, crypto, momo
    payment_id = Column(String(100), nullable=True)
    payment_details = Column(Text, nullable=True)  # Additional payment info
    
    # Game results
    has_played = Column(Boolean, default=False)
    score = Column(Integer, default=0)
    accuracy = Column(Float, default=0.0)
    time_taken = Column(Integer, default=0)  # total seconds
    rank = Column(Integer, nullable=True)
    prize_won = Column(Float, default=0.0)
    
    # Timestamps
    played_at = Column(DateTime, nullable=True)
    
    # Relationships
    tournament = relationship("Tournament", back_populates="participants")
    user = relationship("User")

class TournamentSession(Base):
    """Tournament game session model"""
    __tablename__ = "tournament_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(Integer, ForeignKey('tournaments.id'), nullable=False)
    participant_id = Column(Integer, ForeignKey('tournament_participants.id'), nullable=False)
    
    # Session data
    total_questions = Column(Integer, nullable=False)
    questions_answered = Column(Integer, default=0)
    correct_answers = Column(Integer, default=0)
    total_score = Column(Integer, default=0)
    time_spent = Column(Integer, default=0)  # total seconds
    accuracy = Column(Float, default=0.0)
    
    # Status
    is_completed = Column(Boolean, default=False)
    started_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    tournament = relationship("Tournament", back_populates="sessions")
    participant = relationship("TournamentParticipant")
    answers = relationship("TournamentAnswer", back_populates="session")

class TournamentAnswer(Base):
    """Tournament answer model"""
    __tablename__ = "tournament_answers"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey('tournament_sessions.id'), nullable=False)
    question_id = Column(Integer, ForeignKey('questions.id'), nullable=False)
    
    # Answer data
    selected_answer = Column(Integer, nullable=False)
    is_correct = Column(Boolean, nullable=False)
    time_taken = Column(Integer, nullable=False)  # seconds
    points_earned = Column(Integer, default=0)
    
    # Timestamp
    answered_at = Column(DateTime, default=func.now())
    
    # Relationships
    session = relationship("TournamentSession", back_populates="answers")
    question = relationship("Question")

class TournamentPrize(Base):
    """Tournament prize distribution model"""
    __tablename__ = "tournament_prizes"
    
    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(Integer, ForeignKey('tournaments.id'), nullable=False)
    participant_id = Column(Integer, ForeignKey('tournament_participants.id'), nullable=False)
    
    # Prize details
    rank = Column(Integer, nullable=False)
    prize_amount = Column(Float, nullable=False)
    prize_type = Column(String(50), default="cash")  # cash, credits, gems
    
    # Status
    is_distributed = Column(Boolean, default=False)
    distributed_at = Column(DateTime, nullable=True)
    
    # Relationships
    tournament = relationship("Tournament")
    participant = relationship("TournamentParticipant")
