"""
News data validator
"""
from typing import Dict, Optional
from evaluation_service.core.logger import get_logger

logger = get_logger()

class NewsValidator:
    """Validates news data before processing"""
    
    @staticmethod
    def validate_news_data(data: Dict) -> tuple[bool, Optional[str]]:
        """Validate news data
        
        Returns:
            (is_valid, error_message)
        """
        if not data:
            return False, "No data provided"
        
        # Validate article count
        if 'article_count' in data and data['article_count'] is not None:
            try:
                count = int(data['article_count'])
                if count < 0:
                    return False, f"Article count must be non-negative"
            except (ValueError, TypeError):
                return False, "Article count must be an integer"
        
        # Validate risk score
        if 'risk_score' in data and data['risk_score'] is not None:
            try:
                score = float(data['risk_score'])
                if score < 0 or score > 1:
                    return False, f"Risk score must be between 0 and 1"
            except (ValueError, TypeError):
                return False, "Risk score must be a number"
        
        return True, None
    
    @staticmethod
    def sanitize_data(data: Dict) -> Dict:
        """Sanitize news data"""
        sanitized = {}
        
        for key, value in data.items():
            if value is None:
                continue
            
            # Keep list/dict fields as-is (they will be JSON-serialized in repository)
            if key in ['articles', 'sources_used']:
                sanitized[key] = value
            # Convert numeric fields
            elif key == 'article_count':
                try:
                    sanitized[key] = int(value)
                except (ValueError, TypeError):
                    logger.warning(f"Failed to convert {key} to int: {value}", module='NEWS_VALIDATOR')
            elif key == 'risk_score':
                try:
                    sanitized[key] = float(value)
                except (ValueError, TypeError):
                    logger.warning(f"Failed to convert {key} to float: {value}", module='NEWS_VALIDATOR')
            else:
                sanitized[key] = str(value)
        
        return sanitized
