"""
Centralized logging for evaluation service
"""
import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime

class EvaluationLogger:
    """Centralized logger for all evaluation service modules"""
    
    def __init__(self, log_dir=None, log_level=logging.INFO):
        if log_dir is None:
            log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
        
        os.makedirs(log_dir, exist_ok=True)
        
        self.logger = logging.getLogger('evaluation_service')
        self.logger.setLevel(log_level)
        
        # Prevent duplicate handlers
        if not self.logger.handlers:
            # File handler with rotation
            log_file = os.path.join(log_dir, 'evaluation.log')
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=5*1024*1024,  # 5MB
                backupCount=5
            )
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            self.logger.addHandler(file_handler)
            
            # Console handler
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s'
            ))
            self.logger.addHandler(console_handler)
    
    def info(self, message, module=None):
        """Log info message"""
        if module:
            message = f"[{module}] {message}"
        self.logger.info(message)
    
    def warning(self, message, module=None):
        """Log warning message"""
        if module:
            message = f"[{module}] {message}"
        self.logger.warning(message)
    
    def error(self, message, module=None, exc_info=False):
        """Log error message"""
        if module:
            message = f"[{module}] {message}"
        self.logger.error(message, exc_info=exc_info)
    
    def debug(self, message, module=None):
        """Log debug message"""
        if module:
            message = f"[{module}] {message}"
        self.logger.debug(message)
    
    def collector_run(self, module, status, details=None):
        """Log collector run"""
        message = f"Collector run - {module}: {status}"
        if details:
            message += f" - {details}"
        self.info(message, module='COLLECTOR')
    
    def ai_call(self, model, prompt_length, response_time=None):
        """Log AI call"""
        message = f"AI call - Model: {model}, Prompt length: {prompt_length}"
        if response_time:
            message += f", Response time: {response_time:.2f}s"
        self.info(message, module='AI')
    
    def prediction(self, city, risk_score, confidence):
        """Log prediction"""
        message = f"Prediction - City: {city}, Risk score: {risk_score:.3f}, Confidence: {confidence:.3f}"
        self.info(message, module='DANGER')
    
    def api_request(self, endpoint, method, status_code, response_time=None):
        """Log API request"""
        message = f"API request - {method} {endpoint} - Status: {status_code}"
        if response_time:
            message += f", Time: {response_time:.2f}s"
        self.info(message, module='API')

# Global logger instance
_logger = None

def get_logger():
    """Get global logger instance"""
    global _logger
    if _logger is None:
        _logger = EvaluationLogger()
    return _logger
