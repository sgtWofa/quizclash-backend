"""
Achievements API - Database operations for user achievements
Handles achievement unlocking, tracking, and powerup benefits
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
import requests
import time

from .database import get_db
from .auth import get_current_user
from .models import Achievement  # Use existing Achievement model

router = APIRouter()

@router.get("/achievements/user")
async def get_user_achievements(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all achievements for the current user"""
    try:
        user_id = current_user.id
        
        # Get user's achievements from database
        user_achievements = db.query(Achievement).filter(
            Achievement.user_id == user_id
        ).all()
        
        # Convert to list of dictionaries
        achievements_list = []
        for achievement in user_achievements:
            achievements_list.append({
                "id": achievement.id,
                "name": achievement.name,
                "description": achievement.description or f"Achievement: {achievement.name}",
                "unlocked_at": achievement.unlocked_at.isoformat() if achievement.unlocked_at else None,
                "category": "General"  # You can enhance this with categories later
            })
        
        print(f"DEBUG: Returning {len(achievements_list)} achievements for user {user_id}")
        return achievements_list
        
    except Exception as e:
        print(f"ERROR: Failed to get user achievements: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve achievements")

# Simple cache for user stats to avoid repeated calculations
_user_stats_cache = {}
_cache_timeout = 60  # 60 seconds

def _get_user_stats_sync(user_id: int, db: Session) -> dict:
    """Get user statistics synchronously for achievement evaluation"""
    try:
        # Check cache first
        cache_key = f"user_stats_{user_id}"
        current_time = time.time()
        
        if cache_key in _user_stats_cache:
            cached_data, cache_time = _user_stats_cache[cache_key]
            if current_time - cache_time < _cache_timeout:
                return cached_data
        
        from .models import User, GameSession
        from sqlalchemy import func
        
        # Get user
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {}
        
        # Use aggregated queries for better performance
        from sqlalchemy import func
        
        stats_query = db.query(
            func.count(GameSession.id).label('total_games'),
            func.sum(GameSession.total_score).label('total_score'),
            func.max(GameSession.total_score).label('best_score'),
            func.count(GameSession.id).filter(GameSession.total_score > 0).label('games_won')
        ).filter(
            GameSession.user_id == user_id,
            GameSession.is_completed == True
        ).first()
        
        if not stats_query or stats_query.total_games == 0:
            return {
                "games_played": 0,
                "total_score": 0,
                "best_score": 0,
                "games_won": 0,
                "win_rate": 0,
                "avg_score": 0
            }
        
        total_games = stats_query.total_games or 0
        total_score = stats_query.total_score or 0
        best_score = stats_query.best_score or 0
        games_won = stats_query.games_won or 0
        win_rate = (games_won / total_games * 100) if total_games > 0 else 0
        avg_score = total_score / total_games if total_games > 0 else 0
        
        result = {
            "games_played": total_games,
            "total_score": total_score,
            "best_score": best_score,
            "games_won": games_won,
            "win_rate": win_rate,
            "avg_score": avg_score
        }
        
        # Cache the result
        _user_stats_cache[cache_key] = (result, current_time)
        
        return result
        
    except Exception as e:
        print(f"ERROR: Failed to get user stats: {e}")
        return {}

# Achievement definitions with powerup benefits
ACHIEVEMENT_DEFINITIONS = {
    # Basic Achievements
    "first_steps": {
        "name": "🎮 First Steps",
        "description": "Complete your first quiz game",
        "category": "gameplay",
        "requirement_value": 1,
        "badge_icon": "🎮",
        "powerup_benefits": {
            "extra_time": 5,  # +5 seconds bonus time
        }
    },
    "getting_started": {
        "name": "🔥 Getting Started", 
        "description": "Play 10 games",
        "category": "gameplay",
        "requirement_value": 10,
        "badge_icon": "🔥",
        "powerup_benefits": {
            "double_hint": True,  # Voice hint gives 2 eliminated answers
        }
    },
    "century_club": {
        "name": "💯 Century Club",
        "description": "Score 100+ points in a single game",
        "category": "performance",
        "requirement_value": 100,
        "badge_icon": "💯",
        "powerup_benefits": {
            "score_multiplier": 1.1,  # 10% score bonus
        }
    },
    "perfectionist": {
        "name": "🎯 Perfectionist",
        "description": "Achieve 100% accuracy in a game",
        "category": "performance", 
        "requirement_value": 100,
        "badge_icon": "🎯",
        "powerup_benefits": {
            "perfect_streak_bonus": 50,  # +50 points for perfect games
        }
    },
    "speed_demon": {
        "name": "⚡ Speed Demon",
        "description": "Answer all questions in under 30 seconds total",
        "category": "performance",
        "requirement_value": 30,
        "badge_icon": "⚡",
        "powerup_benefits": {
            "time_freeze": True,  # Can freeze timer for 10 seconds
        }
    },
    "sharpshooter": {
        "name": "🏹 Sharpshooter",
        "description": "Maintain 80%+ win rate over 10+ games",
        "category": "performance",
        "requirement_value": 80,
        "badge_icon": "🏹",
        "powerup_benefits": {
            "lucky_guess": True,  # 50% chance to auto-correct wrong answers
        }
    },
    
    # Advanced Achievements
    "quiz_master": {
        "name": "🎓 Quiz Master",
        "description": "Play 50 games",
        "category": "gameplay",
        "requirement_value": 50,
        "badge_icon": "🎓",
        "powerup_benefits": {
            "master_hint": True,  # Voice hint reveals correct answer directly
            "extra_powerups": 1,  # +1 additional powerup per game
        }
    },
    "high_scorer": {
        "name": "🚀 High Scorer",
        "description": "Score 500+ points in a single game",
        "category": "performance",
        "requirement_value": 500,
        "badge_icon": "🚀",
        "powerup_benefits": {
            "score_multiplier": 1.25,  # 25% score bonus
            "bonus_points": 100,  # +100 points per game
        }
    },
    "legend": {
        "name": "👑 Legend",
        "description": "Score 1000+ points in a single game",
        "category": "performance", 
        "requirement_value": 1000,
        "badge_icon": "👑",
        "powerup_benefits": {
            "score_multiplier": 1.5,  # 50% score bonus
            "all_powerups": True,  # Access to all powerups
            "unlimited_hints": True,  # Unlimited voice hints
        }
    },
    "tournament_champion": {
        "name": "🏆 Tournament Champion",
        "description": "Win 5 tournaments",
        "category": "tournament",
        "requirement_value": 5,
        "badge_icon": "🏆",
        "powerup_benefits": {
            "champion_aura": True,  # 20% score bonus in tournaments
            "pressure_immunity": True,  # No time pressure effects
        }
    }
}

@router.post("/achievements/evaluate")
async def evaluate_achievements(
    game_data: dict,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Evaluate and unlock new achievements based on game performance"""
    import asyncio
    import time
    
    try:
        start_time = time.time()
        timeout_seconds = 8  # 8-second timeout
        user_id = current_user.id
        new_achievements = []
        
        # Get existing achievements for this user
        existing_achievements = db.query(Achievement).filter(
            Achievement.user_id == user_id
        ).all()
        existing_names = {ach.name for ach in existing_achievements}
        
        # Get user stats for evaluation with timeout protection
        try:
            user_stats = _get_user_stats_sync(user_id, db)
        except Exception as e:
            print(f"ERROR: Failed to get user stats: {e}")
            return {"new_achievements": [], "error": "Failed to get user stats"}
        
        # Evaluate only essential achievements to prevent timeout
        processed_count = 0
        max_achievements_to_check = 5  # Reduced limit to prevent timeout
        
        # Priority achievements to check first
        priority_achievements = ["first_steps", "century_club", "perfectionist", "high_scorer", "legend"]
        
        for achievement_id in priority_achievements:
            # Check timeout
            if time.time() - start_time > timeout_seconds:
                print("WARNING: Achievement evaluation timeout reached")
                break
            if processed_count >= max_achievements_to_check:
                break
            if achievement_id not in ACHIEVEMENT_DEFINITIONS:
                continue
            processed_count += 1
            definition = ACHIEVEMENT_DEFINITIONS[achievement_id]
            achievement_name = definition["name"]
            
            # Skip if already unlocked
            if achievement_name in existing_names:
                continue
                
            # Check if achievement should be unlocked
            should_unlock = False
            
            if achievement_id == "first_steps":
                should_unlock = user_stats.get("games_played", 0) >= 1
            elif achievement_id == "getting_started":
                should_unlock = user_stats.get("games_played", 0) >= 10
            elif achievement_id == "century_club":
                should_unlock = game_data.get("total_score", 0) >= 100
            elif achievement_id == "perfectionist":
                should_unlock = game_data.get("accuracy", 0) >= 100
            elif achievement_id == "speed_demon":
                should_unlock = game_data.get("time_spent", 999) <= 30
            elif achievement_id == "sharpshooter":
                should_unlock = (user_stats.get("games_played", 0) >= 10 and 
                               user_stats.get("win_rate", 0) >= 80)
            elif achievement_id == "quiz_master":
                should_unlock = user_stats.get("games_played", 0) >= 50
            elif achievement_id == "high_scorer":
                should_unlock = game_data.get("total_score", 0) >= 500
            elif achievement_id == "legend":
                should_unlock = game_data.get("total_score", 0) >= 1000
            elif achievement_id == "tournament_champion":
                # This would need tournament stats
                should_unlock = False  # Implement when tournament stats are available
                
            if should_unlock:
                # Create new achievement
                new_achievement = Achievement(
                    user_id=user_id,
                    name=definition["name"],
                    description=definition["description"],
                    badge_icon=definition["badge_icon"],
                    category=definition["category"],
                    requirement_value=definition["requirement_value"],
                    unlocked_at=datetime.utcnow()
                )
                db.add(new_achievement)
                new_achievements.append({
                    "id": achievement_id,
                    "name": definition["name"],
                    "description": definition["description"],
                    "badge_icon": definition["badge_icon"],
                    "category": definition["category"],
                    "powerup_benefits": definition.get("powerup_benefits", {})
                })
        
        db.commit()
        
        return {
            "new_achievements": new_achievements,
            "total_achievements": len(existing_achievements) + len(new_achievements)
        }
        
    except Exception as e:
        print(f"ERROR: Achievement evaluation failed: {e}")
        db.rollback()
        # Return success with empty results instead of raising exception
        return {"new_achievements": [], "error": str(e)}

@router.get("/achievements/user/{user_id}")
async def get_user_achievements(
    user_id: int,
    db: Session = Depends(get_db)
):
    """Get all achievements for a specific user"""
    try:
        achievements = db.query(Achievement).filter(
            Achievement.user_id == user_id
        ).all()
        
        result = []
        for achievement in achievements:
            # Find the definition to get powerup benefits
            achievement_def = None
            for def_id, definition in ACHIEVEMENT_DEFINITIONS.items():
                if definition["name"] == achievement.name:
                    achievement_def = definition
                    break
            
            result.append({
                "id": achievement.id,
                "name": achievement.name,
                "description": achievement.description,
                "badge_icon": achievement.badge_icon,
                "category": achievement.category,
                "requirement_value": achievement.requirement_value,
                "unlocked_at": achievement.unlocked_at.isoformat(),
                "powerup_benefits": achievement_def.get("powerup_benefits", {}) if achievement_def else {}
            })
        
        return {"achievements": result}
        
    except Exception as e:
        print(f"ERROR: Failed to get user achievements: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get achievements: {str(e)}")

@router.get("/achievements/benefits/{user_id}")
async def get_user_powerup_benefits(
    user_id: int,
    db: Session = Depends(get_db)
):
    """Get all powerup benefits unlocked by user's achievements"""
    try:
        achievements = db.query(Achievement).filter(
            Achievement.user_id == user_id
        ).all()
        
        # Aggregate all powerup benefits
        benefits = {
            "score_multiplier": 1.0,
            "bonus_points": 0,
            "extra_time": 0,
            "extra_powerups": 0,
            "double_hint": False,
            "master_hint": False,
            "time_freeze": False,
            "lucky_guess": False,
            "all_powerups": False,
            "unlimited_hints": False,
            "perfect_streak_bonus": 0,
            "champion_aura": False,
            "pressure_immunity": False
        }
        
        for achievement in achievements:
            # Find the definition to get powerup benefits
            for def_id, definition in ACHIEVEMENT_DEFINITIONS.items():
                if definition["name"] == achievement.name:
                    powerup_benefits = definition.get("powerup_benefits", {})
                    
                    # Aggregate benefits
                    for benefit, value in powerup_benefits.items():
                        if benefit == "score_multiplier":
                            benefits[benefit] = max(benefits[benefit], value)
                        elif benefit in ["bonus_points", "extra_time", "extra_powerups", "perfect_streak_bonus"]:
                            benefits[benefit] += value
                        else:
                            benefits[benefit] = benefits[benefit] or value
                    break
        
        return {"benefits": benefits}
        
    except Exception as e:
        print(f"ERROR: Failed to get powerup benefits: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get benefits: {str(e)}")

@router.get("/achievements/test/{user_id}")
async def test_achievements(user_id: int, db: Session = Depends(get_db)):
    """Test achievement system for a specific user"""
    try:
        user_stats = _get_user_stats_sync(user_id, db)
        return {
            "user_id": user_id,
            "user_stats": user_stats,
            "cache_info": f"Cache has {len(_user_stats_cache)} entries"
        }
    except Exception as e:
        return {"error": str(e)}

@router.get("/achievements/available")
async def get_available_achievements():
    """Get all available achievements and their requirements"""
    try:
        available = []
        for achievement_id, definition in ACHIEVEMENT_DEFINITIONS.items():
            available.append({
                "id": achievement_id,
                "name": definition["name"],
                "description": definition["description"],
                "badge_icon": definition["badge_icon"],
                "category": definition["category"],
                "requirement_value": definition["requirement_value"],
                "powerup_benefits": definition.get("powerup_benefits", {})
            })
        
        return {"available_achievements": available}
        
    except Exception as e:
        print(f"ERROR: Failed to get available achievements: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get available achievements: {str(e)}")
