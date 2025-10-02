"""
Audio Manager for QuizClash Application
Handles all audio settings, playback, and voice feedback functionality
"""

import json
import os
import threading
from typing import Dict, Optional, Callable
import pygame
import pyttsx3
from pathlib import Path


class AudioManager:
    """Centralized audio management system for the QuizClash application"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(AudioManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        
        # Settings cache to prevent excessive database calls
        self._settings_cache = None
        self._cache_timestamp = 0
        self._cache_duration = 300  # Cache for 5 minutes for better performance
        
        # Audio settings
        self.settings_file = "app_settings.json"
        self.current_user_id = None  # Track current user for database integration
        
        # Handle PyInstaller bundled path with multiple fallbacks
        import sys
        self.assets_path = None
        
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            # Running as PyInstaller bundle - try multiple potential paths
            potential_paths = [
                Path(sys._MEIPASS) / "assets",
                Path(sys._MEIPASS),
                Path(sys.executable).parent / "assets",
                Path.cwd() / "assets"
            ]
            
            print(f"DEBUG: PyInstaller detected - trying asset paths:")
            for path in potential_paths:
                print(f"DEBUG: Trying: {path} (exists: {path.exists()})")
                if path.exists():
                    self.assets_path = path
                    print(f"DEBUG: Using assets path: {self.assets_path}")
                    if (path / "music").exists() or (path / "sound effects").exists():
                        print(f"DEBUG: Found audio directories in: {path}")
                        break
                    else:
                        print(f"DEBUG: No audio directories found in: {path}")
        
        if self.assets_path is None:
            # Fallback to local assets
            self.assets_path = Path("assets")
            print(f"DEBUG: Using fallback assets path: {self.assets_path}")
        
        print(f"DEBUG: Final assets path: {self.assets_path}")
        print(f"DEBUG: Assets path exists: {self.assets_path.exists()}")
        if self.assets_path.exists():
            print(f"DEBUG: Assets contents: {list(self.assets_path.iterdir())}")
        
        # Initialize pygame mixer for audio playback
        pygame.mixer.pre_init(frequency=22050, size=-16, channels=2, buffer=512)
        pygame.mixer.init()
        
        # Audio settings with defaults - MUST be defined before _load_settings()
        self.default_settings = {
            "master_volume": 80,
            "sound_effects": True,
            "background_music": 50,
            "button_sounds": True,
            "voice_feedback": True,
            "notification_sounds": True,
            "voice_speed": 150,
            "voice_volume": 80,
            # Category-specific audio settings
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
        
        # Load current settings AFTER default_settings is defined
        self.settings = self._load_settings()
        
        # Initialize text-to-speech engine AFTER settings are loaded
        self.tts_engine = None
        self._init_tts()
        
        # Audio channels
        self.music_channel = None
        self.sfx_channels = []
        
        # Music context tracking for resume functionality
        self._current_music_context = None
        self._previous_music_context = None
        
        # Preloaded sounds cache
        self.sound_cache = {}
        self._preload_sounds()
        
        # Apply initial volume settings
        self._apply_volume_settings()
    
    def _init_tts(self):
        """Initialize TTS engine with enhanced PyInstaller compatibility"""
        try:
            import pyttsx3
            
            # Try multiple TTS drivers for better compatibility
            drivers = ['sapi5', 'espeak', 'nsss']  # Windows, Linux, macOS
            
            for driver in drivers:
                try:
                    print(f"DEBUG: Trying TTS driver: {driver}")
                    self.tts_engine = pyttsx3.init(driver)
                    
                    # Test the engine with a simple phrase
                    voices = self.tts_engine.getProperty('voices')
                    if voices:
                        print(f"DEBUG: TTS driver {driver} initialized with {len(voices)} voices")
                        # Set a clear voice if available
                        for voice in voices:
                            if 'english' in voice.name.lower() or 'david' in voice.name.lower() or 'zira' in voice.name.lower():
                                self.tts_engine.setProperty('voice', voice.id)
                                print(f"DEBUG: Selected voice: {voice.name}")
                                break
                        else:
                            # If no preferred voice found, use first available
                            self.tts_engine.setProperty('voice', voices[0].id)
                            print(f"DEBUG: Using default voice: {voices[0].name}")
                        break
                    else:
                        print(f"DEBUG: No voices available for driver {driver}")
                        continue
                        
                except Exception as driver_error:
                    print(f"DEBUG: Driver {driver} failed: {driver_error}")
                    continue
            
            if not hasattr(self, 'tts_engine') or self.tts_engine is None:
                # Fallback to default initialization
                self.tts_engine = pyttsx3.init()
            
            print("DEBUG: TTS engine initialized successfully")
        except Exception as e:
            print(f"Failed to initialize TTS engine: {e}")
            self.tts_engine = None
    
    def _load_settings(self, force_reload: bool = False) -> Dict:
        """Load audio settings prioritizing JSON file for performance"""
        try:
            import time
            current_time = time.time()
            
            # Check cache first (unless force reload)
            if not force_reload and self._settings_cache and (current_time - self._cache_timestamp) < self._cache_duration:
                return self._settings_cache
            
            # Load from file first for better performance
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    data = json.load(f)
                    loaded_settings = data.get('audio', self.default_settings.copy())
                    
                    # Fix boolean settings that might be stored as integers or strings
                    boolean_keys = ['sound_effects', 'button_sounds', 'notification_sounds', 'voice_feedback']
                    for key in boolean_keys:
                        if key in loaded_settings:
                            value = loaded_settings[key]
                            if isinstance(value, int):
                                loaded_settings[key] = value > 0
                            elif isinstance(value, str):
                                loaded_settings[key] = value.lower() in ('true', '1', 'yes', 'on')
                            elif value is None:
                                loaded_settings[key] = True  # Default to enabled
                    
                    # Ensure minimum volume levels
                    if loaded_settings.get('master_volume', 0) < 10:
                        loaded_settings['master_volume'] = 80
                    
                    # Merge with defaults to ensure all keys exist
                    merged_settings = self.default_settings.copy()
                    merged_settings.update(loaded_settings)
                    
                    # Cache the file-based settings too
                    self._settings_cache = merged_settings
                    self._cache_timestamp = current_time
                    
                    return merged_settings
        
            # Return defaults and cache them
            default_settings = self.default_settings.copy()
            self._settings_cache = default_settings
            self._cache_timestamp = current_time
            return default_settings
        except Exception as e:
            print(f"Error loading audio settings: {e}")
            return self.default_settings.copy()
    
    def _save_settings(self):
        """Save audio settings to file first, then sync to database"""
        try:
            import time
            
            # Update cache immediately
            self._settings_cache = self.settings.copy()
            self._cache_timestamp = time.time()
            
            # Save to file first for immediate performance
            app_settings = {}
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    app_settings = json.load(f)
            
            # Update audio section
            app_settings['audio'] = self.settings
            
            with open(self.settings_file, 'w') as f:
                json.dump(app_settings, f, indent=2)
            
            print("DEBUG: Audio settings saved to file successfully")
            
            # Optional: sync to database in background (non-blocking)
            if self.current_user_id:
                try:
                    import requests
                    import threading
                    
                    def sync_to_database():
                        try:
                            token = self._get_auth_token()
                            if token:
                                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                                response = requests.put(
                                    "http://localhost:8000/audio-settings/", 
                                    json=self.settings,
                                    headers=headers,
                                    timeout=2
                                )
                                if response.status_code == 200:
                                    print("DEBUG: Audio settings synced to database")
                        except:
                            pass  # Silent fail for background sync
                    
                    # Run database sync in background thread
                    threading.Thread(target=sync_to_database, daemon=True).start()
                except:
                    pass  # Silent fail if threading not available
            
        except Exception as e:
            print(f"Error saving audio settings: {e}")
    
    def _preload_sounds(self):
        """Preload commonly used sound effects"""
        sound_effects_path = self.assets_path / "sound effects"
        
        print(f"DEBUG: Looking for sounds in: {sound_effects_path}")
        print(f"DEBUG: Assets path exists: {sound_effects_path.exists()}")
        
        if sound_effects_path.exists():
            print(f"DEBUG: Sound files found: {list(sound_effects_path.glob('*.ogg'))}")
        
        sound_mappings = {
            "button_click": "button-394464.ogg",
            "success": "clear-combo-7-394494.ogg",
            "bonus": "game-bonus-02-294436.ogg",
            "character": "game-character-140506.ogg",
            "fail": "game-fail-90322.ogg",
            "game_start": "game-start-317318.ogg",
            "combo": "clear-combo-8-394509.ogg"
        }
        
        for sound_name, filename in sound_mappings.items():
            try:
                sound_path = sound_effects_path / filename
                print(f"DEBUG: Checking sound {sound_name} at {sound_path}")
                if sound_path.exists():
                    self.sound_cache[sound_name] = pygame.mixer.Sound(str(sound_path))
                    print(f"DEBUG: Successfully loaded {sound_name}")
                else:
                    print(f"DEBUG: Sound file not found: {sound_path}")
            except Exception as e:
                print(f"Failed to load sound {sound_name}: {e}")
        
        print(f"DEBUG: Final sound cache: {list(self.sound_cache.keys())}")
    
    def _apply_volume_settings(self):
        """Apply current volume settings to all audio channels"""
        master_vol = self.settings.get('master_volume', 70) / 100.0
        
        # Set music volume
        if self.settings.get('background_music', 50) > 0:
            music_vol = (self.settings.get('background_music', 50) / 100.0) * master_vol
            pygame.mixer.music.set_volume(music_vol)
        
        # Set sound effects volume - ensure it's audible
        sfx_enabled = self.settings.get('sound_effects', True)
        if isinstance(sfx_enabled, int):
            sfx_enabled = sfx_enabled > 0
        
        sfx_vol = master_vol if sfx_enabled else 0
        
        # Ensure minimum audible volume
        if sfx_vol > 0 and sfx_vol < 0.1:
            sfx_vol = 0.3  # Set minimum audible volume
        
        for sound in self.sound_cache.values():
            sound.set_volume(sfx_vol)
        
        print(f"DEBUG: Applied volumes - Master: {master_vol:.2f}, SFX: {sfx_vol:.2f}, SFX Enabled: {sfx_enabled}")
    
    # Public API Methods
    
    def update_setting(self, key: str, value) -> bool:
        """Update a specific audio setting"""
        try:
            self.settings[key] = value
            self._save_settings()
            self._apply_volume_settings()
            
            # Update TTS settings if needed
            if key == 'voice_speed' and self.tts_engine:
                self.tts_engine.setProperty('rate', value)
            elif key == 'voice_volume' and self.tts_engine:
                self.tts_engine.setProperty('volume', value / 100.0)
            
            return True
        except Exception as e:
            print(f"Error updating audio setting {key}: {e}")
            return False
    
    def get_setting(self, key: str, default=None):
        """Get a specific audio setting"""
        return self.settings.get(key, default)
    
    def get_all_settings(self) -> Dict:
        """Get all audio settings"""
        return self.settings.copy()
    
    def play_sound_effect(self, sound_name: str, volume_override: Optional[float] = None):
        """Play a sound effect"""
        # Force immediate output
        import sys
        print(f"DEBUG: play_sound_effect called with {sound_name}", flush=True)
        sys.stdout.flush()
        
        sfx_enabled = self.settings.get('sound_effects', True)
        if isinstance(sfx_enabled, int):
            sfx_enabled = sfx_enabled > 0
        
        print(f"DEBUG: Sound effects enabled: {sfx_enabled}", flush=True)
        sys.stdout.flush()
        
        if not sfx_enabled:
            print(f"DEBUG: Sound effects disabled, skipping {sound_name}", flush=True)
            return
        
        print(f"DEBUG: Sound cache contents: {list(self.sound_cache.keys())}", flush=True)
        sys.stdout.flush()
        
        try:
            if sound_name in self.sound_cache:
                print(f"DEBUG: Found {sound_name} in cache", flush=True)
                sound = self.sound_cache[sound_name]
                
                if volume_override is not None:
                    final_volume = volume_override * (self.settings.get('master_volume', 70) / 100.0)
                else:
                    master_vol = self.settings.get('master_volume', 70) / 100.0
                    final_volume = master_vol
                
                # Ensure minimum audible volume
                if final_volume > 0 and final_volume < 0.1:
                    final_volume = 0.5  # Increased minimum volume
                
                print(f"DEBUG: Setting volume to {final_volume:.2f}", flush=True)
                sound.set_volume(final_volume)
                
                print(f"DEBUG: About to play sound...", flush=True)
                sound.play()
                print(f"DEBUG: Successfully played {sound_name} at volume {final_volume:.2f}", flush=True)
            else:
                print(f"DEBUG: Sound {sound_name} not found in cache. Available: {list(self.sound_cache.keys())}", flush=True)
        except Exception as e:
            print(f"ERROR: Exception in play_sound_effect: {e}", flush=True)
            import traceback
            traceback.print_exc()
    
    def play_button_sound(self):
        """Play button click sound"""
        try:
            button_sounds_enabled = self.settings.get('button_sounds', True)
            if isinstance(button_sounds_enabled, int):
                button_sounds_enabled = button_sounds_enabled > 0
            
            print(f"DEBUG: Button sounds enabled: {button_sounds_enabled}")
            
            if button_sounds_enabled:
                # Direct sound playback bypass
                if 'button_click' in self.sound_cache:
                    sound = self.sound_cache['button_click']
                    master_vol = self.settings.get('master_volume', 70) / 100.0
                    final_volume = max(0.5, master_vol)  # Ensure audible volume
                    sound.set_volume(final_volume)
                    sound.play()
                    print(f"DEBUG: Direct button sound played at volume {final_volume:.2f}")
                else:
                    print(f"DEBUG: button_click not found in cache: {list(self.sound_cache.keys())}")
            else:
                print("DEBUG: Button sounds disabled, skipping")
        except Exception as e:
            print(f"ERROR: Exception in play_button_sound: {e}")
            import traceback
            traceback.print_exc()
    
    def play_notification_sound(self, sound_type: str = 'success'):
        """Play notification sound"""
        notification_sounds_enabled = self.settings.get('notification_sounds', True)
        if isinstance(notification_sounds_enabled, int):
            notification_sounds_enabled = notification_sounds_enabled > 0
            
        if not notification_sounds_enabled:
            print(f"DEBUG: Notification sounds disabled")
            return
        
        sound_map = {
            'success': 'success',
            'error': 'fail',
            'warning': 'character',
            'info': 'bonus'
        }
        
        sound_name = sound_map.get(sound_type, 'success')
        
        # Direct sound playback bypass
        try:
            if sound_name in self.sound_cache:
                sound = self.sound_cache[sound_name]
                master_vol = self.settings.get('master_volume', 70) / 100.0
                final_volume = max(0.5, master_vol)  # Ensure audible volume
                sound.set_volume(final_volume)
                sound.play()
                print(f"DEBUG: Direct notification sound '{sound_type}' ({sound_name}) played at volume {final_volume:.2f}")
            else:
                print(f"DEBUG: Notification sound '{sound_name}' not found in cache: {list(self.sound_cache.keys())}")
        except Exception as e:
            print(f"ERROR: Exception playing notification sound: {e}")
            import traceback
            traceback.print_exc()
    
    def start_background_music(self, music_file: Optional[str] = None):
        """Start background music"""
        if self.settings.get('background_music', 50) == 0:
            return
        
        try:
            if music_file is None:
                # Use selected music or default random selection
                selected_music = self.settings.get('selected_music', 'Default')
                if selected_music != 'Default':
                    # Find the selected music file
                    music_path = self.assets_path / "music"
                    for file in music_path.glob("*.ogg"):
                        display_name = file.stem.replace(" (freetouse.com)", "")
                        if display_name == selected_music:
                            music_file = str(file)
                            break
                
                if music_file is None:
                    # Select random music from assets
                    music_path = self.assets_path / "music"
                    music_files = list(music_path.glob("*.ogg"))
                    if music_files:
                        import random
                        music_file = str(random.choice(music_files))
            
            if music_file and os.path.exists(music_file):
                pygame.mixer.music.load(music_file)
                pygame.mixer.music.play(-1)  # Loop indefinitely
                self._apply_volume_settings()
        except Exception as e:
            print(f"Error playing background music: {e}")
    
    def stop_background_music(self):
        """Stop background music"""
        try:
            pygame.mixer.music.stop()
        except Exception as e:
            print(f"Error stopping background music: {e}")
    
    def speak_text(self, text: str, priority: bool = False):
        """Speak text using TTS with enhanced PyInstaller compatibility and gameplay focus"""
        # Force reload settings to ensure we have the latest voice_feedback setting
        self.settings = self._load_settings()
        
        voice_feedback_enabled = self.settings.get('voice_feedback', True)
        print(f"DEBUG: Voice feedback setting: {voice_feedback_enabled} (type: {type(voice_feedback_enabled)})")
        
        if not voice_feedback_enabled:
            print(f"DEBUG: Voice feedback disabled, skipping TTS for: {text}")
            return
        
        print(f"DEBUG: Attempting TTS for text: {text}")
        
        # Enhanced gameplay voice feedback - force enable for critical game events
        gameplay_keywords = ['correct', 'wrong', 'question', 'game', 'score', 'level', 'achievement']
        is_gameplay = any(keyword in text.lower() for keyword in gameplay_keywords)
        
        if is_gameplay or priority:
            print(f"DEBUG: Priority/gameplay TTS - forcing speech for: {text}")
        
        # Enhanced TTS with better error handling for PyInstaller
        try:
            if self.tts_engine is None:
                print(f"DEBUG: TTS engine not initialized, attempting reinit...")
                self._init_tts()
            
            if self.tts_engine:
                print(f"DEBUG: TTS engine available, speaking text")
                
                # Enhanced TTS solution with gameplay priority
                try:
                    import tempfile
                    import os
                    import time
                    
                    # For gameplay events, use multiple methods simultaneously for reliability
                    if is_gameplay or priority:
                        # Method 1: Direct Windows SAPI COM interface (highest priority)
                        success = self._try_windows_sapi_direct(text)
                        
                        # Method 2: Parallel audio file generation for backup
                        if not success:
                            success = self._try_audio_file_tts(text)
                        
                        # Method 3: System command fallback
                        if not success:
                            success = self._try_system_tts(text)
                    else:
                        # For non-gameplay, use standard approach
                        success = self._try_windows_sapi_direct(text)
                        if not success:
                            success = self._try_system_tts(text)
                    
                    if success:
                        print(f"DEBUG: TTS completed successfully for: '{text}'")
                    else:
                        print(f"DEBUG: All TTS methods failed for: '{text}'")
                        
                except Exception as tts_error:
                    print(f"DEBUG: Enhanced TTS error: {tts_error}")
            else:
                print(f"DEBUG: TTS engine unavailable after reinit attempt")
        except Exception as e:
            print(f"Error in text-to-speech: {e}")
            import traceback
            traceback.print_exc()
    
    def _try_windows_sapi_direct(self, text: str) -> bool:
        """Try direct Windows SAPI COM interface"""
        try:
            import win32com.client
            
            # Lower music volume
            original_volume = pygame.mixer.music.get_volume()
            pygame.mixer.music.set_volume(0.1)
            
            # Create SAPI voice object directly
            voice = win32com.client.Dispatch("SAPI.SpVoice")
            
            # Set voice properties
            voice.Rate = 2  # Moderate speed
            voice.Volume = 100  # Maximum volume
            
            # Get available voices and select a good one
            voices = voice.GetVoices()
            for i in range(voices.Count):
                voice_info = voices.Item(i)
                if 'david' in voice_info.GetDescription().lower() or 'zira' in voice_info.GetDescription().lower():
                    voice.Voice = voice_info
                    print(f"DEBUG: SAPI Direct using: {voice_info.GetDescription()}")
                    break
            
            # Speak the text
            print(f"DEBUG: SAPI Direct speaking: '{text}'")
            voice.Speak(text, 0)  # 0 = synchronous
            
            # Restore music volume
            pygame.mixer.music.set_volume(original_volume)
            
            return True
            
        except Exception as e:
            print(f"DEBUG: SAPI Direct failed: {e}")
            try:
                pygame.mixer.music.set_volume(original_volume)
            except:
                pass
            return False
    
    def _try_audio_file_tts(self, text: str) -> bool:
        """Generate TTS audio file and play through pygame"""
        try:
            import tempfile
            import pyttsx3
            
            # Create temporary file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_path = temp_file.name
            
            # Generate audio file
            engine = pyttsx3.init('sapi5')
            engine.setProperty('rate', 150)
            engine.setProperty('volume', 1.0)
            
            # Select voice
            voices = engine.getProperty('voices')
            if voices:
                for voice in voices:
                    if 'david' in voice.name.lower() or 'zira' in voice.name.lower():
                        engine.setProperty('voice', voice.id)
                        break
            
            # Save to file
            engine.save_to_file(text, temp_path)
            engine.runAndWait()
            engine.stop()
            
            # Play through pygame
            if os.path.exists(temp_path):
                # Lower music volume
                original_volume = pygame.mixer.music.get_volume()
                pygame.mixer.music.set_volume(0.1)
                
                # Load and play TTS audio
                tts_sound = pygame.mixer.Sound(temp_path)
                tts_sound.set_volume(1.0)
                channel = tts_sound.play()
                
                print(f"DEBUG: Audio File TTS playing: '{text}'")
                
                # Wait for audio to complete
                while channel.get_busy():
                    pygame.time.wait(100)
                
                # Restore music volume
                pygame.mixer.music.set_volume(original_volume)
                
                # Clean up
                os.unlink(temp_path)
                
                return True
            
            return False
            
        except Exception as e:
            print(f"DEBUG: Audio File TTS failed: {e}")
            try:
                pygame.mixer.music.set_volume(original_volume)
                if 'temp_path' in locals() and os.path.exists(temp_path):
                    os.unlink(temp_path)
            except:
                pass
            return False
    
    def _try_system_tts(self, text: str) -> bool:
        """Fallback to system TTS command"""
        try:
            import subprocess
            
            # Lower music volume
            original_volume = pygame.mixer.music.get_volume()
            pygame.mixer.music.set_volume(0.1)
            
            # Use PowerShell for TTS
            ps_command = f'Add-Type -AssemblyName System.Speech; $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; $synth.Rate = 2; $synth.Volume = 100; $synth.Speak("{text}")'
            
            print(f"DEBUG: System TTS speaking: '{text}'")
            
            result = subprocess.run([
                'powershell', '-Command', ps_command
            ], capture_output=True, timeout=5)
            
            # Restore music volume
            pygame.mixer.music.set_volume(original_volume)
            
            return result.returncode == 0
            
        except Exception as e:
            print(f"DEBUG: System TTS failed: {e}")
            try:
                pygame.mixer.music.set_volume(original_volume)
            except:
                pass
            return False
    
    def set_master_volume(self, volume: int):
        """Set master volume (0-100)"""
        volume = max(0, min(100, volume))
        self.update_setting('master_volume', volume)
        print(f"DEBUG: Master volume set to {volume}%")
        
    def set_user_context(self, user_id: int, auth_token: str = None):
        """Set the current user context for database operations"""
        self.current_user_id = user_id
        print(f"DEBUG: Audio manager user context set to user {user_id}")
        
        # Save auth token to app settings if provided
        if auth_token:
            self._save_auth_token(auth_token)
        
        # Clear cache to force fresh load for new user
        self._settings_cache = None
        self._cache_timestamp = 0
        
        # Reload settings from database for this user
        self.settings = self._load_settings(force_reload=True)
        self._apply_volume_settings()
        
    def _save_auth_token(self, token: str):
        """Save auth token to app_settings.json for database access"""
        try:
            import os
            import json
            
            app_settings = {}
            if os.path.exists("app_settings.json"):
                with open("app_settings.json", 'r') as f:
                    app_settings = json.load(f)
            
            app_settings['auth_token'] = token
            
            with open("app_settings.json", 'w') as f:
                json.dump(app_settings, f, indent=2)
            
            print("DEBUG: Auth token saved to app_settings.json")
        except Exception as e:
            print(f"DEBUG: Failed to save auth token: {e}")
    
    def set_music_volume(self, volume: int):
        """Set background music volume (0-100)"""
        volume = max(0, min(100, volume))
        self.update_setting('background_music', volume)
    
    def toggle_sound_effects(self, enabled: bool):
        """Toggle sound effects on/off"""
        self.update_setting('sound_effects', enabled)
    
    def toggle_button_sounds(self, enabled: bool):
        """Toggle button sounds on/off"""
        self.update_setting('button_sounds', enabled)
    
    def toggle_voice_feedback(self, enabled: bool):
        """Toggle voice feedback on/off"""
        self.update_setting('voice_feedback', enabled)
    
    def toggle_notification_sounds(self, enabled: bool):
        """Toggle notification sounds on/off"""
        self.update_setting('notification_sounds', enabled)
    
    def play_category_audio(self, category: str, loop: bool = False, volume_override: Optional[float] = None):
        """Play audio for a specific category"""
        try:
            # Reload settings to ensure we have the latest changes
            self.settings = self._load_settings()
            
            # Get category audio settings
            audio_setting = f"category_{category}_audio"
            volume_setting = f"category_{category}_volume"
            
            selected_audio = self.settings.get(audio_setting, "Default")
            category_volume = self.settings.get(volume_setting, 80) / 100.0
            
            print(f"DEBUG: Playing category '{category}' audio: '{selected_audio}' at volume {category_volume}")
            
            if volume_override is not None:
                category_volume = volume_override
            
            # Apply master volume
            final_volume = category_volume * (self.settings.get('master_volume', 70) / 100.0)
            
            if selected_audio == "Default":
                # Use default behavior for this category
                print(f"DEBUG: Using default audio for category '{category}'")
                self._play_default_category_audio(category, final_volume, loop)
                return
            
            # Determine if this is music or sound effect based on category
            music_categories = [
                'level_upgrade', 'gameplay_background', 'thinking_time', 
                'game_victory', 'tournament_mode', 'menu_background'
            ]
            
            if category in music_categories:
                # Play as background music
                audio_path = self._get_music_file_path(selected_audio)
                print(f"DEBUG: Music category '{category}' - looking for file: {audio_path}")
                if audio_path:
                    pygame.mixer.music.stop()  # Stop current music first
                    pygame.mixer.music.load(audio_path)
                    pygame.mixer.music.set_volume(final_volume)
                    pygame.mixer.music.play(-1 if loop else 0)
                    print(f"DEBUG: Started music '{selected_audio}' for category '{category}'")
                else:
                    print(f"DEBUG: Music file not found for '{selected_audio}'")
            else:
                # Play as sound effect
                audio_path = self._get_sound_file_path(selected_audio)
                print(f"DEBUG: Sound category '{category}' - looking for file: {audio_path}")
                if audio_path:
                    sound = pygame.mixer.Sound(audio_path)
                    sound.set_volume(final_volume)
                    sound.play()
                    print(f"DEBUG: Played sound '{selected_audio}' for category '{category}'")
                else:
                    print(f"DEBUG: Sound file not found for '{selected_audio}'")
                    
        except Exception as e:
            print(f"Error playing category audio {category}: {e}")
            import traceback
            traceback.print_exc()
    
    def _play_default_category_audio(self, category: str, volume: float, loop: bool):
        """Play default audio for a category"""
        # Map categories to default sounds
        default_mappings = {
            'level_upgrade': 'bonus',
            'game_start': 'game_start',
            'correct_answer': 'success',
            'wrong_answer': 'fail',
            'bonus_achievement': 'bonus',
            'gameplay_background': None,  # Use random music
            'thinking_time': None,  # Use random music
            'game_victory': 'success',
            'tournament_mode': None,  # Use random music
            'menu_background': None  # Use random music
        }
        
        default_sound = default_mappings.get(category)
        
        if default_sound and default_sound in self.sound_cache:
            # Play cached sound effect
            sound = self.sound_cache[default_sound]
            sound.set_volume(volume)
            sound.play()
        elif default_sound is None:
            # Play random background music for music categories
            self.start_background_music()
    
    def _get_music_file_path(self, music_name: str) -> Optional[str]:
        """Get full path for music file"""
        music_dir = self.assets_path / "music"
        
        print(f"DEBUG: Looking for music '{music_name}' in: {music_dir}")
        print(f"DEBUG: Music dir exists: {music_dir.exists()}")
        
        if music_dir.exists():
            print(f"DEBUG: Music dir contents: {list(music_dir.iterdir())}")
        
        # Try exact match first
        music_path = music_dir / f"{music_name}.ogg"
        if music_path.exists():
            print(f"DEBUG: Found exact match: {music_path}")
            return str(music_path)
        
        # Try with freetouse.com suffix
        music_path = music_dir / f"{music_name} (freetouse.com).ogg"
        if music_path.exists():
            print(f"DEBUG: Found with suffix: {music_path}")
            return str(music_path)
        
        print(f"DEBUG: Music file not found for: {music_name}")
        return None
    
    def _get_sound_file_path(self, sound_name: str) -> Optional[str]:
        """Get full path for sound effect file"""
        sounds_dir = self.assets_path / "sound effects"
        sound_path = sounds_dir / f"{sound_name}.ogg"
        
        print(f"DEBUG: Looking for sound '{sound_name}' at: {sound_path}")
        print(f"DEBUG: Sound file exists: {sound_path.exists()}")
        
        if sound_path.exists():
            return str(sound_path)
        else:
            print(f"DEBUG: Sound file not found for: {sound_name}")
            if sounds_dir.exists():
                print(f"DEBUG: Available sound files: {list(sounds_dir.glob('*.ogg'))}")
            return None
    
    def play_background_music(self, music_file: str, loop: bool = True, volume: Optional[float] = None):
        """Enhanced background music playback with volume control"""
        if self.settings.get('background_music', 50) == 0:
            return
        
        try:
            if os.path.exists(music_file):
                pygame.mixer.music.load(music_file)
                
                if volume is not None:
                    # Apply custom volume with master volume
                    final_volume = volume * (self.settings.get('master_volume', 70) / 100.0)
                    pygame.mixer.music.set_volume(final_volume)
                else:
                    self._apply_volume_settings()
                
                pygame.mixer.music.play(-1 if loop else 0)
        except Exception as e:
            print(f"Error playing background music: {e}")
    
    def play_sound_effect(self, sound_file: str, volume: Optional[float] = None):
        """Enhanced sound effect playback with volume control"""
        if not self.settings.get('sound_effects', True):
            return
        
        try:
            if os.path.exists(sound_file):
                sound = pygame.mixer.Sound(sound_file)
                
                if volume is not None:
                    # Apply custom volume with master volume
                    final_volume = volume * (self.settings.get('master_volume', 70) / 100.0)
                    sound.set_volume(final_volume)
                else:
                    master_vol = self.settings.get('master_volume', 70) / 100.0
                    sound.set_volume(master_vol)
                
                sound.play()
        except Exception as e:
            print(f"Error playing sound effect: {e}")
    
    def stop_all_sounds(self):
        """Stop all sound effects"""
        try:
            pygame.mixer.stop()
        except Exception as e:
            print(f"Error stopping all sounds: {e}")
    
    # Convenience methods for specific game events
    def play_level_upgrade_audio(self):
        """Play level upgrade celebration audio"""
        self.play_category_audio('level_upgrade')
    
    def play_game_start_audio(self):
        """Play game start audio"""
        self.play_category_audio('game_start')
    
    def play_correct_answer_audio(self):
        """Play correct answer audio"""
        self.play_category_audio('correct_answer')
    
    def play_wrong_answer_audio(self):
        """Play wrong answer audio"""
        self.play_category_audio('wrong_answer')
    
    def play_game_victory_audio(self):
        """Play game victory audio"""
        self.play_category_audio('game_victory')
    
    def play_bonus_achievement_audio(self):
        """Play bonus/achievement audio"""
        self.play_category_audio('bonus_achievement')
    
    def start_gameplay_background_music(self):
        """Start gameplay background music"""
        print(f"DEBUG: Starting gameplay background music")
        # Store previous context for resume
        self._previous_music_context = self._current_music_context
        self._current_music_context = 'gameplay_background'
        self.play_category_audio('gameplay_background', loop=True)
        print(f"DEBUG: Gameplay background music started")
    
    def start_thinking_time_music(self):
        """Start thinking time music"""
        self.play_category_audio('thinking_time', loop=True)
    
    def start_tournament_background_music(self):
        """Start tournament background music"""
        print(f"DEBUG: Starting tournament background music")
        # Store previous context for resume
        self._previous_music_context = self._current_music_context
        self._current_music_context = 'tournament_mode'
        self.play_category_audio('tournament_mode', loop=True)
        print(f"DEBUG: Tournament background music started")
    
    def start_menu_background_music(self):
        """Start menu background music with persistence"""
        print(f"DEBUG: Starting menu background music")
        # Store current state for resume functionality
        self._current_music_context = 'menu_background'
        self.play_category_audio('menu_background', loop=True)
        print(f"DEBUG: Menu background music started")

    def reinitialize_audio(self):
        """Reinitialize audio system with current settings"""
        try:
            # Reload settings
            self.settings = self._load_settings()
            
            # Reinitialize pygame mixer
            pygame.mixer.quit()
            pygame.mixer.pre_init(frequency=22050, size=-16, channels=2, buffer=512)
            pygame.mixer.init()
            
            # Reload sound cache
            self.sound_cache = {}
            self._preload_sounds()
            
            # Apply volume settings
            self._apply_volume_settings()
            
            print("✅ Audio system reinitialized successfully")
            
        except Exception as e:
            print(f"Error reinitializing audio: {e}")
    
    def refresh_gameplay_audio(self):
        """Refresh gameplay audio settings during active game"""
        try:
            # Reload settings to get latest changes
            self.settings = self._load_settings()
            
            # Stop current background music
            pygame.mixer.music.stop()
            
            # Restart gameplay background music with new settings
            self.start_gameplay_background_music()
            
            # Apply new volume settings
            self._apply_volume_settings()
            
            print("DEBUG: Gameplay audio refreshed with new settings")
            
        except Exception as e:
            print(f"Error refreshing gameplay audio: {e}")
    
    def force_enable_audio(self):
        """Force enable all audio features for debugging"""
        self.update_setting('sound_effects', True)
        self.update_setting('button_sounds', True)
        self.update_setting('notification_sounds', True)
        self.update_setting('voice_feedback', True)
        self.update_setting('master_volume', 80)
        self._apply_volume_settings()
        print("🔊 All audio features force-enabled")
        
    def force_gameplay_voice_feedback(self, enabled: bool = True):
        """Force enable voice feedback specifically for gameplay"""
        self.update_setting('voice_feedback', enabled)
        if enabled:
            print("🗣️ Gameplay voice feedback force-enabled")
            # Test voice feedback immediately
            self.speak_text("Voice feedback is now enabled for gameplay", priority=True)
        else:
            print("🔇 Gameplay voice feedback disabled")
    
    def resume_previous_background_music(self):
        """Resume the previous background music context"""
        try:
            if self._previous_music_context:
                print(f"DEBUG: Resuming previous background music: {self._previous_music_context}")
                
                # Map contexts to their start methods
                context_methods = {
                    'menu_background': self.start_menu_background_music,
                    'gameplay_background': self.start_gameplay_background_music,
                    'tournament_mode': self.start_tournament_background_music
                }
                
                if self._previous_music_context in context_methods:
                    # Temporarily store the previous context to avoid overwriting
                    temp_context = self._previous_music_context
                    self._previous_music_context = None  # Clear to avoid recursion
                    self._current_music_context = temp_context
                    
                    # Start the appropriate music
                    if temp_context == 'menu_background':
                        self.play_category_audio('menu_background', loop=True)
                    elif temp_context == 'gameplay_background':
                        self.play_category_audio('gameplay_background', loop=True)
                    elif temp_context == 'tournament_mode':
                        self.play_category_audio('tournament_mode', loop=True)
                    
                    print(f"DEBUG: Successfully resumed {temp_context} background music")
                else:
                    print(f"DEBUG: Unknown music context: {self._previous_music_context}")
                    # Default to menu background music
                    self.start_menu_background_music()
            else:
                print(f"DEBUG: No previous music context, starting menu background music")
                self.start_menu_background_music()
                
        except Exception as e:
            print(f"Error resuming background music: {e}")
            # Fallback to menu background music
            self.start_menu_background_music()
    
    def stop_background_music_completely(self):
        """Stop background music completely and clear context"""
        try:
            pygame.mixer.music.stop()
            self._current_music_context = None
            self._previous_music_context = None
            print("DEBUG: Background music stopped completely")
        except Exception as e:
            print(f"Error stopping background music: {e}")

    def cleanup(self):
        """Cleanup audio resources"""
        try:
            pygame.mixer.quit()
            if self.tts_engine:
                self.tts_engine.stop()
            print("DEBUG: Audio manager cleanup completed")
        except Exception as e:
            print(f"Error during audio cleanup: {e}")
            
    def get_gameplay_voice_status(self) -> bool:
        """Check if voice feedback is enabled for gameplay"""
        # Use cached settings instead of force reload
        voice_enabled = self.settings.get('voice_feedback', True)
        print(f"DEBUG: Gameplay voice feedback status: {voice_enabled}")
        return voice_enabled
        
    def _get_auth_token(self) -> str:
        """Innovative method to extract auth token from multiple sources"""
        try:
            import os
            
            # Method 1: Try to get from app_settings.json
            if os.path.exists("app_settings.json"):
                with open("app_settings.json", 'r') as f:
                    data = json.load(f)
                    token = data.get('auth_token')
                    if token:
                        print("DEBUG: Found auth token in app_settings.json")
                        return token
            
            # Method 2: Try to get from environment or global state
            token = os.environ.get('QUIZCLASH_AUTH_TOKEN')
            if token:
                print("DEBUG: Found auth token in environment")
                return token
            
            # Method 3: Try to extract from current session (innovative approach)
            try:
                import tkinter as tk
                
                # Get all toplevel windows
                for widget in tk._default_root.winfo_children() if tk._default_root else []:
                    if hasattr(widget, 'auth_token') and widget.auth_token:
                        print("DEBUG: Found auth token from toplevel widget")
                        return widget.auth_token
                
                # Search through all existing Tk instances
                import gc
                for obj in gc.get_objects():
                    if hasattr(obj, 'auth_token') and obj.auth_token and hasattr(obj, 'winfo_exists'):
                        try:
                            if obj.winfo_exists():
                                print("DEBUG: Found auth token from existing Tk object")
                                return obj.auth_token
                        except:
                            continue
            except Exception as e:
                print(f"DEBUG: Widget search failed: {e}")
                pass
            
            print("DEBUG: No auth token found in any source")
            return None
            
        except Exception as e:
            print(f"DEBUG: Error getting auth token: {e}")
            return None


# Global audio manager instance
audio_manager = AudioManager()
