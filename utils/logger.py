"""
Logger utility for streaming logs to Streamlit
"""

from datetime import datetime
from typing import List, Dict, Optional
import threading

class StreamlitLogger:
    """Thread-safe logger that stores logs for Streamlit display"""
    
    def __init__(self):
        self._logs: List[Dict[str, str]] = []
        self._lock = threading.Lock()
    
    def log(self, message: str, level: str = "info"):
        """Add a log entry"""
        with self._lock:
            self._logs.append({
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "message": message,
                "level": level
            })
    
    def get_logs(self) -> List[Dict[str, str]]:
        """Get all logs"""
        with self._lock:
            return self._logs.copy()
    
    def clear(self):
        """Clear all logs"""
        with self._lock:
            self._logs.clear()

