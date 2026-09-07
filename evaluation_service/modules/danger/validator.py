"""
Danger data validator
"""
from typing import Dict, Optional
from evaluation_service.core.logger import get_logger

logger = get_logger()

class DangerValidator:
    """Validates danger prediction data before processing"""
    
    @staticmethod
    def validate_prediction_data(data: Dict) -> tuple[bool, Optional[str]]:
        """Validate prediction data
        
        Returns:
            (is_valid, error_message)
        """
        if not data:
            return False, "No data provided"
        
        # Check required fields
        if 'city' not in data or not data['city']:
            return False, "City is required"
        
        # Validate risk score
        if 'risk_score' in data and data['risk_score'] is not None:
            try:
                score = float(data['risk_score'])
                if score < 0 or score > 1:
                    return False, f"Risk score must be between 0 and 1"
            except (ValueError, TypeError):
                return False, "Risk score must be a number"
        
        # Validate confidence
        if 'confidence' in data and data['confidence'] is not None:
            try:
                conf = float(data['confidence'])
                if conf < 0 or conf > 1:
                    return False, f"Confidence must be between 0 and 1"
            except (ValueError, TypeError):
                return False, "Confidence must be a number"
        
        return True, None
    
    @staticmethod
    def validate_features(features: Dict) -> tuple[bool, Optional[str]]:
        """Validate feature data before feeding to ML model
        
        Returns:
            (is_valid, error_message)
        """
        if not features:
            return False, "No features provided"
        
        # Check if all required features are present
        required_features = ['weather_temp', 'weather_humidity', 'weather_pressure', 
                          'weather_wind', 'coastal_wave_height', 'news_risk_score']
        
        missing_features = [f for f in required_features if f not in features or features[f] is None]
        
        if missing_features:
            logger.warning(f"Missing features: {missing_features}", module='DANGER_VALIDATOR')
            # Return True but with warning - we'll handle missing data in the service
            return True, f"Missing features: {missing_features}"
        
        return True, None
    
    @staticmethod
    def sanitize_data(data: Dict) -> Dict:
        """Sanitize prediction data"""
        sanitized = {}
        
        for key, value in data.items():
            if value is None:
                continue
            
            # Convert numeric fields
            if key in ['risk_score', 'confidence']:
                try:
                    sanitized[key] = float(value)
                except (ValueError, TypeError):
                    logger.warning(f"Failed to convert {key} to float: {value}", module='DANGER_VALIDATOR')
            else:
                sanitized[key] = str(value)
        
        return sanitized
