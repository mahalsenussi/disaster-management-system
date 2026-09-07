"""
Historical service for business logic
"""
from typing import Dict, Optional
from evaluation_service.core.logger import get_logger
from evaluation_service.core.cache import get_cache
from evaluation_service.modules.historical.repository import HistoricalRepository

logger = get_logger()
cache = get_cache()

class HistoricalService:
    """Service layer for historical disaster data operations"""
    
    def __init__(self):
        self.repository = HistoricalRepository()
    
    def get_disasters_by_country(self, country: str, use_cache: bool = True) -> list:
        """Get disasters by country"""
        cache_key = f"historical:country:{country}"
        
        if use_cache:
            cached_data = cache.get(cache_key)
            if cached_data:
                logger.info(f"Cache hit for historical disasters: {country}", module='HISTORICAL_SERVICE')
                return cached_data
        
        disasters = self.repository.get_disasters_by_country(country)
        
        if disasters:
            cache.set(cache_key, disasters, ttl=3600)  # Cache for 1 hour
            logger.info(f"Retrieved historical disasters for {country}", module='HISTORICAL_SERVICE')
        
        return disasters
    
    def get_disasters_by_type(self, disaster_type: str, use_cache: bool = True) -> list:
        """Get disasters by type"""
        cache_key = f"historical:type:{disaster_type}"
        
        if use_cache:
            cached_data = cache.get(cache_key)
            if cached_data:
                logger.info(f"Cache hit for historical disasters by type: {disaster_type}", module='HISTORICAL_SERVICE')
                return cached_data
        
        disasters = self.repository.get_disasters_by_type(disaster_type)
        
        if disasters:
            cache.set(cache_key, disasters, ttl=3600)
            logger.info(f"Retrieved historical disasters by type: {disaster_type}", module='HISTORICAL_SERVICE')
        
        return disasters
    
    def get_all_disasters(self, limit: int = 100, use_cache: bool = True) -> list:
        """Get all disasters"""
        cache_key = f"historical:all:{limit}"
        
        if use_cache:
            cached_data = cache.get(cache_key)
            if cached_data:
                logger.info("Cache hit for all historical disasters", module='HISTORICAL_SERVICE')
                return cached_data
        
        disasters = self.repository.get_all_disasters(limit)
        
        if disasters:
            cache.set(cache_key, disasters, ttl=3600)
            logger.info("Retrieved all historical disasters", module='HISTORICAL_SERVICE')
        
        return disasters
    
    def get_disaster_patterns(self, country: str = None, use_cache: bool = True) -> Dict:
        """Get disaster patterns statistics"""
        cache_key = f"historical:patterns:{country or 'all'}"
        
        if use_cache:
            cached_data = cache.get(cache_key)
            if cached_data:
                logger.info("Cache hit for disaster patterns", module='HISTORICAL_SERVICE')
                return cached_data
        
        patterns = self.repository.get_disaster_patterns(country)
        
        if patterns:
            cache.set(cache_key, patterns, ttl=3600)
            logger.info("Retrieved disaster patterns", module='HISTORICAL_SERVICE')
        
        return patterns
    
    def get_all_countries(self, use_cache: bool = True) -> list:
        """Get all countries with disaster data"""
        cache_key = "historical:countries"
        
        if use_cache:
            cached_data = cache.get(cache_key)
            if cached_data:
                logger.info("Cache hit for countries", module='HISTORICAL_SERVICE')
                return cached_data
        
        countries = self.repository.get_all_countries()
        
        if countries:
            cache.set(cache_key, countries, ttl=3600)
            logger.info("Retrieved countries", module='HISTORICAL_SERVICE')
        
        return countries
