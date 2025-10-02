"""
API Client for QuizClash - Centralized API Communication
Automatically handles local/remote endpoint switching
"""
import requests
from typing import Optional, Dict, Any
from config import Config

class APIClient:
    """Centralized API client with automatic endpoint detection"""
    
    def __init__(self):
        self.base_url = Config.get_api_base()
        self.timeout = Config.API_TIMEOUT
        self.max_retries = Config.MAX_RETRIES
        self._test_connection()
    
    def _test_connection(self):
        """Test and auto-switch connection if needed"""
        if Config.AUTO_DETECT_MODE:
            try:
                response = requests.get(f"{self.base_url}/health", timeout=3)
                if response.status_code == 200:
                    print(f"✅ Connected to API: {self.base_url}")
                    return
            except:
                pass
            
            # If primary fails and fallback enabled, try switching
            if Config.FALLBACK_TO_LOCAL and Config.API_MODE == "remote":
                print(f"⚠️ Remote API unavailable, falling back to local...")
                Config.API_MODE = "local"
                self.base_url = Config.get_api_base()
                try:
                    response = requests.get(f"{self.base_url}/health", timeout=3)
                    if response.status_code == 200:
                        print(f"✅ Connected to local API: {self.base_url}")
                        return
                except:
                    print(f"❌ No API connection available")
    
    def get(self, endpoint: str, params: Optional[Dict] = None, **kwargs) -> requests.Response:
        """Make GET request to API"""
        url = f"{self.base_url}{endpoint}"
        timeout = kwargs.pop('timeout', self.timeout)
        return requests.get(url, params=params, timeout=timeout, **kwargs)
    
    def post(self, endpoint: str, json: Optional[Dict] = None, **kwargs) -> requests.Response:
        """Make POST request to API"""
        url = f"{self.base_url}{endpoint}"
        timeout = kwargs.pop('timeout', self.timeout)
        return requests.post(url, json=json, timeout=timeout, **kwargs)
    
    def put(self, endpoint: str, json: Optional[Dict] = None, **kwargs) -> requests.Response:
        """Make PUT request to API"""
        url = f"{self.base_url}{endpoint}"
        timeout = kwargs.pop('timeout', self.timeout)
        return requests.put(url, json=json, timeout=timeout, **kwargs)
    
    def delete(self, endpoint: str, **kwargs) -> requests.Response:
        """Make DELETE request to API"""
        url = f"{self.base_url}{endpoint}"
        timeout = kwargs.pop('timeout', self.timeout)
        return requests.delete(url, timeout=timeout, **kwargs)
    
    def switch_mode(self, mode: str):
        """Switch between local and remote mode"""
        Config.set_mode(mode)
        self.base_url = Config.get_api_base()
        self._test_connection()
        print(f"✅ Switched to {mode} mode: {self.base_url}")

# Global API client instance
api_client = APIClient()

# Convenience functions for backward compatibility
def get_api_base() -> str:
    """Get current API base URL"""
    return api_client.base_url

def switch_api_mode(mode: str):
    """Switch API mode (local/remote)"""
    api_client.switch_mode(mode)

def test_api_connection() -> bool:
    """Test API connection"""
    try:
        response = api_client.get("/health", timeout=3)
        return response.status_code == 200
    except:
        return False
