"""
Data fusion for danger module
Reads data from weather, news, coastal, operations, and reports
"""
from typing import Dict, Optional
from evaluation_service.core.logger import get_logger

logger = get_logger()

class DataFusion:
    """Fuses data from multiple sources for danger prediction"""
    
    def __init__(self, weather_service=None, coastal_service=None, news_service=None):
        self.weather_service = weather_service
        self.coastal_service = coastal_service
        self.news_service = news_service
    
    def get_fused_data(self, city: str) -> Optional[Dict]:
        """Get fused data from all sources for a city"""
        fused_data = {
            'city': city,
            'weather': None,
            'coastal': None,
            'news': None,
            'operations': None,
            'reports': None
        }
        
        # Get weather data
        if self.weather_service:
            try:
                weather_data = self.weather_service.get_weather(city)
                if weather_data:
                    fused_data['weather'] = weather_data
            except Exception as e:
                logger.error(f"Failed to get weather data: {e}", module='DATA_FUSION')
        
        # Get coastal data (using city as location)
        if self.coastal_service:
            try:
                coastal_data = self.coastal_service.get_coastal(city)
                if coastal_data:
                    fused_data['coastal'] = coastal_data
            except Exception as e:
                logger.error(f"Failed to get coastal data: {e}", module='DATA_FUSION')
        
        # Get news data
        if self.news_service:
            try:
                news_data = self.news_service.get_news()
                if news_data:
                    fused_data['news'] = news_data
            except Exception as e:
                logger.error(f"Failed to get news data: {e}", module='DATA_FUSION')
        
        # Operations and reports would be fetched from operation system
        # For now, we'll leave them as None
        # TODO: Integrate with operation system API
        
        return fused_data
    
    def extract_features(self, fused_data: Dict) -> Dict:
        """Extract features from fused data for ML model"""
        features = {
            'city': fused_data.get('city')
        }
        
        # Extract weather features
        weather = fused_data.get('weather')
        if weather:
            features['weather_temp'] = weather.get('temperature')
            features['weather_humidity'] = weather.get('humidity')
            features['weather_pressure'] = weather.get('pressure')
            features['weather_wind'] = weather.get('wind_speed')
            features['weather_risk_score'] = weather.get('risk_score')
        else:
            # Default values if weather data missing
            features['weather_temp'] = 25.0
            features['weather_humidity'] = 50.0
            features['weather_pressure'] = 1013.0
            features['weather_wind'] = 5.0
            features['weather_risk_score'] = 0.5
        
        # Extract coastal features
        coastal = fused_data.get('coastal')
        if coastal:
            features['coastal_wave_height'] = coastal.get('wave_height')
            features['coastal_wave_period'] = coastal.get('wave_period')
            features['coastal_sea_level'] = coastal.get('sea_level_anomaly')
        else:
            # Default values if coastal data missing
            features['coastal_wave_height'] = 1.0
            features['coastal_wave_period'] = 8.0
            features['coastal_sea_level'] = 0.0
        
        # Extract news features
        news = fused_data.get('news')
        if news:
            features['news_risk_score'] = news.get('risk_score')
            features['news_article_count'] = news.get('article_count')
        else:
            # Default values if news data missing
            features['news_risk_score'] = 0.3
            features['news_article_count'] = 5
        
        return features
    
    def calculate_component_scores(self, fused_data: Dict) -> Dict:
        """Calculate individual component scores"""
        component_scores = {}
        
        # Weather component score
        weather = fused_data.get('weather')
        if weather and weather.get('risk_score'):
            component_scores['weather'] = weather['risk_score']
        else:
            component_scores['weather'] = 0.5
        
        # Coastal component score (based on wave height)
        coastal = fused_data.get('coastal')
        if coastal and coastal.get('wave_height'):
            # Normalize wave height to 0-1 range (0-30m)
            wave_score = min(coastal['wave_height'] / 30, 1.0)
            component_scores['coastal'] = wave_score
        else:
            component_scores['coastal'] = 0.3
        
        # News component score
        news = fused_data.get('news')
        if news and news.get('risk_score'):
            component_scores['news'] = news['risk_score']
        else:
            component_scores['news'] = 0.3
        
        return component_scores
