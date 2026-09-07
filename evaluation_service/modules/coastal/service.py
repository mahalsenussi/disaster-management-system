"""
Coastal service for business logic
"""
from typing import Dict, Optional
from evaluation_service.core.logger import get_logger
from evaluation_service.core.cache import get_cache
from evaluation_service.modules.coastal.repository import CoastalRepository
from evaluation_service.modules.coastal.validator import CoastalValidator

logger = get_logger()
cache = get_cache()

class CoastalService:
    """Service layer for coastal operations"""
    
    def __init__(self):
        self.repository = CoastalRepository()
        self.validator = CoastalValidator()
    
    def get_coastal(self, location: str, use_cache: bool = True, auto_refresh: bool = False) -> Optional[Dict]:
        """Get coastal data for a location"""
        # Try cache first
        if use_cache:
            cache_key = f"coastal:{location}"
            cached_data = cache.get(cache_key)
            if cached_data:
                logger.info(f"Cache hit for coastal: {location}", module='COASTAL_SERVICE')
                return cached_data
        
        # Get from database
        coastal_data = self.repository.get_latest_coastal(location)
        
        if coastal_data:
            # Check if data is fresh
            if auto_refresh and not self.repository.is_data_fresh(location, max_age_hours=1):
                logger.info(f"Coastal data for {location} is stale, needs refresh", module='COASTAL_SERVICE')
                return None  # Signal that refresh is needed
            
            # Cache for 10 minutes
            cache.set(f"coastal:{location}", coastal_data, ttl=600)
            logger.info(f"Retrieved coastal from database: {location}", module='COASTAL_SERVICE')
        
        return coastal_data
    
    def save_coastal(self, data: Dict) -> tuple[bool, str, Optional[int]]:
        """Save coastal data"""
        # Validate data
        is_valid, error = self.validator.validate_coastal_data(data)
        if not is_valid:
            logger.error(f"Invalid coastal data: {error}", module='COASTAL_SERVICE')
            return False, error, None
        
        # Sanitize data
        sanitized_data = self.validator.sanitize_data(data)
        
        # Save to database
        try:
            coastal_id = self.repository.save_coastal_data(sanitized_data)
            logger.info(f"Saved coastal data for {sanitized_data['location']}", module='COASTAL_SERVICE')
            
            # Invalidate cache
            cache_key = f"coastal:{sanitized_data['location']}"
            cache.delete(cache_key)
            
            return True, "Coastal data saved successfully", coastal_id
        except Exception as e:
            logger.error(f"Failed to save coastal data: {e}", module='COASTAL_SERVICE', exc_info=True)
            return False, str(e), None
    
    def get_coastal_history(self, location: str, hours: int = 24) -> list:
        """Get coastal history for a location"""
        return self.repository.get_coastal_history(location, hours)
    
    def get_all_locations(self) -> list:
        """Get all locations with coastal data"""
        return self.repository.get_all_locations()
    
    def update_risk_evaluation(self, coastal_id: int, risk_score: float, ollama_evaluation: str):
        """Update risk score and evaluation"""
        try:
            self.repository.update_risk_score(coastal_id, risk_score, ollama_evaluation)
            logger.info(f"Updated risk evaluation for coastal ID {coastal_id}", module='COASTAL_SERVICE')
            
            # Invalidate cache for the location
            coastal_data = self.repository.get_by_id('coastal_data', coastal_id)
            if coastal_data:
                cache_key = f"coastal:{coastal_data['location']}"
                cache.delete(cache_key)
        except Exception as e:
            logger.error(f"Failed to update risk evaluation: {e}", module='COASTAL_SERVICE', exc_info=True)
