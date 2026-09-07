"""
News service for business logic
"""
from typing import Dict, Optional
from evaluation_service.core.logger import get_logger
from evaluation_service.core.cache import get_cache
from evaluation_service.modules.news.repository import NewsRepository
from evaluation_service.modules.news.validator import NewsValidator

logger = get_logger()
cache = get_cache()

class NewsService:
    """Service layer for news operations"""
    
    def __init__(self):
        self.repository = NewsRepository()
        self.validator = NewsValidator()
    
    def get_news(self, category: str = None, use_cache: bool = True, auto_refresh: bool = False) -> Optional[Dict]:
        """Get latest news data"""
        # Try cache first
        if use_cache:
            cache_key = f"news:{category or 'latest'}"
            cached_data = cache.get(cache_key)
            if cached_data:
                logger.info(f"Cache hit for news: {category or 'latest'}", module='NEWS_SERVICE')
                return cached_data
        
        # Get from database
        news_data = self.repository.get_latest_news(category)
        
        if news_data:
            # Check if data is fresh
            if auto_refresh and not self.repository.is_data_fresh(category, max_age_hours=1):
                logger.info(f"News data for {category or 'latest'} is stale, needs refresh", module='NEWS_SERVICE')
                return None  # Signal that refresh is needed
            
            # Cache for 10 minutes
            cache.set(f"news:{category or 'latest'}", news_data, ttl=600)
            logger.info(f"Retrieved news from database: {category or 'latest'}", module='NEWS_SERVICE')
        else:
            logger.info(f"No news data found in database for: {category or 'latest'}", module='NEWS_SERVICE')
        
        return news_data
    
    def save_news(self, data: Dict) -> tuple[bool, str, Optional[int]]:
        """Save news data"""
        # Validate data
        is_valid, error = self.validator.validate_news_data(data)
        if not is_valid:
            logger.error(f"Invalid news data: {error}", module='NEWS_SERVICE')
            return False, error, None
        
        # Sanitize data
        sanitized_data = self.validator.sanitize_data(data)
        
        # Save to database
        try:
            news_id = self.repository.save_news_data(sanitized_data)
            logger.info("Saved news data", module='NEWS_SERVICE')
            
            # Invalidate cache
            cache.delete("news:latest")
            
            return True, "News data saved successfully", news_id
        except Exception as e:
            logger.error(f"Failed to save news data: {e}", module='NEWS_SERVICE', exc_info=True)
            return False, str(e), None
    
    def update_risk_evaluation(self, news_id: int, risk_score: float, ollama_evaluation: str):
        """Update risk score and evaluation"""
        try:
            self.repository.update_risk_score(news_id, risk_score, ollama_evaluation)
            logger.info(f"Updated risk evaluation for news ID {news_id}", module='NEWS_SERVICE')
            
            # Invalidate cache for all news categories
            cache.delete("news:latest")
            for category in ['comprehensive', 'libya-danger-assessment', 'libya_cities', 'humanitarian', 'disasters', 'mediterranean', 'north_africa', 'lrc_operations']:
                cache.delete(f"news:{category}")
        except Exception as e:
            logger.error(f"Failed to update risk evaluation: {e}", module='NEWS_SERVICE', exc_info=True)
    
    def get_news_history(self, hours: int = 24, category: str = None) -> list:
        """Get news history"""
        return self.repository.get_news_history(hours, category)
