"""
Tournament API endpoints for QuizClash
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel
import uuid
import hashlib
import hmac

from .database import get_db
from .auth import get_current_user, get_admin_user
from .models import User, Subject, Topic, Question
from .tournament_models import (
    Tournament, TournamentParticipant, TournamentSession, 
    TournamentAnswer, TournamentPrize
)

router = APIRouter(prefix="/tournaments", tags=["tournaments"])

def sync_tournament_questions_count(tournament: Tournament, db: Session):
    """Synchronize tournament questions_count with actual number of questions"""
    actual_count = len(tournament.questions)
    if tournament.questions_count != actual_count:
        print(f"DEBUG: Syncing tournament {tournament.id} questions_count from {tournament.questions_count} to {actual_count}")
        tournament.questions_count = actual_count
        db.commit()

# Pydantic models for API
class TournamentCreate(BaseModel):
    title: str
    description: Optional[str] = None
    subject: str
    difficulty: str
    subscription_fee: float = 0.0
    prize_pool: float = 0.0
    first_prize: float = 0.0
    second_prize: float = 0.0
    third_prize: float = 0.0
    min_players: int = 2
    max_players: int = 100
    questions_count: int = 10
    time_limit: int = 30
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    registration_deadline: Optional[datetime] = None
    topic_ids: List[int] = []
    question_ids: List[int] = []

class TournamentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    subject: Optional[str] = None
    difficulty: Optional[str] = None
    subscription_fee: Optional[float] = None
    prize_pool: Optional[float] = None
    first_prize: Optional[float] = None
    second_prize: Optional[float] = None
    third_prize: Optional[float] = None
    min_players: Optional[int] = None
    max_players: Optional[int] = None
    questions_count: Optional[int] = None
    time_limit: Optional[int] = None
    status: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    registration_deadline: Optional[datetime] = None
    topic_ids: Optional[List[int]] = None
    question_ids: Optional[List[int]] = None

class TournamentResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    subject: str
    difficulty: str
    subscription_fee: float
    prize_pool: float
    first_prize: float
    second_prize: float
    third_prize: float
    min_players: int
    max_players: int
    questions_count: int
    time_limit: int
    status: str
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    registration_deadline: Optional[datetime]
    created_at: datetime
    participants_count: int
    is_registered: bool = False
    has_played: bool = False
    
    class Config:
        from_attributes = True

class ParticipantResponse(BaseModel):
    id: int
    user_id: int
    username: str
    score: int
    accuracy: float
    time_taken: int
    rank: Optional[int]
    prize_won: Optional[float] = 0.0
    played_at: Optional[datetime] = None
    has_played: Optional[bool] = False
    registered_at: Optional[datetime] = None
    payment_amount: Optional[float] = 0.0
    
    class Config:
        from_attributes = True

class PaymentRequest(BaseModel):
    payment_method: str  # "crypto", "momo", "free"
    amount: float
    currency: Optional[str] = "USD"
    crypto_address: Optional[str] = None
    crypto_currency: Optional[str] = None  # "BTC", "ETH", "USDT"
    momo_number: Optional[str] = None
    momo_provider: Optional[str] = None  # "MTN", "Vodafone", "AirtelTigo"

class PaymentResponse(BaseModel):
    payment_id: str
    status: str
    payment_method: str
    amount: float
    currency: str
    payment_url: Optional[str] = None
    qr_code: Optional[str] = None
    instructions: Optional[str] = None
    expires_at: Optional[datetime] = None

class TournamentStats(BaseModel):
    tournaments_joined: int
    tournaments_won: int
    top_3_finishes: int
    prize_money_earned: float
    current_streak: int
    avg_tournament_rank: float
    best_tournament_score: int
    total_tournament_points: int
    recent_performance: List[dict]
    win_rate: float
    podium_rate: float

@router.post("/", response_model=TournamentResponse)
async def create_tournament(
    tournament_data: TournamentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new tournament (admin only)"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can create tournaments"
        )
    
    # Validate subject exists
    subject = db.query(Subject).filter(Subject.name == tournament_data.subject).first()
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subject not found"
        )
    
    # Create tournament
    tournament = Tournament(
        title=tournament_data.title,
        description=tournament_data.description,
        subject=tournament_data.subject,
        difficulty=tournament_data.difficulty,
        subscription_fee=tournament_data.subscription_fee,
        prize_pool=tournament_data.prize_pool,
        first_prize=tournament_data.first_prize,
        second_prize=tournament_data.second_prize,
        third_prize=tournament_data.third_prize,
        min_players=tournament_data.min_players,
        max_players=tournament_data.max_players,
        questions_count=tournament_data.questions_count,
        time_limit=tournament_data.time_limit,
        start_date=tournament_data.start_date,
        end_date=tournament_data.end_date,
        registration_deadline=tournament_data.registration_deadline,
        created_by=current_user.id,
        status="draft"
    )
    
    db.add(tournament)
    db.commit()
    db.refresh(tournament)
    
    # Add topics
    if tournament_data.topic_ids:
        topics = db.query(Topic).filter(Topic.id.in_(tournament_data.topic_ids)).all()
        tournament.topics.extend(topics)
    
    # Add questions
    if tournament_data.question_ids:
        # Use specifically selected questions
        questions = db.query(Question).filter(Question.id.in_(tournament_data.question_ids)).all()
        tournament.questions.extend(questions)
        print(f"DEBUG: Added {len(questions)} specifically selected questions to tournament {tournament.id}")
    elif tournament_data.topic_ids:
        # If no specific questions selected, use all questions from selected topics
        questions = db.query(Question).filter(Question.topic_id.in_(tournament_data.topic_ids)).all()
        tournament.questions.extend(questions)
        print(f"DEBUG: Added {len(questions)} questions from {len(tournament_data.topic_ids)} topics to tournament {tournament.id}")
    
    # Commit the questions to the database BEFORE syncing
    if tournament.questions:
        db.commit()
        db.refresh(tournament)
        # Force reload the questions relationship
        db.expunge(tournament)
        tournament = db.query(Tournament).filter(Tournament.id == tournament.id).first()
        print(f"DEBUG: After commit and reload - tournament {tournament.id} has {len(tournament.questions)} questions")
        sync_tournament_questions_count(tournament, db)
    
    # Return response with manual field mapping
    response = TournamentResponse(
        id=tournament.id,
        title=tournament.title,
        description=tournament.description,
        subject=tournament.subject,
        difficulty=tournament.difficulty,
        subscription_fee=tournament.subscription_fee,
        prize_pool=tournament.prize_pool,
        first_prize=tournament.first_prize,
        second_prize=tournament.second_prize,
        third_prize=tournament.third_prize,
        min_players=tournament.min_players,
        max_players=tournament.max_players,
        questions_count=tournament.questions_count,
        time_limit=tournament.time_limit,
        status=tournament.status,
        start_date=tournament.start_date,
        end_date=tournament.end_date,
        registration_deadline=tournament.registration_deadline,
        created_at=tournament.created_at,
        participants_count=0,
        is_registered=False,
        has_played=False
    )
    
    return response

@router.get("/", response_model=List[TournamentResponse])
async def get_tournaments(
    status: Optional[str] = None,
    subject: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all tournaments with optional filters"""
    query = db.query(Tournament)
    
    # Admin can see all tournaments, regular users only see published ones
    if current_user.role != "admin":
        query = query.filter(Tournament.status.in_(["active", "published"]))
    
    if status:
        query = query.filter(Tournament.status == status)
    if subject:
        query = query.filter(Tournament.subject == subject)
    
    tournaments = query.order_by(Tournament.created_at.desc()).all()
    
    # Add participant info for current user
    result = []
    for tournament in tournaments:
        # Ensure questions_count is accurate
        sync_tournament_questions_count(tournament, db)
        
        participants_count = db.query(TournamentParticipant).filter(
            TournamentParticipant.tournament_id == tournament.id
        ).count()
        
        participant = db.query(TournamentParticipant).filter(
            TournamentParticipant.tournament_id == tournament.id,
            TournamentParticipant.user_id == current_user.id
        ).first()
        
        response = TournamentResponse(
            id=tournament.id,
            title=tournament.title,
            description=tournament.description,
            subject=tournament.subject,
            difficulty=tournament.difficulty,
            subscription_fee=tournament.subscription_fee,
            prize_pool=tournament.prize_pool,
            first_prize=tournament.first_prize,
            second_prize=tournament.second_prize,
            third_prize=tournament.third_prize,
            min_players=tournament.min_players,
            max_players=tournament.max_players,
            questions_count=tournament.questions_count,
            time_limit=tournament.time_limit,
            status=tournament.status,
            start_date=tournament.start_date,
            end_date=tournament.end_date,
            registration_deadline=tournament.registration_deadline,
            created_at=tournament.created_at,
            participants_count=participants_count,
            is_registered=participant is not None,
            has_played=participant.has_played if participant else False
        )
        
        result.append(response)
    
    return result

# User stats endpoint - MUST be before /{tournament_id} route to avoid conflicts
@router.get("/user-stats", response_model=TournamentStats)
async def get_user_tournament_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get tournament statistics for the current user"""
    print(f"DEBUG: Tournament stats requested for user {current_user.id}")
    
    try:
        # Get user's tournament participation data
        user_participations = db.query(TournamentParticipant).filter(
            TournamentParticipant.user_id == current_user.id
        ).all()
        
        # Calculate basic tournament metrics
        tournaments_joined = len(user_participations)
        tournaments_won = len([p for p in user_participations if getattr(p, 'rank', None) == 1])
        top_3_finishes = len([p for p in user_participations if getattr(p, 'rank', None) and p.rank <= 3])
        
        # Calculate prize money earned
        prize_money_earned = sum([getattr(p, 'prize_won', 0) or 0 for p in user_participations])
        
        # Calculate current tournament streak (consecutive wins)
        recent_participations = sorted(user_participations, key=lambda x: x.registered_at, reverse=True)
        current_streak = 0
        for participation in recent_participations:
            if getattr(participation, 'rank', None) == 1:
                current_streak += 1
            else:
                break
        
        # Calculate additional metrics
        total_tournament_points = sum([p.score or 0 for p in user_participations])
        avg_tournament_rank = sum([getattr(p, 'rank', 999) for p in user_participations if getattr(p, 'rank', None)]) / max(len([p for p in user_participations if getattr(p, 'rank', None)]), 1)
        best_tournament_score = max([p.score or 0 for p in user_participations]) if user_participations else 0
        
        # Get recent tournament performance (last 5 tournaments)
        recent_performance = []
        for participation in recent_participations[:5]:
            tournament = db.query(Tournament).filter(Tournament.id == participation.tournament_id).first()
            if tournament:
                recent_performance.append({
                    "tournament_title": tournament.title,
                    "rank": getattr(participation, 'rank', None),
                    "score": participation.score or 0,
                    "prize_won": float(getattr(participation, 'prize_won', 0) or 0),
                    "date": participation.registered_at.isoformat() if participation.registered_at else None
                })
        
        result = {
            "tournaments_joined": tournaments_joined,
            "tournaments_won": tournaments_won,
            "top_3_finishes": top_3_finishes,
            "prize_money_earned": float(prize_money_earned),
            "current_streak": current_streak,
            "avg_tournament_rank": round(avg_tournament_rank, 1) if avg_tournament_rank < 999 else None,
            "best_tournament_score": best_tournament_score,
            "total_tournament_points": total_tournament_points,
            "recent_performance": recent_performance,
            "win_rate": round((tournaments_won / tournaments_joined * 100), 1) if tournaments_joined > 0 else 0.0,
            "podium_rate": round((top_3_finishes / tournaments_joined * 100), 1) if tournaments_joined > 0 else 0.0
        }
        
        print(f"DEBUG: Tournament stats result: {result}")
        return result
        
    except Exception as e:
        print(f"Error fetching tournament statistics: {e}")
        import traceback
        traceback.print_exc()
        
        # Return empty stats on error
        return {
            "tournaments_joined": 0,
            "tournaments_won": 0,
            "top_3_finishes": 0,
            "prize_money_earned": 0.0,
            "current_streak": 0,
            "avg_tournament_rank": None,
            "best_tournament_score": 0,
            "total_tournament_points": 0,
            "recent_performance": [],
            "win_rate": 0.0,
            "podium_rate": 0.0
        }

@router.get("/{tournament_id}", response_model=TournamentResponse)
async def get_tournament(
    tournament_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get tournament details"""
    tournament = db.query(Tournament).filter(Tournament.id == tournament_id).first()
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tournament not found"
        )
    
    participants_count = db.query(TournamentParticipant).filter(
        TournamentParticipant.tournament_id == tournament_id
    ).count()
    
    participant = db.query(TournamentParticipant).filter(
        TournamentParticipant.tournament_id == tournament_id,
        TournamentParticipant.user_id == current_user.id
    ).first()
    
    response = TournamentResponse(
        id=tournament.id,
        title=tournament.title,
        description=tournament.description,
        subject=tournament.subject,
        difficulty=tournament.difficulty,
        subscription_fee=tournament.subscription_fee,
        prize_pool=tournament.prize_pool,
        first_prize=tournament.first_prize,
        second_prize=tournament.second_prize,
        third_prize=tournament.third_prize,
        min_players=tournament.min_players,
        max_players=tournament.max_players,
        questions_count=tournament.questions_count,
        time_limit=tournament.time_limit,
        status=tournament.status,
        start_date=tournament.start_date,
        end_date=tournament.end_date,
        registration_deadline=tournament.registration_deadline,
        created_at=tournament.created_at,
        participants_count=participants_count,
        is_registered=participant is not None,
        has_played=participant.has_played if participant else False
    )
    
    return response

@router.put("/{tournament_id}/status")
async def update_tournament_status(
    tournament_id: int,
    status_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update tournament status (admin only)"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update tournament status"
        )
    
    tournament = db.query(Tournament).filter(Tournament.id == tournament_id).first()
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tournament not found"
        )
    
    new_status = status_data.get("status")
    if new_status not in ["draft", "published", "active", "completed", "cancelled"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid status"
        )
    
    tournament.status = new_status
    db.commit()
    
    return {"message": f"Tournament status updated to {new_status}"}

@router.post("/{tournament_id}/register")
async def register_tournament(
    tournament_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Register for a tournament"""
    tournament = db.query(Tournament).filter(Tournament.id == tournament_id).first()
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tournament not found"
        )
    
    if tournament.status not in ["published", "active"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tournament is not available for registration"
        )
    
    # Check if already registered or played
    existing = db.query(TournamentParticipant).filter(
        TournamentParticipant.tournament_id == tournament_id,
        TournamentParticipant.user_id == current_user.id
    ).first()
    
    if existing:
        if existing.has_played:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You have already played this tournament"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Already registered for this tournament"
            )
    
    # Check max participants
    participants_count = db.query(TournamentParticipant).filter(
        TournamentParticipant.tournament_id == tournament_id
    ).count()
    
    if participants_count >= tournament.max_players:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tournament is full"
        )
    
    # Create participant
    participant = TournamentParticipant(
        tournament_id=tournament_id,
        user_id=current_user.id,
        payment_amount=tournament.subscription_fee,
        payment_status="paid" if tournament.subscription_fee == 0 else "pending"
    )
    
    db.add(participant)
    db.commit()
    
    return {"message": "Successfully registered for tournament"}

@router.post("/{tournament_id}/payment", response_model=PaymentResponse)
async def process_tournament_payment(
    tournament_id: int,
    payment_request: PaymentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Process tournament registration payment with crypto, MoMo, or free options"""
    tournament = db.query(Tournament).filter(Tournament.id == tournament_id).first()
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tournament not found"
        )
    
    if tournament.status not in ["published", "active"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tournament is not available for registration"
        )
    
    # Check if already registered
    existing = db.query(TournamentParticipant).filter(
        TournamentParticipant.tournament_id == tournament_id,
        TournamentParticipant.user_id == current_user.id
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already registered for this tournament"
        )
    
    # Check max participants
    participants_count = db.query(TournamentParticipant).filter(
        TournamentParticipant.tournament_id == tournament_id
    ).count()
    
    if participants_count >= tournament.max_players:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tournament is full"
        )
    
    # Validate payment amount
    if payment_request.amount != tournament.subscription_fee:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment amount does not match tournament fee"
        )
    
    payment_id = str(uuid.uuid4())
    
    # Handle free tournaments - register directly
    if tournament.subscription_fee == 0 or payment_request.payment_method == "free":
        participant = TournamentParticipant(
            tournament_id=tournament_id,
            user_id=current_user.id,
            payment_amount=0.0,
            payment_status="paid",
            payment_method="free",
            payment_id=payment_id
        )
        
        db.add(participant)
        db.commit()
        
        return PaymentResponse(
            payment_id=payment_id,
            status="completed",
            payment_method="free",
            amount=0.0,
            currency="USD",
            instructions="Registration completed successfully! Tournament is free."
        )
    
    # Handle crypto payments
    elif payment_request.payment_method == "crypto":
        if not payment_request.crypto_currency:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Crypto currency is required for crypto payments"
            )
        
        # Generate crypto payment details
        crypto_addresses = {
            "BTC": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
            "ETH": "0x742d35Cc6634C0532925a3b8D8C9C4e4e8b8e8e8",
            "USDT": "TQn9Y2khEsLJW1ChVWFMSMeRDow5KcbLSE"
        }
        
        crypto_address = crypto_addresses.get(payment_request.crypto_currency)
        if not crypto_address:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported cryptocurrency"
            )
        
        # Create pending participant
        participant = TournamentParticipant(
            tournament_id=tournament_id,
            user_id=current_user.id,
            payment_amount=payment_request.amount,
            payment_status="pending",
            payment_method="crypto",
            payment_id=payment_id,
            payment_details=f"{payment_request.crypto_currency}:{crypto_address}"
        )
        
        db.add(participant)
        db.commit()
        
        return PaymentResponse(
            payment_id=payment_id,
            status="pending",
            payment_method="crypto",
            amount=payment_request.amount,
            currency=payment_request.crypto_currency,
            qr_code=f"crypto:{payment_request.crypto_currency}:{crypto_address}:{payment_request.amount}",
            instructions=f"Send {payment_request.amount} {payment_request.crypto_currency} to: {crypto_address}",
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
    
    # Handle MoMo payments
    elif payment_request.payment_method == "momo":
        if not payment_request.momo_number or not payment_request.momo_provider:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Mobile number and provider are required for MoMo payments"
            )
        
        # Generate MoMo payment details
        momo_numbers = {
            "MTN": "024-123-4567",
            "Vodafone": "020-987-6543", 
            "AirtelTigo": "027-555-0123"
        }
        
        merchant_number = momo_numbers.get(payment_request.momo_provider)
        if not merchant_number:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported MoMo provider"
            )
        
        # Create pending participant
        participant = TournamentParticipant(
            tournament_id=tournament_id,
            user_id=current_user.id,
            payment_amount=payment_request.amount,
            payment_status="pending",
            payment_method="momo",
            payment_id=payment_id,
            payment_details=f"{payment_request.momo_provider}:{payment_request.momo_number}"
        )
        
        db.add(participant)
        db.commit()
        
        return PaymentResponse(
            payment_id=payment_id,
            status="pending",
            payment_method="momo",
            amount=payment_request.amount,
            currency="GHS",
            instructions=f"Send GHS {payment_request.amount} to {merchant_number} ({payment_request.momo_provider}) with reference: {payment_id[:8]}",
            expires_at=datetime.utcnow() + timedelta(minutes=30)
        )
    
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported payment method"
        )

@router.post("/{tournament_id}/payment/{payment_id}/verify")
async def verify_payment(
    tournament_id: int,
    payment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Verify payment status (for demo purposes, this would integrate with actual payment providers)"""
    participant = db.query(TournamentParticipant).filter(
        TournamentParticipant.tournament_id == tournament_id,
        TournamentParticipant.user_id == current_user.id,
        TournamentParticipant.payment_id == payment_id
    ).first()
    
    if not participant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found"
        )
    
    # For demo purposes, simulate payment verification
    # In production, this would check with actual payment providers
    if participant.payment_status == "pending":
        # Simulate successful payment after 30 seconds (for demo)
        time_elapsed = (datetime.utcnow() - participant.registered_at).total_seconds()
        if time_elapsed > 30:  # Demo: auto-approve after 30 seconds
            participant.payment_status = "paid"
            db.commit()
            return {"status": "paid", "message": "Payment verified successfully"}
        else:
            return {"status": "pending", "message": "Payment verification in progress"}
    
    return {"status": participant.payment_status, "message": f"Payment is {participant.payment_status}"}

@router.get("/{tournament_id}/leaderboard", response_model=List[ParticipantResponse])
async def get_tournament_leaderboard(
    tournament_id: int,
    db: Session = Depends(get_db)
):
    """Get tournament leaderboard"""
    participants = db.query(TournamentParticipant, User.username).join(
        User, TournamentParticipant.user_id == User.id
    ).filter(
        TournamentParticipant.tournament_id == tournament_id,
        TournamentParticipant.has_played == True
    ).order_by(
        TournamentParticipant.score.desc(),
        TournamentParticipant.accuracy.desc(),
        TournamentParticipant.time_taken.asc()
    ).all()
    
    result = []
    for i, (participant, username) in enumerate(participants):
        response = ParticipantResponse(
            id=participant.id,
            user_id=participant.user_id,
            username=username,
            score=participant.score or 0,
            accuracy=participant.accuracy or 0.0,
            time_taken=participant.time_taken or 0,
            rank=i + 1,
            prize_won=getattr(participant, 'prize_won', 0.0) or 0.0,
            played_at=getattr(participant, 'played_at', None),
            has_played=getattr(participant, 'has_played', True),
            registered_at=getattr(participant, 'registered_at', None),
            payment_amount=getattr(participant, 'payment_amount', 0.0) or 0.0
        )
        result.append(response)
    
    return result

@router.put("/{tournament_id}", response_model=TournamentResponse)
async def update_tournament(
    tournament_id: int,
    tournament_data: TournamentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update tournament (admin only)"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update tournaments"
        )
    
    tournament = db.query(Tournament).filter(Tournament.id == tournament_id).first()
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tournament not found"
        )
    
    # Update basic fields (excluding relationships)
    update_dict = tournament_data.dict(exclude_unset=True)
    topic_ids = update_dict.pop('topic_ids', None)
    question_ids = update_dict.pop('question_ids', None)
    
    for field, value in update_dict.items():
        setattr(tournament, field, value)
    
    # Update topics relationship
    if topic_ids is not None:
        tournament.topics.clear()
        if topic_ids:
            topics = db.query(Topic).filter(Topic.id.in_(topic_ids)).all()
            tournament.topics.extend(topics)
    
    # Update questions relationship
    if question_ids is not None:
        tournament.questions.clear()
        if question_ids:
            questions = db.query(Question).filter(Question.id.in_(question_ids)).all()
            tournament.questions.extend(questions)
        
        # Sync questions_count to match actual number of questions
        sync_tournament_questions_count(tournament, db)
    
    # Commit all changes to database
    db.commit()
    db.refresh(tournament)
    
    participants_count = db.query(TournamentParticipant).filter(
        TournamentParticipant.tournament_id == tournament_id
    ).count()
    
    response = TournamentResponse(
        id=tournament.id,
        title=tournament.title,
        description=tournament.description,
        subject=tournament.subject,
        difficulty=tournament.difficulty,
        subscription_fee=tournament.subscription_fee,
        prize_pool=tournament.prize_pool,
        first_prize=tournament.first_prize,
        second_prize=tournament.second_prize,
        third_prize=tournament.third_prize,
        min_players=tournament.min_players,
        max_players=tournament.max_players,
        questions_count=tournament.questions_count,
        time_limit=tournament.time_limit,
        status=tournament.status,
        start_date=tournament.start_date,
        end_date=tournament.end_date,
        registration_deadline=tournament.registration_deadline,
        created_at=tournament.created_at,
        participants_count=participants_count,
        is_registered=False,
        has_played=False
    )
    
    return response

@router.get("/{tournament_id}/participants", response_model=List[ParticipantResponse])
async def get_tournament_participants(
    tournament_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get tournament participants"""
    tournament = db.query(Tournament).filter(Tournament.id == tournament_id).first()
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tournament not found"
        )
    
    participants = db.query(TournamentParticipant, User.username).join(
        User, TournamentParticipant.user_id == User.id
    ).filter(
        TournamentParticipant.tournament_id == tournament_id
    ).all()
    
    result = []
    for participant, username in participants:
        response = ParticipantResponse(
            id=participant.id,
            user_id=participant.user_id,
            username=username,
            score=participant.score or 0,
            accuracy=participant.accuracy or 0.0,
            time_taken=participant.time_taken or 0,
            rank=participant.rank or 0,
            prize_won=0.0,  # Default value for prize_won
            played_at=participant.registered_at,  # Use registered_at for played_at if available
            has_played=participant.has_played,
            registered_at=participant.registered_at,
            payment_amount=participant.payment_amount or 0.0
        )
        result.append(response)
    
    return result

@router.get("/user/{user_id}/history", response_model=List[TournamentResponse])
async def get_user_tournament_history(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get tournament history for a specific user (admin only or own history)"""
    # Check if user is admin or requesting their own history
    if current_user.role != "admin" and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this user's tournament history"
        )
    
    # Get tournaments the user has participated in
    participant_tournaments = db.query(Tournament, TournamentParticipant).join(
        TournamentParticipant, Tournament.id == TournamentParticipant.tournament_id
    ).filter(
        TournamentParticipant.user_id == user_id
    ).order_by(Tournament.created_at.desc()).all()
    
    result = []
    for tournament, participant in participant_tournaments:
        # Get total participants count
        participants_count = db.query(TournamentParticipant).filter(
            TournamentParticipant.tournament_id == tournament.id
        ).count()
        
        response = TournamentResponse(
            id=tournament.id,
            title=tournament.title,
            description=tournament.description,
            subject=tournament.subject,
            difficulty=tournament.difficulty,
            subscription_fee=tournament.subscription_fee,
            prize_pool=tournament.prize_pool,
            first_prize=tournament.first_prize,
            second_prize=tournament.second_prize,
            third_prize=tournament.third_prize,
            min_players=tournament.min_players,
            max_players=tournament.max_players,
            questions_count=tournament.questions_count,
            time_limit=tournament.time_limit,
            status=tournament.status,
            start_date=tournament.start_date,
            end_date=tournament.end_date,
            registration_deadline=tournament.registration_deadline,
            created_at=tournament.created_at,
            participants_count=participants_count,
            is_registered=True,  # Always true since they participated
            has_played=participant.has_played
        )
        result.append(response)
    
    return result

@router.get("/{tournament_id}/questions")
async def get_tournament_questions(
    tournament_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get tournament questions"""
    tournament = db.query(Tournament).filter(Tournament.id == tournament_id).first()
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tournament not found"
        )
    
    # Get questions associated with this tournament
    questions = db.query(Question).join(
        Tournament.questions
    ).filter(Tournament.id == tournament_id).all()
    
    result = []
    for question in questions:
        question_data = {
            "id": question.id,
            "text": question.text,
            "options": question.options,
            "correct_answer": question.correct_answer,
            "difficulty": question.difficulty,
            "explanation": question.explanation,
            "subject": question.subject.name if question.subject else None,
            "topic": question.topic.name if question.topic else None,
            "media_type": question.media_type,
            "media_url": question.media_url,
            "media_metadata": question.media_metadata
        }
        result.append(question_data)
    
    return result

@router.get("/{tournament_id}/topics")
async def get_tournament_topics(
    tournament_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get topics associated with tournament"""
    tournament = db.query(Tournament).filter(Tournament.id == tournament_id).first()
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tournament not found"
        )
    
    # Get topics associated with this tournament
    topics = db.query(Topic).join(
        Tournament.topics
    ).filter(Tournament.id == tournament_id).all()
    
    result = []
    for topic in topics:
        topic_data = {
            "id": topic.id,
            "name": topic.name,
            "subject": topic.subject.name if topic.subject else None
        }
        result.append(topic_data)
    
    return result

@router.delete("/{tournament_id}")
async def delete_tournament(
    tournament_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete tournament (admin only)"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can delete tournaments"
        )
    
    tournament = db.query(Tournament).filter(Tournament.id == tournament_id).first()
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tournament not found"
        )
    
    db.delete(tournament)
    db.commit()
    
    return {"message": "Tournament deleted successfully"}

@router.post("/{tournament_id}/join")
async def join_tournament(
    tournament_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Join a tournament"""
    tournament = db.query(Tournament).filter(Tournament.id == tournament_id).first()
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tournament not found"
        )
    
    # Check if tournament is active
    if tournament.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tournament is not active for registration"
        )
    
    # Check if user already joined
    existing_participant = db.query(TournamentParticipant).filter(
        TournamentParticipant.tournament_id == tournament_id,
        TournamentParticipant.user_id == current_user.id
    ).first()
    
    if existing_participant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already registered for this tournament"
        )
    
    # Check max participants
    participant_count = db.query(TournamentParticipant).filter(
        TournamentParticipant.tournament_id == tournament_id
    ).count()
    
    if participant_count >= tournament.max_players:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tournament is full"
        )
    
    # Create participant
    participant = TournamentParticipant(
        tournament_id=tournament_id,
        user_id=current_user.id,
        payment_amount=tournament.subscription_fee,
        payment_status="paid" if tournament.subscription_fee == 0 else "pending"
    )
    
    db.add(participant)
    db.commit()
    db.refresh(participant)
    
    return {"message": "Successfully joined tournament", "participant_id": participant.id}

@router.post("/{tournament_id}/start")
async def start_tournament_session(
    tournament_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Start a tournament game session"""
    # Get participant
    participant = db.query(TournamentParticipant).filter(
        TournamentParticipant.tournament_id == tournament_id,
        TournamentParticipant.user_id == current_user.id
    ).first()
    
    if not participant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not registered for this tournament"
        )
    
    if participant.has_played:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already played this tournament. Each user can only play once."
        )
    
    # Get tournament
    tournament = db.query(Tournament).filter(Tournament.id == tournament_id).first()
    
    # Create session
    session = TournamentSession(
        tournament_id=tournament_id,
        participant_id=participant.id,
        total_questions=tournament.questions_count
    )
    
    db.add(session)
    db.commit()
    db.refresh(session)
    
    return {
        "session_id": session.id,
        "tournament": {
            "id": tournament.id,
            "title": tournament.title,
            "questions_count": tournament.questions_count,
            "time_limit": tournament.time_limit
        }
    }

@router.post("/{tournament_id}/sessions/{session_id}/answer")
async def submit_tournament_answer(
    tournament_id: int,
    session_id: int,
    answer_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Submit answer for tournament session"""
    # Verify session belongs to user
    session = db.query(TournamentSession).filter(
        TournamentSession.id == session_id,
        TournamentSession.tournament_id == tournament_id
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    participant = db.query(TournamentParticipant).filter(
        TournamentParticipant.id == session.participant_id,
        TournamentParticipant.user_id == current_user.id
    ).first()
    
    if not participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized for this session"
        )
    
    # Get question to check correct answer
    question = db.query(Question).filter(Question.id == answer_data["question_id"]).first()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found"
        )
    
    # Calculate points (base 100 points, bonus for speed)
    is_correct = answer_data["selected_answer"] == question.correct_answer
    time_taken = answer_data["time_taken"]
    points = 0
    
    if is_correct:
        base_points = 100
        # Speed bonus: up to 50 extra points for quick answers
        speed_bonus = max(0, 50 - (time_taken * 2))
        points = base_points + speed_bonus
    
    # Save answer
    tournament_answer = TournamentAnswer(
        session_id=session_id,
        question_id=answer_data["question_id"],
        selected_answer=answer_data["selected_answer"],
        is_correct=is_correct,
        time_taken=time_taken,
        points_earned=points
    )
    
    db.add(tournament_answer)
    
    # Update session stats
    session.questions_answered += 1
    if is_correct:
        session.correct_answers += 1
    session.total_score += points
    session.time_spent += time_taken
    session.accuracy = (session.correct_answers / session.questions_answered) * 100
    
    db.commit()
    
    return {
        "is_correct": is_correct,
        "points_earned": points,
        "total_score": session.total_score,
        "questions_remaining": session.total_questions - session.questions_answered
    }

@router.post("/{tournament_id}/sessions/{session_id}/complete")
async def complete_tournament_session(
    tournament_id: int,
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Complete tournament session and calculate final results"""
    try:
        print(f"DEBUG: Completing tournament session - Tournament: {tournament_id}, Session: {session_id}, User: {current_user.username}")
        
        # Verify session
        session = db.query(TournamentSession).filter(
            TournamentSession.id == session_id,
            TournamentSession.tournament_id == tournament_id
        ).first()
        
        print(f"DEBUG: Session found: {session is not None}")
        if session:
            print(f"DEBUG: Session details - ID: {session.id}, Tournament: {session.tournament_id}, Participant: {session.participant_id}")
        
        if not session:
            print(f"ERROR: Session not found - ID: {session_id}, Tournament: {tournament_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        participant = db.query(TournamentParticipant).filter(
            TournamentParticipant.id == session.participant_id,
            TournamentParticipant.user_id == current_user.id
        ).first()
        
        print(f"DEBUG: Participant found: {participant is not None}")
        if participant:
            print(f"DEBUG: Participant details - ID: {participant.id}, User: {participant.user_id}, Tournament: {participant.tournament_id}")
        
        if not participant:
            print(f"ERROR: Participant not found or not authorized - Participant ID: {session.participant_id}, User ID: {current_user.id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized"
            )
        
        # Mark session as completed
        print(f"DEBUG: Updating session completion status")
        from datetime import datetime
        session.is_completed = True
        session.completed_at = datetime.utcnow()
        
        # Update participant results
        print(f"DEBUG: Updating participant results - Score: {session.total_score}, Accuracy: {session.accuracy}")
        participant.has_played = True
        participant.score = session.total_score or 0
        participant.accuracy = session.accuracy or 0.0
        participant.time_taken = session.time_spent or 0
        participant.played_at = datetime.utcnow()
        
        print(f"DEBUG: Committing session and participant updates")
        db.commit()
        
        # Calculate rank among completed participants
        print(f"DEBUG: Calculating participant rank")
        better_scores = db.query(TournamentParticipant).filter(
            TournamentParticipant.tournament_id == tournament_id,
            TournamentParticipant.has_played == True,
            TournamentParticipant.score > participant.score
        ).count()
        
        participant.rank = better_scores + 1
        print(f"DEBUG: Participant rank calculated: {participant.rank}")
        
        db.commit()
        print(f"DEBUG: Final commit completed successfully")
        
        response_data = {
            "final_score": session.total_score or 0,
            "accuracy": session.accuracy or 0.0,
            "time_taken": session.time_spent or 0,
            "rank": participant.rank,
            "session_completed": True
        }
        
        print(f"DEBUG: Returning completion response: {response_data}")
        return response_data
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        print(f"ERROR: Exception in tournament session completion: {e}")
        import traceback
        print(f"DEBUG: Full traceback: {traceback.format_exc()}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

@router.get("/{tournament_id}/leaderboard")
async def get_tournament_leaderboard(
    tournament_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get tournament leaderboard"""
    print(f"DEBUG: Tournament leaderboard API called for tournament_id: {tournament_id}")
    print(f"DEBUG: Current user: {current_user.username if current_user else 'None'}")
    
    tournament = db.query(Tournament).filter(Tournament.id == tournament_id).first()
    if not tournament:
        print(f"DEBUG: Tournament {tournament_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tournament not found"
        )
    
    print(f"DEBUG: Found tournament: {tournament.title}")
    
    # Get all participants who have played, ordered by score
    participants = db.query(TournamentParticipant).filter(
        TournamentParticipant.tournament_id == tournament_id,
        TournamentParticipant.has_played == True
    ).order_by(TournamentParticipant.score.desc()).all()
    
    print(f"DEBUG: Found {len(participants)} participants who have played")
    
    leaderboard = []
    for i, participant in enumerate(participants, 1):
        user = db.query(User).filter(User.id == participant.user_id).first()
        if user:
            entry = {
                "rank": i,
                "username": user.username,
                "score": participant.score or 0,
                "accuracy": participant.accuracy or 0.0,
                "time_taken": participant.time_taken or 0,
                "prize_won": participant.prize_won or 0
            }
            leaderboard.append(entry)
            print(f"DEBUG: Added leaderboard entry: {entry}")
        else:
            print(f"DEBUG: User not found for participant {participant.user_id}")
    
    response_data = {
        "tournament": {
            "id": tournament.id,
            "title": tournament.title,
            "status": tournament.status,
            "prize_pool": tournament.prize_pool or 0
        },
        "leaderboard": leaderboard,
        "total_participants": len(participants)
    }
    
    print(f"DEBUG: Returning leaderboard response: {response_data}")
    return response_data

@router.get("/{tournament_id}/detailed-results")
async def get_tournament_detailed_results(
    tournament_id: int,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Get detailed tournament results with question-by-question analysis for admin"""
    print(f"DEBUG: Getting detailed results for tournament {tournament_id}")
    
    tournament = db.query(Tournament).filter(Tournament.id == tournament_id).first()
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    # Get all participants who have played
    participants = db.query(TournamentParticipant).filter(
        TournamentParticipant.tournament_id == tournament_id,
        TournamentParticipant.has_played == True
    ).all()
    
    # Calculate results for each participant first
    participant_results = []
    
    for participant in participants:
        user = db.query(User).filter(User.id == participant.user_id).first()
        if not user:
            continue
            
        # Get the tournament session for this participant
        session = db.query(TournamentSession).filter(
            TournamentSession.tournament_id == tournament_id,
            TournamentSession.participant_id == participant.id
        ).first()
        
        if not session:
            continue
            
        # Get all answers for this session with question details
        answers = db.query(TournamentAnswer, Question).join(
            Question, TournamentAnswer.question_id == Question.id
        ).filter(TournamentAnswer.session_id == session.id).all()
        
        # Process answers with question details
        question_results = []
        for answer, question in answers:
            # Extract options from JSON field
            options = question.options if question.options else ["", "", "", ""]
            
            question_results.append({
                "question_id": question.id,
                "question_text": question.text,
                "option_a": options[0] if len(options) > 0 else "",
                "option_b": options[1] if len(options) > 1 else "",
                "option_c": options[2] if len(options) > 2 else "",
                "option_d": options[3] if len(options) > 3 else "",
                "correct_answer": question.correct_answer + 1,  # Convert from 0-based to 1-based
                "selected_answer": answer.selected_answer + 1 if answer.selected_answer is not None else None,  # Convert from 0-based to 1-based
                "is_correct": answer.is_correct,
                "time_taken": answer.time_taken,
                "points_earned": answer.points_earned,
                "answered_at": answer.answered_at.isoformat() if answer.answered_at else None
            })
        
        # Calculate accurate statistics from actual answers
        total_questions = len(question_results)
        correct_answers = sum(1 for q in question_results if q["is_correct"])
        total_score = sum(q["points_earned"] for q in question_results)
        total_time = sum(q["time_taken"] for q in question_results)
        grade_percentage = (correct_answers / total_questions * 100) if total_questions > 0 else 0
        accuracy = grade_percentage  # Accuracy is the same as grade percentage
        
        participant_result = {
            "user_id": user.id,
            "username": user.username,
            "email": user.email,
            "total_score": total_score,  # Use calculated score from answers
            "accuracy": round(accuracy, 1),  # Use calculated accuracy
            "time_taken": total_time,  # Use calculated time from answers
            "total_questions": total_questions,
            "correct_answers": correct_answers,
            "wrong_answers": total_questions - correct_answers,
            "grade_percentage": round(grade_percentage, 2),
            "grade_letter": _calculate_letter_grade(grade_percentage),
            "prize_won": participant.prize_won,
            "played_at": participant.played_at.isoformat() if participant.played_at else None,
            "question_results": question_results
        }
        
        participant_results.append(participant_result)
    
    # Sort by score (descending), then by correct answers, then by time (ascending for faster completion)
    participant_results.sort(key=lambda x: (-x["total_score"], -x["correct_answers"], x["time_taken"]))
    
    # Add ranks after sorting
    detailed_results = []
    for rank, result in enumerate(participant_results, 1):
        result["rank"] = rank
        detailed_results.append(result)
    
    return {
        "tournament": {
            "id": tournament.id,
            "title": tournament.title,
            "subject": tournament.subject,
            "difficulty": tournament.difficulty,
            "total_questions": tournament.questions_count,
            "time_limit": tournament.time_limit,
            "status": tournament.status
        },
        "results": detailed_results,
        "total_participants": len(detailed_results)
    }

def _calculate_letter_grade(percentage: float) -> str:
    """Calculate letter grade from percentage"""
    if percentage >= 90:
        return "A+"
    elif percentage >= 85:
        return "A"
    elif percentage >= 80:
        return "A-"
    elif percentage >= 75:
        return "B+"
    elif percentage >= 70:
        return "B"
    elif percentage >= 65:
        return "B-"
    elif percentage >= 60:
        return "C+"
    elif percentage >= 55:
        return "C"
    elif percentage >= 50:
        return "C-"
    elif percentage >= 45:
        return "D"
    else:
        return "F"

@router.get("/{tournament_id}/statistics")
async def get_tournament_statistics(
    tournament_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get tournament statistics - basic stats for all users, detailed for admins"""
    print(f"DEBUG: Tournament statistics requested for tournament {tournament_id} by user {current_user.username} (role: {current_user.role})")
    
    # Allow all users to access basic tournament statistics
    # Admin users get more detailed information
    
    tournament = db.query(Tournament).filter(Tournament.id == tournament_id).first()
    if not tournament:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tournament not found"
        )
    
    # Get statistics
    total_registered = db.query(TournamentParticipant).filter(
        TournamentParticipant.tournament_id == tournament_id
    ).count()
    
    total_played = db.query(TournamentParticipant).filter(
        TournamentParticipant.tournament_id == tournament_id,
        TournamentParticipant.has_played == True
    ).count()
    
    try:
        # Average statistics
        from sqlalchemy import func as sql_func
        avg_stats = db.query(
            sql_func.avg(TournamentParticipant.score).label('avg_score'),
            sql_func.avg(TournamentParticipant.accuracy).label('avg_accuracy'),
            sql_func.avg(TournamentParticipant.time_taken).label('avg_time')
        ).filter(
            TournamentParticipant.tournament_id == tournament_id,
            TournamentParticipant.has_played == True
        ).first()
        
        # Revenue calculation - handle missing columns gracefully
        try:
            total_revenue = db.query(sql_func.sum(TournamentParticipant.payment_amount)).filter(
                TournamentParticipant.tournament_id == tournament_id,
                TournamentParticipant.payment_status == "paid"
            ).scalar() or 0
        except Exception as e:
            print(f"Error calculating revenue: {e}")
            # Fallback if payment columns don't exist
            total_revenue = 0
        
        # Get top performers
        try:
            top_performers = db.query(TournamentParticipant).join(User).filter(
                TournamentParticipant.tournament_id == tournament_id,
                TournamentParticipant.has_played == True
            ).order_by(
                TournamentParticipant.score.desc(),
                TournamentParticipant.time_taken.asc()
            ).limit(10).all()
        except Exception as e:
            print(f"Error getting top performers: {e}")
            top_performers = []
        
        top_performers_data = []
        for participant in top_performers:
            try:
                top_performers_data.append({
                    "username": participant.user.username,
                    "score": participant.score or 0,
                    "accuracy": participant.accuracy or 0,
                    "time_taken": participant.time_taken or 0,
                    "prize_won": getattr(participant, 'prize_won', 0) or 0,
                    "rank": len(top_performers_data) + 1
                })
            except Exception as e:
                print(f"Error processing participant {participant.id}: {e}")
                continue
        
        return {
            "total_participants": total_registered,
            "completed_participants": total_played,
            "active_participants": total_registered - total_played,
            "completion_rate": (total_played / total_registered * 100) if total_registered > 0 else 0,
            "average_score": float(avg_stats.avg_score or 0) if avg_stats else 0,
            "average_accuracy": float(avg_stats.avg_accuracy or 0) if avg_stats else 0,
            "average_time": float(avg_stats.avg_time or 0) if avg_stats else 0,
            "highest_score": max([p.score or 0 for p in top_performers]) if top_performers else 0,
            "total_prize_pool": tournament.prize_pool or 0,
            "total_prizes_awarded": sum([getattr(p, 'prize_won', 0) or 0 for p in top_performers]),
            "total_entry_fees": total_revenue,
            "net_revenue": total_revenue - sum([getattr(p, 'prize_won', 0) or 0 for p in top_performers]),
            "tournament_status": tournament.status,
            "start_date": tournament.start_date.isoformat() if tournament.start_date else None,
            "registration_deadline": tournament.registration_deadline.isoformat() if tournament.registration_deadline else None,
            "top_performers": top_performers_data
        }
        
    except Exception as e:
        print(f"Error in tournament statistics: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating statistics: {str(e)}"
        )

