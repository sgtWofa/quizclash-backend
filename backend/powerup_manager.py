"""
Powerup Manager - Handles powerup logic and state management
"""

class PowerupManager:
    """Manages powerup availability and effects"""
    
    def __init__(self):
        self.active_effects = {}
        self.powerup_counts = {
            "fifty_fifty": 10,
            "voice_hint": 10,
            "time_boost": 10
        }
    
    def has_active_effect(self, effect_name):
        """Check if a powerup effect is currently active"""
        return effect_name in self.active_effects
    
    def consume_effect(self, effect_name):
        """Consume/remove an active effect"""
        if effect_name in self.active_effects:
            del self.active_effects[effect_name]
    
    def activate_powerup(self, powerup_name):
        """Activate a powerup if available"""
        if self.powerup_counts.get(powerup_name, 0) > 0:
            self.powerup_counts[powerup_name] -= 1
            self.active_effects[powerup_name] = True
            return True
        return False
    
    def reset_powerups(self):
        """Reset powerups for new game"""
        self.active_effects.clear()
        self.powerup_counts = {
            "fifty_fifty": 10,
            "voice_hint": 10,
            "time_boost": 10
        }
    
    def get_powerup_count(self, powerup_name):
        """Get remaining count for a powerup"""
        return self.powerup_counts.get(powerup_name, 0)

# Global instance
powerup_manager = PowerupManager()
