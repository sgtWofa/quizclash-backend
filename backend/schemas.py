"""
Pydantic schemas for request/response validation in QuizClash API
"""
from pydantic import BaseModel, field_validator
from typing import List, Optional, Any
from datetime import datetime
from enum import Enum


class APIResponse(BaseModel):
    message: str
    success: bool = True


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


class GameMode(str, Enum):
    SOLO = "solo"
    TOURNAMENT = "tournament"
    FRIEND = "friend"
    AI = "ai"


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


# User Schemas
class UserBase(BaseModel):
    username: str
    email: str
    role: UserRole = UserRole.USER


class UserCreate(UserBase):
    password: str


class UserLogin(BaseModel):
    username: str  # Can be username or email
    password: str


class UserResponse(UserBase):
    id: int
    is_active: bool
    total_score: int
    games_played: int
    achievements_count: int
    created_at: datetime
    last_login: Optional[datetime]

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    email: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


# Subject Schemas
class SubjectBase(BaseModel):
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None


class SubjectCreate(SubjectBase):
    pass


class SubjectResponse(SubjectBase):
    id: int
    is_active: bool
    created_by: int
    created_at: datetime
    topics_count: Optional[int] = 0

    class Config:
        from_attributes = True


class SubjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    is_active: Optional[bool] = None


# Topic Schemas
class TopicBase(BaseModel):
    name: str
    description: Optional[str] = None
    subject_id: int


class TopicCreate(TopicBase):
    pass


class TopicResponse(TopicBase):
    id: int
    is_active: bool
    question_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class TopicUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


# Question Schemas
class QuestionOption(BaseModel):
    text: str
    is_correct: bool


class QuestionBase(BaseModel):
    text: str
    topic_id: int
    subject_id: int  # CRITICAL: Missing subject_id field
    options: List[str]  # List of 4 option texts
    correct_answer: int  # Index of correct option (0-3)
    difficulty: Difficulty = Difficulty.MEDIUM
    explanation: Optional[str] = None
    media_type: Optional[str] = "text"  # text, image, audio, video
    media_url: Optional[str] = None
    media_metadata: Optional[dict] = None

    @field_validator('media_metadata', mode='before')
    @classmethod
    def parse_media_metadata(cls, v):
        """Parse media_metadata if it's a JSON string"""
        if v is None:
            return None
        if isinstance(v, str):
            try:
                import json
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return None
        return v

    @field_validator('options')
    @classmethod
    def validate_options(cls, v):
        if len(v) != 4:
            raise ValueError('Exactly 4 options are required')
        return v

    @field_validator('correct_answer')
    @classmethod
    def validate_correct_answer(cls, v):
        if v not in [0, 1, 2, 3]:
            raise ValueError('Correct answer must be between 0 and 3')
        return v


class QuestionCreate(QuestionBase):
    pass


class QuestionResponse(QuestionBase):
    id: int
    times_asked: int
    times_correct: int
    accuracy: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True


class QuestionUpdate(BaseModel):
    text: Optional[str] = None
    topic_id: Optional[int] = None
    options: Optional[List[str]] = None
    correct_answer: Optional[int] = None
    difficulty: Optional[Difficulty] = None
    explanation: Optional[str] = None
    media_type: Optional[str] = None
    media_url: Optional[str] = None
    media_metadata: Optional[dict] = None

    @field_validator('media_metadata', mode='before')
    @classmethod
    def parse_media_metadata(cls, v):
        """Parse media_metadata if it's a JSON string"""
        if v is None:
            return None
        if isinstance(v, str):
            try:
                import json
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return None
        return v

    @field_validator('options')
    @classmethod
    def validate_options(cls, v):
        if v is not None and len(v) != 4:
            raise ValueError('Exactly 4 options are required')
        return v

    @field_validator('correct_answer')
    @classmethod
    def validate_correct_answer(cls, v):
        if v is not None and v not in [0, 1, 2, 3]:
            raise ValueError('Correct answer must be between 0 and 3')
        return v


# Game Session Schemas
class GameSessionCreate(BaseModel):
    subject_id: int
    mode: GameMode
    difficulty: Difficulty = Difficulty.MEDIUM
    total_questions: int = 10
    topic_ids: Optional[List[int]] = None


class GameSessionResponse(BaseModel):
    id: int
    user_id: int
    subject_id: int
    mode: GameMode
    difficulty: Difficulty
    total_questions: int
    questions_answered: int
    correct_answers: int
    total_score: int
    time_spent: int
    is_completed: bool
    started_at: datetime
    completed_at: Optional[datetime]
    accuracy: Optional[float] = None

    class Config:
        from_attributes = True


class GameAnswerCreate(BaseModel):
    question_id: int
    selected_answer: str
    time_taken: int  # in seconds


class UserUpdate(BaseModel):
    username: str
    email: str
    role: str


class UserStatusUpdate(BaseModel):
    is_active: bool


# Duplicate schemas removed - using QuestionBase-derived schemas above


class SubjectCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    icon: Optional[str] = "📚"


class SubjectUpdate(BaseModel):
    name: str
    description: Optional[str] = ""
    icon: Optional[str] = "📚"


class TopicCreate(BaseModel):
    name: str
    subject_id: int
    description: Optional[str] = ""


class TopicUpdate(BaseModel):
    name: str
    subject_id: int
    description: Optional[str] = ""


class GameAnswerResponse(BaseModel):
    id: int
    question_id: int
    selected_answer: str
    is_correct: bool
    time_taken: int
    points_earned: int
    answered_at: datetime

    class Config:
        from_attributes = True


# Achievement Schemas
class AchievementResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    badge_icon: Optional[str]
    category: Optional[str]
    unlocked_at: datetime

    class Config:
        from_attributes = True


# Leaderboard Schemas
class LeaderboardEntry(BaseModel):
    user_id: int
    username: str
    score: int
    accuracy: Optional[float]
    games_count: int
    rank: Optional[int] = None

    class Config:
        from_attributes = True


class LeaderboardResponse(BaseModel):
    entries: List[LeaderboardEntry]
    total_count: int
    page: int
    page_size: int


# Tournament Schemas
class TournamentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    subject_id: int
    max_participants: int = 100
    entry_fee: int = 0
    prize_pool: int = 0
    start_time: datetime
    end_time: datetime


class TournamentResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    subject_id: int
    max_participants: int
    entry_fee: int
    prize_pool: int
    start_time: datetime
    end_time: datetime
    status: str
    participants_count: Optional[int] = 0
    created_at: datetime

    class Config:
        from_attributes = True


# Bulk Operations
class BulkQuestionCreate(BaseModel):
    questions: List[QuestionCreate]


class BulkQuestionResponse(BaseModel):
    created_count: int
    failed_count: int
    errors: List[str] = []


# Statistics and Analytics
class UserStats(BaseModel):
    total_games: int
    total_score: int
    average_score: float
    best_score: int
    total_correct: int
    total_questions: int
    overall_accuracy: float
    favorite_subject: Optional[str]
    achievements_count: int
    current_streak: int
    best_streak: int


class SubjectStats(BaseModel):
    subject_id: int
    subject_name: str
    total_questions: int
    total_games: int
    average_accuracy: float
    most_difficult_topic: Optional[str]


class TournamentPerformance(BaseModel):
    tournament_title: str
    rank: Optional[int]
    score: int
    prize_won: float
    date: Optional[str]


class TournamentStats(BaseModel):
    tournaments_joined: int
    tournaments_won: int
    top_3_finishes: int
    prize_money_earned: float
    tournament_streak: int
    avg_tournament_rank: Optional[float]
    best_tournament_score: int
    total_tournament_points: int
    recent_performance: List[TournamentPerformance]
    win_rate: float
    podium_rate: float


# Pagination
class PaginationParams(BaseModel):
    page: int = 1
    page_size: int = 10
    search: Optional[str] = None
    sort_by: Optional[str] = None
    sort_order: Optional[str] = "asc"


# API Response wrapper
class APIResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None
    errors: Optional[List[str]] = None


# Token Response
class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: UserResponse
