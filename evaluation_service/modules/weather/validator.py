"""
Weather data validator
"""
from typing import Dict, Optional
from evaluation_service.core.logger import get_logger

logger = get_logger()

class WeatherValidator:
    """Validates weather data before processing"""
    
    @staticmethod
    def validate_weather_data(data: Dict) -> tuple[bool, Optional[str]]:
        """Validate weather data
        
        Returns:
            (is_valid, error_message)
        """
        if not data:
            return False, "No data provided"
        
        # Check required fields
        if 'city' not in data or not data['city']:
            return False, "City is required"
        
        # Validate numeric fields
        numeric_fields = ['temperature', 'humidity', 'pressure', 'wind_speed']
        for field in numeric_fields:
            if field in data and data[field] is not None:
                try:
                    float(data[field])
                except (ValueError, TypeError):
                    return False, f"{field} must be a number"
        
        # Validate ranges
        if 'temperature' in data and data['temperature'] is not None:
            temp = float(data['temperature'])
            if temp < -50 or temp > 60:
                return False, f"Temperature {temp} is out of valid range (-50 to 60)"
        
        if 'humidity' in data and data['humidity'] is not None:
            humidity = float(data['humidity'])
            if humidity < 0 or humidity > 100:
                return False, f"Humidity {humidity} is out of valid range (0 to 100)"
        
        if 'pressure' in data and data['pressure'] is not None:
            pressure = float(data['pressure'])
            if pressure < 800 or pressure > 1200:
                return False, f"Pressure {pressure} is out of valid range (800 to 1200)"
        
        if 'wind_speed' in data and data['wind_speed'] is not None:
            wind = float(data['wind_speed'])
            if wind < 0 or wind > 200:
                return False, f"Wind speed {wind} is out of valid range (0 to 200)"
        
        return True, None
    
    @staticmethod
    def sanitize_data(data: Dict) -> Dict:
        """Sanitize weather data"""
        sanitized = {}
        
        for key, value in data.items():
            if value is None:
                continue
            
            # Convert numeric fields to float
            if key in ['temperature', 'humidity', 'pressure', 'wind_speed']:
                try:
                    sanitized[key] = float(value)
                except (ValueError, TypeError):
                    logger.warning(f"Failed to convert {key} to float: {value}", module='WEATHER_VALIDATOR')
            else:
                sanitized[key] = str(value)
        
        return sanitized
