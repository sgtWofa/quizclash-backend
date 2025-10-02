"""
Audio Settings API for QuizClash Application
Handles database operations for user audio preferences
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any
from backend.database import get_db
from backend.audio_settings_model import UserAudioSettings
from backend.auth import get_current_user
from backend.models import User

router = APIRouter(prefix="/audio-settings", tags=["audio-settings"])


@router.get("/")
async def get_user_audio_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get current user's audio settings"""
    try:
        # Get user's audio settings from database
        audio_settings = db.query(UserAudioSettings).filter(
            UserAudioSettings.user_id == current_user.id
        ).first()
        
        if not audio_settings:
            # Create default settings if none exist
            default_settings = {
                "master_volume": 80,
                "sound_effects": True,
                "background_music": 50,
                "button_sounds": True,
                "notification_sounds": True,
                "voice_feedback": True,
                "voice_speed": 150,
                "voice_volume": 80,
                # Default category settings
                "category_level_upgrade_audio": "Default",
                "category_level_upgrade_volume": 80,
                "category_game_start_audio": "Default",
                "category_game_start_volume": 80,
                "category_gameplay_background_audio": "Default",
                "category_gameplay_background_volume": 80,
                "category_thinking_time_audio": "Default",
                "category_thinking_time_volume": 80,
                "category_correct_answer_audio": "Default",
                "category_correct_answer_volume": 80,
                "category_wrong_answer_audio": "Default",
                "category_wrong_answer_volume": 80,
                "category_game_victory_audio": "Default",
                "category_game_victory_volume": 80,
                "category_tournament_mode_audio": "Default",
                "category_tournament_mode_volume": 80,
                "category_menu_background_audio": "Default",
                "category_menu_background_volume": 80,
                "category_bonus_achievement_audio": "Default",
                "category_bonus_achievement_volume": 80
            }
            
            audio_settings = UserAudioSettings.from_dict(current_user.id, default_settings)
            db.add(audio_settings)
            db.commit()
            db.refresh(audio_settings)
        
        return {
            "status": "success",
            "settings": audio_settings.to_dict(),
            "profile_name": audio_settings.profile_name,
            "last_updated": audio_settings.last_updated.isoformat()
        }
        
    except Exception as e:
        print(f"Error getting audio settings: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get audio settings: {str(e)}")


@router.put("/")
async def update_user_audio_settings(
    settings: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Update user's audio settings"""
    try:
        # Get existing settings or create new
        audio_settings = db.query(UserAudioSettings).filter(
            UserAudioSettings.user_id == current_user.id
        ).first()
        
        if not audio_settings:
            # Create new settings
            audio_settings = UserAudioSettings.from_dict(current_user.id, settings)
            db.add(audio_settings)
        else:
            # Update existing settings
            audio_settings.master_volume = settings.get("master_volume", audio_settings.master_volume)
            audio_settings.sound_effects_enabled = settings.get("sound_effects", audio_settings.sound_effects_enabled)
            audio_settings.background_music_volume = settings.get("background_music", audio_settings.background_music_volume)
            audio_settings.button_sounds_enabled = settings.get("button_sounds", audio_settings.button_sounds_enabled)
            audio_settings.notification_sounds_enabled = settings.get("notification_sounds", audio_settings.notification_sounds_enabled)
            audio_settings.voice_feedback_enabled = settings.get("voice_feedback", audio_settings.voice_feedback_enabled)
            audio_settings.voice_speed = settings.get("voice_speed", audio_settings.voice_speed)
            audio_settings.voice_volume = settings.get("voice_volume", audio_settings.voice_volume)
            
            # Update category settings
            category_audio = {}
            category_volume = {}
            
            for key, value in settings.items():
                if key.startswith("category_") and key.endswith("_audio"):
                    category = key.replace("category_", "").replace("_audio", "")
                    category_audio[category] = value
                elif key.startswith("category_") and key.endswith("_volume"):
                    category = key.replace("category_", "").replace("_volume", "")
                    category_volume[category] = value
            
            if category_audio:
                audio_settings.category_audio_settings = category_audio
            if category_volume:
                audio_settings.category_volume_settings = category_volume
        
        db.commit()
        db.refresh(audio_settings)
        
        return {
            "status": "success",
            "message": "Audio settings updated successfully",
            "settings": audio_settings.to_dict()
        }
        
    except Exception as e:
        print(f"Error updating audio settings: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update audio settings: {str(e)}")


@router.post("/setting")
async def update_single_audio_setting(
    setting_data: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Update a single audio setting"""
    try:
        key = setting_data.get("key")
        value = setting_data.get("value")
        
        if not key:
            raise HTTPException(status_code=400, detail="Setting key is required")
        
        # Get existing settings or create new
        audio_settings = db.query(UserAudioSettings).filter(
            UserAudioSettings.user_id == current_user.id
        ).first()
        
        if not audio_settings:
            # Create with default settings and update the specific key
            default_settings = {key: value}
            audio_settings = UserAudioSettings.from_dict(current_user.id, default_settings)
            db.add(audio_settings)
        else:
            # Update specific setting
            if key == "master_volume":
                audio_settings.master_volume = value
            elif key == "sound_effects":
                audio_settings.sound_effects_enabled = value
            elif key == "background_music":
                audio_settings.background_music_volume = value
            elif key == "button_sounds":
                audio_settings.button_sounds_enabled = value
            elif key == "notification_sounds":
                audio_settings.notification_sounds_enabled = value
            elif key == "voice_feedback":
                audio_settings.voice_feedback_enabled = value
            elif key == "voice_speed":
                audio_settings.voice_speed = value
            elif key == "voice_volume":
                audio_settings.voice_volume = value
            elif key.startswith("category_") and key.endswith("_audio"):
                category = key.replace("category_", "").replace("_audio", "")
                if not audio_settings.category_audio_settings:
                    audio_settings.category_audio_settings = {}
                audio_settings.category_audio_settings[category] = value
            elif key.startswith("category_") and key.endswith("_volume"):
                category = key.replace("category_", "").replace("_volume", "")
                if not audio_settings.category_volume_settings:
                    audio_settings.category_volume_settings = {}
                audio_settings.category_volume_settings[category] = value
        
        db.commit()
        db.refresh(audio_settings)
        
        return {
            "status": "success",
            "message": f"Audio setting '{key}' updated successfully",
            "key": key,
            "value": value
        }
        
    except Exception as e:
        print(f"Error updating single audio setting: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update audio setting: {str(e)}")


@router.delete("/reset")
async def reset_audio_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Reset user's audio settings to defaults"""
    try:
        # Delete existing settings
        audio_settings = db.query(UserAudioSettings).filter(
            UserAudioSettings.user_id == current_user.id
        ).first()
        
        if audio_settings:
            db.delete(audio_settings)
            db.commit()
        
        return {
            "status": "success",
            "message": "Audio settings reset to defaults"
        }
        
    except Exception as e:
        print(f"Error resetting audio settings: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to reset audio settings: {str(e)}")
