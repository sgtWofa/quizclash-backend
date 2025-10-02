"""
Audio Settings Database Model for QuizClash Application
Stores user-specific audio preferences in the database
"""

from sqlalchemy import Column, Integer, String, ForeignKey, JSON, DateTime, Boolean, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from backend.database import Base


class UserAudioSettings(Base):
    """User-specific audio settings stored in database"""
    __tablename__ = "user_audio_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    
    # Master Audio Controls
    master_volume = Column(Integer, default=80)  # 0-100
    sound_effects_enabled = Column(Boolean, default=True)
    background_music_volume = Column(Integer, default=50)  # 0-100
    button_sounds_enabled = Column(Boolean, default=True)
    notification_sounds_enabled = Column(Boolean, default=True)
    
    # Voice Feedback Settings
    voice_feedback_enabled = Column(Boolean, default=True)
    voice_speed = Column(Integer, default=150)  # 50-300
    voice_volume = Column(Integer, default=80)  # 0-100
    
    # Activity-Specific Audio Settings (JSON for flexibility)
    category_audio_settings = Column(JSON, default={})
    category_volume_settings = Column(JSON, default={})
    
    # Audio Profile Metadata
    profile_name = Column(String(100), default="Default")
    last_updated = Column(DateTime, default=func.now(), onupdate=func.now())
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    user = relationship("User")
    
    def to_dict(self):
        """Convert to dictionary format compatible with audio manager"""
        base_settings = {
            "master_volume": self.master_volume,
            "sound_effects": self.sound_effects_enabled,
            "background_music": self.background_music_volume,
            "button_sounds": self.button_sounds_enabled,
            "notification_sounds": self.notification_sounds_enabled,
            "voice_feedback": self.voice_feedback_enabled,
            "voice_speed": self.voice_speed,
            "voice_volume": self.voice_volume,
        }
        
        # Add category-specific settings
        if self.category_audio_settings:
            for category, audio in self.category_audio_settings.items():
                base_settings[f"category_{category}_audio"] = audio
        
        if self.category_volume_settings:
            for category, volume in self.category_volume_settings.items():
                base_settings[f"category_{category}_volume"] = volume
                
        return base_settings
    
    @classmethod
    def from_dict(cls, user_id: int, settings_dict: dict):
        """Create from dictionary format"""
        category_audio = {}
        category_volume = {}
        
        # Extract category-specific settings
        for key, value in settings_dict.items():
            if key.startswith("category_") and key.endswith("_audio"):
                category = key.replace("category_", "").replace("_audio", "")
                category_audio[category] = value
            elif key.startswith("category_") and key.endswith("_volume"):
                category = key.replace("category_", "").replace("_volume", "")
                category_volume[category] = value
        
        return cls(
            user_id=user_id,
            master_volume=settings_dict.get("master_volume", 80),
            sound_effects_enabled=settings_dict.get("sound_effects", True),
            background_music_volume=settings_dict.get("background_music", 50),
            button_sounds_enabled=settings_dict.get("button_sounds", True),
            notification_sounds_enabled=settings_dict.get("notification_sounds", True),
            voice_feedback_enabled=settings_dict.get("voice_feedback", True),
            voice_speed=settings_dict.get("voice_speed", 150),
            voice_volume=settings_dict.get("voice_volume", 80),
            category_audio_settings=category_audio,
            category_volume_settings=category_volume
        )
