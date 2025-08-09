import logging
import sys
from pathlib import Path
from typing import Optional
import json
from datetime import datetime

class StructuredLogger:
    """Structured logger with JSON output and multiple levels"""
    
    def __init__(self, name: str, log_file: Optional[str] = None):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        # Clear existing handlers
        self.logger.handlers.clear()
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # File handler if specified
        if log_file:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_path)
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)
    
    def _log_structured(self, level: str, message: str, **kwargs):
        """Log with structured data"""
        log_data = {
            'timestamp': datetime.now().isoformat(),
            'level': level,
            'message': message,
            **kwargs
        }
        
        if level == 'ERROR':
            self.logger.error(json.dumps(log_data))
        elif level == 'WARNING':
            self.logger.warning(json.dumps(log_data))
        elif level == 'INFO':
            self.logger.info(json.dumps(log_data))
        else:
            self.logger.debug(json.dumps(log_data))
    
    def info(self, message: str, **kwargs):
        self._log_structured('INFO', message, **kwargs)
    
    def error(self, message: str, **kwargs):
        self._log_structured('ERROR', message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        self._log_structured('WARNING', message, **kwargs)
    
    def debug(self, message: str, **kwargs):
        self._log_structured('DEBUG', message, **kwargs)

# Global logger instance
logger = StructuredLogger('BestBuyTracker', 'logs/bot.log')
