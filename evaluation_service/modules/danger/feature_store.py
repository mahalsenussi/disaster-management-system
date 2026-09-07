"""
Feature store for data alignment and normalization
Aligns timestamps from multiple sources and normalizes data for AI model
"""
from typing import Dict, Optional
from datetime import datetime, timedelta
from evaluation_service.core.logger import get_logger
from evaluation_service.core.cache import get_cache

logger = get_logger()
cache = get_cache()

class FeatureStore:
    """Aggregates and normalizes features from multiple sources"""
    
    def __init__(self):
        self._feature_cache = {}
    
    def get_features(self, city: str, use_cache: bool = True) -> Optional[Dict]:
        """Get aggregated features for a city"""
        cache_key = f"features:{city}"
        
        if use_cache:
            cached_features = cache.get(cache_key)
            if cached_features:
                logger.info(f"Cache hit for features: {city}", module='FEATURE_STORE')
                return cached_features
        
        # Aggregate features from all sources
        features = self._aggregate_features(city)
        
        if features:
            # Cache for 5 minutes
            cache.set(cache_key, features, ttl=300)
            logger.info(f"Aggregated features for {city}", module='FEATURE_STORE')
        
        return features
    
    def _aggregate_features(self, city: str) -> Optional[Dict]:
        """Aggregate features from weather, coastal, and news sources"""
        from evaluation_service.modules.news.service import NewsService
        from evaluation_service.modules.news.repository import NewsRepository

        features = {
            'city': city,
            'weather_temp': None,
            'weather_humidity': None,
            'weather_pressure': None,
            'weather_wind': None,
            'coastal_wave_height': None,
            'coastal_wave_period': None,
            'coastal_sea_level': None,
            'news_risk_score': 0.0,
            'news_article_count': 0,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Fetch real news data
        try:
            news_repo = NewsRepository()
            news_data = news_repo.get_latest_news('comprehensive')
            if news_data:
                risk_score = news_data.get('risk_score') or 0.0
                features['news_risk_score'] = min(max(float(risk_score), 0.0), 1.0)
                features['news_article_count'] = news_data.get('total_articles') or len(news_data.get('articles', []) or [])
                features['news_last_updated'] = news_data.get('collected_at')
                logger.info(f"Using real news data for {city}: risk={features['news_risk_score']}, articles={features['news_article_count']}", module='FEATURE_STORE')
            else:
                logger.info(f"No news data found for feature store city {city}", module='FEATURE_STORE')
        except Exception as e:
            logger.error(f"Failed to fetch news data for feature store: {e}", module='FEATURE_STORE')

        # Fetch real weather and coastal data if available
        try:
            from evaluation_service.modules.weather.service import WeatherService
            from evaluation_service.modules.coastal.service import CoastalService
            weather_service = WeatherService()
            coastal_service = CoastalService()
            weather_data = weather_service.get_weather(city, use_cache=False, auto_refresh=False)
            if weather_data:
                features['weather_temp'] = weather_data.get('temperature')
                features['weather_humidity'] = weather_data.get('humidity')
                features['weather_pressure'] = weather_data.get('pressure')
                features['weather_wind'] = weather_data.get('wind_speed')
                features['weather_risk_score'] = weather_data.get('risk_score')
            coastal_data = coastal_service.get_coastal(city, use_cache=False)
            if coastal_data:
                features['coastal_wave_height'] = coastal_data.get('wave_height')
                features['coastal_wave_period'] = coastal_data.get('wave_period')
                features['coastal_sea_level'] = coastal_data.get('sea_level_anomaly')
        except Exception as e:
            logger.warning(f"Failed to fetch weather/coastal data for feature store: {e}", module='FEATURE_STORE')

        return features
    
    def normalize_features(self, features: Dict) -> Dict:
        """Normalize features for ML model input"""
        normalized = {}
        
        # Normalize temperature (0-1 range)
        if 'weather_temp' in features:
            normalized['weather_temp_norm'] = (features['weather_temp'] - 0) / 60
        
        # Normalize humidity (0-1 range)
        if 'weather_humidity' in features:
            normalized['weather_humidity_norm'] = features['weather_humidity'] / 100
        
        # Normalize pressure (0-1 range)
        if 'weather_pressure' in features:
            normalized['weather_pressure_norm'] = (features['weather_pressure'] - 800) / 400
        
        # Normalize wind speed (0-1 range)
        if 'weather_wind' in features:
            normalized['weather_wind_norm'] = features['weather_wind'] / 200
        
        # Normalize wave height (0-1 range)
        if 'coastal_wave_height' in features:
            normalized['coastal_wave_height_norm'] = features['coastal_wave_height'] / 30
        
        # Normalize news risk score (already 0-1)
        if 'news_risk_score' in features:
            normalized['news_risk_score_norm'] = features['news_risk_score']
        
        return normalized
    
    def align_timestamps(self, features_list: list) -> list:
        """Align timestamps from multiple sources to nearest minute"""
        aligned = []
        
        for features in features_list:
            if 'timestamp' in features:
                try:
                    dt = datetime.fromisoformat(features['timestamp'])
                    # Round to nearest minute
                    aligned_dt = dt.replace(second=0, microsecond=0)
                    features['timestamp'] = aligned_dt.isoformat()
                except Exception as e:
                    logger.warning(f"Failed to align timestamp: {e}", module='FEATURE_STORE')
            
            aligned.append(features)
        
        return aligned
    
    def invalidate_cache(self, city: str):
        """Invalidate feature cache for a city"""
        cache_key = f"features:{city}"
        cache.delete(cache_key)
        logger.info(f"Invalidated feature cache for {city}", module='FEATURE_STORE')
