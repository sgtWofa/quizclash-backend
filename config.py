"""
Configuration System for QuizClash - API Endpoint Management
Supports both local development and remote production deployment
"""
import os
import json
from pathlib import Path

class Config:
    """Central configuration for QuizClash application"""
    
    # API Configuration
    API_MODE = os.getenv("QUIZ_API_MODE", "local")  # local or remote
    
    # API Endpoints
    LOCAL_API = "http://127.0.0.1:8000"
    REMOTE_API = os.getenv("QUIZ_API_URL", "https://quizclash-api.railway.app")
    
    # Database Configuration
    LOCAL_DB = "sqlite:///./quiz_game.db"
    REMOTE_DB = os.getenv("DATABASE_URL", LOCAL_DB)
    
    # Environment
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")  # development, production
    
    # Frontend Settings
    AUTO_DETECT_MODE = True  # Automatically detect if backend is online
    FALLBACK_TO_LOCAL = True  # Fall back to local if remote fails
    
    # Connection Settings
    API_TIMEOUT = 10  # seconds
    MAX_RETRIES = 3
    RETRY_DELAY = 1  # seconds
    
    @classmethod
    def get_api_base(cls):
        """Get the appropriate API base URL based on mode"""
        if cls.API_MODE == "remote":
            return cls.REMOTE_API
        return cls.LOCAL_API
    
    @classmethod
    def get_database_url(cls):
        """Get the appropriate database URL"""
        if cls.ENVIRONMENT == "production":
            return cls.REMOTE_DB
        return cls.LOCAL_DB
    
    @classmethod
    def is_production(cls):
        """Check if running in production mode"""
        return cls.ENVIRONMENT == "production"
    
    @classmethod
    def is_remote_mode(cls):
        """Check if using remote API"""
        return cls.API_MODE == "remote"
    
    @classmethod
    def set_mode(cls, mode: str):
        """Set API mode (local or remote)"""
        if mode not in ["local", "remote"]:
            raise ValueError("Mode must be 'local' or 'remote'")
        cls.API_MODE = mode
        cls._save_config()
    
    @classmethod
    def _get_config_path(cls):
        """Get path to config file"""
        return Path(__file__).parent / "api_config.json"
    
    @classmethod
    def _save_config(cls):
        """Save configuration to file"""
        try:
            config_data = {
                "api_mode": cls.API_MODE,
                "remote_api": cls.REMOTE_API
            }
            with open(cls._get_config_path(), 'w') as f:
                json.dump(config_data, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save config: {e}")
    
    @classmethod
    def _load_config(cls):
        """Load configuration from file"""
        try:
            config_path = cls._get_config_path()
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config_data = json.load(f)
                    cls.API_MODE = config_data.get("api_mode", cls.API_MODE)
                    if "remote_api" in config_data:
                        cls.REMOTE_API = config_data["remote_api"]
        except Exception as e:
            print(f"Warning: Could not load config: {e}")
    
    @classmethod
    def test_connection(cls, api_url: str = None) -> bool:
        """Test connection to API endpoint"""
        import requests
        
        url = api_url or cls.get_api_base()
        try:
            response = requests.get(f"{url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    @classmethod
    def auto_detect_mode(cls):
        """Automatically detect best API mode"""
        # Try remote first if configured
        if cls.REMOTE_API != "https://quizclash-api.railway.app":
            if cls.test_connection(cls.REMOTE_API):
                cls.API_MODE = "remote"
                print("✅ Connected to remote API")
                return
        
        # Fall back to local
        if cls.test_connection(cls.LOCAL_API):
            cls.API_MODE = "local"
            print("✅ Connected to local API")
            return
        
        # No connection available
        print("⚠️ No API connection available")
        cls.API_MODE = "local"  # Default to local

# Load saved configuration on import
Config._load_config()

# Auto-detect mode if enabled
if Config.AUTO_DETECT_MODE and Config.API_MODE == "local":
    try:
        Config.auto_detect_mode()
    except:
        pass  # Silent fail during import
