"""
Weather service for business logic
"""
from typing import Dict, Optional
from evaluation_service.core.logger import get_logger
from evaluation_service.core.cache import get_cache
from evaluation_service.modules.weather.repository import WeatherRepository
from evaluation_service.modules.weather.validator import WeatherValidator

logger = get_logger()
cache = get_cache()

class WeatherService:
    """Service layer for weather operations"""
    
    def __init__(self):
        self.repository = WeatherRepository()
        self.validator = WeatherValidator()
    
    def get_weather(self, city: str, use_cache: bool = True, auto_refresh: bool = False) -> Optional[Dict]:
        """Get weather data for a city"""
        # Try cache first
        if use_cache:
            cache_key = f"weather:{city}"
            cached_data = cache.get(cache_key)
            if cached_data:
                logger.info(f"Cache hit for weather: {city}", module='WEATHER_SERVICE')
                return cached_data
        
        # Get from database
        weather_data = self.repository.get_latest_weather(city)
        
        if weather_data:
            # Check if data is fresh
            if auto_refresh and not self.repository.is_data_fresh(city, max_age_hours=1):
                logger.info(f"Weather data for {city} is stale, needs refresh", module='WEATHER_SERVICE')
                return None  # Signal that refresh is needed
            
            # Cache for 10 minutes
            cache.set(f"weather:{city}", weather_data, ttl=600)
            logger.info(f"Retrieved weather from database: {city}", module='WEATHER_SERVICE')
        
        return weather_data
    
    def save_weather(self, data: Dict) -> tuple[bool, str, Optional[int]]:
        """Save weather data"""
        # Validate data
        is_valid, error = self.validator.validate_weather_data(data)
        if not is_valid:
            logger.error(f"Invalid weather data: {error}", module='WEATHER_SERVICE')
            return False, error, None
        
        # Sanitize data
        sanitized_data = self.validator.sanitize_data(data)
        
        # Save to database
        try:
            weather_id = self.repository.save_weather_data(sanitized_data)
            logger.info(f"Saved weather data for {sanitized_data['city']}", module='WEATHER_SERVICE')
            
            # Invalidate cache
            cache_key = f"weather:{sanitized_data['city']}"
            cache.delete(cache_key)
            
            return True, "Weather data saved successfully", weather_id
        except Exception as e:
            logger.error(f"Failed to save weather data: {e}", module='WEATHER_SERVICE', exc_info=True)
            return False, str(e), None
    
    def update_risk_evaluation(self, weather_id: int, risk_score: float, ollama_evaluation: str):
        """Update risk score and evaluation"""
        try:
            self.repository.update_risk_score(weather_id, risk_score, ollama_evaluation)
            logger.info(f"Updated risk evaluation for weather ID {weather_id}", module='WEATHER_SERVICE')
            
            # Invalidate cache for the city
            weather_data = self.repository.get_by_id('weather_data', weather_id)
            if weather_data:
                cache_key = f"weather:{weather_data['city']}"
                cache.delete(cache_key)
        except Exception as e:
            logger.error(f"Failed to update risk evaluation: {e}", module='WEATHER_SERVICE', exc_info=True)
    
    def get_weather_history(self, city: str, hours: int = 24) -> list:
        """Get weather history for a city"""
        return self.repository.get_weather_history(city, hours)
    
    def get_all_cities(self) -> list:
        """Get all cities with weather data"""
        return self.repository.get_all_cities()
