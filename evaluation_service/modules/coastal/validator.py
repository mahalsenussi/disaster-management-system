"""
Coastal data validator
"""
from typing import Dict, Optional
from evaluation_service.core.logger import get_logger

logger = get_logger()

class CoastalValidator:
    """Validates coastal data before processing"""
    
    @staticmethod
    def validate_coastal_data(data: Dict) -> tuple[bool, Optional[str]]:
        """Validate coastal data
        
        Returns:
            (is_valid, error_message)
        """
        if not data:
            return False, "No data provided"
        
        # Check required fields
        if 'location' not in data or not data['location']:
            return False, "Location is required"
        
        # Validate numeric fields
        numeric_fields = ['wave_height', 'wave_period', 'sea_level_anomaly', 'wind_speed']
        for field in numeric_fields:
            if field in data and data[field] is not None:
                try:
                    float(data[field])
                except (ValueError, TypeError):
                    return False, f"{field} must be a number"
        
        # Validate ranges
        if 'wave_height' in data and data['wave_height'] is not None:
            wave = float(data['wave_height'])
            if wave < 0 or wave > 30:
                return False, f"Wave height {wave} is out of valid range (0 to 30)"
        
        if 'wave_period' in data and data['wave_period'] is not None:
            period = float(data['wave_period'])
            if period < 0 or period > 30:
                return False, f"Wave period {period} is out of valid range (0 to 30)"
        
        if 'sea_level_anomaly' in data and data['sea_level_anomaly'] is not None:
            anomaly = float(data['sea_level_anomaly'])
            if anomaly < -2 or anomaly > 2:
                return False, f"Sea level anomaly {anomaly} is out of valid range (-2 to 2)"
        
        if 'wind_speed' in data and data['wind_speed'] is not None:
            wind = float(data['wind_speed'])
            if wind < 0 or wind > 200:
                return False, f"Wind speed {wind} is out of valid range (0 to 200)"
        
        return True, None
    
    @staticmethod
    def sanitize_data(data: Dict) -> Dict:
        """Sanitize coastal data"""
        sanitized = {}
        
        for key, value in data.items():
            if value is None:
                continue
            
            # Convert numeric fields to float
            if key in ['wave_height', 'wave_period', 'sea_level_anomaly', 'wind_speed']:
                try:
                    sanitized[key] = float(value)
                except (ValueError, TypeError):
                    logger.warning(f"Failed to convert {key} to float: {value}", module='COASTAL_VALIDATOR')
            else:
                sanitized[key] = str(value)
        
        return sanitized
