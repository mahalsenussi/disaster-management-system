#!/usr/bin/env python3
"""
ML Risk Engine Integration
Integrates the disaster prediction ML model from /home/mahmoud/v2/ml
"""
import sys
import os
from typing import Dict, Optional
from evaluation_service.core.logger import get_logger

logger = get_logger()

# Add ML module to path
ML_MODULE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), 'ml')
sys.path.insert(0, ML_MODULE_PATH)

class MLRiskEngine:
    """Wrapper for the ML disaster prediction risk engine with intelligence features"""
    
    def __init__(self, use_intelligence_features=True):
        """Initialize ML risk engine with models
        
        Args:
            use_intelligence_features: Enable intelligence features from news events
        """
        self.risk_engine = None
        self.features = None
        self.scaler = None
        self.model_loaded = False
        self.use_intelligence_features = use_intelligence_features
        
        try:
            # Import the risk engine from ML module
            from risk_engine_v2 import RiskEngineV2
            self.risk_engine = RiskEngineV2(use_intelligence_features=use_intelligence_features)
            self.model_loaded = True
            logger.info(f"ML risk engine loaded successfully (intelligence: {use_intelligence_features})", module='ML_RISK_ENGINE')
        except Exception as e:
            logger.error(f"Failed to load ML risk engine: {e}", module='ML_RISK_ENGINE')
            self.model_loaded = False
    
    def predict(self, features: Dict, city: str = 'unknown', news_events: Optional[list] = None, location: Optional[Dict] = None) -> Optional[Dict]:
        """
        Predict risk using ML model with intelligence features
        
        Args:
            features: Dictionary of features matching ML model requirements
            city: City name for risk history tracking
            news_events: Optional list of AI-evaluated news events for intelligence features
            location: Optional dictionary with 'lat' and 'lng' for intelligence features
            
        Returns:
            Dictionary with risk prediction or None if model not loaded
        """
        if not self.model_loaded or not self.risk_engine:
            logger.warning("ML model not loaded, returning None", module='ML_RISK_ENGINE')
            return None
        
        try:
            # Map danger module features to ML model features
            ml_features = self._map_features_to_ml_format(features, city)
            
            # Get prediction from ML engine with intelligence features
            prediction = self.risk_engine.predict(
                ml_features, 
                city=city,
                news_events=news_events,
                location=location
            )
            
            logger.info(f"ML prediction for {city}: {prediction['risk_level']} (intelligence: {prediction.get('intelligence_enabled', False)})", module='ML_RISK_ENGINE')
            return prediction
            
        except Exception as e:
            logger.error(f"Error in ML prediction: {e}", module='ML_RISK_ENGINE', exc_info=True)
            return None
    
    def _map_features_to_ml_format(self, features: Dict, city: str) -> Dict:
        """
        Map danger module features to ML model feature format
        
        Args:
            features: Features from danger module
            city: City name for geolocation
            
        Returns:
            Dictionary in ML model format
        """
        # Import city geolocation from ML module
        try:
            from city_geolocation import get_city_geolocation
            geo_data = get_city_geolocation(city)
        except:
            geo_data = {
                'lat': 32.8872,  # Default to Tripoli
                'lon': 13.1913,
                'elevation': 25,
                'distance_to_coast': 0.0
            }
        
        # Map features
        ml_features = {
            # Weather features
            'weather_airPressure': features.get('weather_pressure', 1013),
            'weather_airQuality': features.get('weather_humidity', 50),  # Using humidity as proxy
            'weather_weather_risk_score': features.get('weather_risk_score', 0.5),
            'weather_weather_risk_level': self._risk_level_to_numeric(features.get('weather_risk_level', 'MEDIUM')),
            
            # Marine/Coastal features
            'marine_sea_level_anomaly': features.get('coastal_sea_level', 0.0),
            'marine_swell_wave_height': features.get('coastal_wave_height', 1.0),
            'marine_wave_height': features.get('coastal_wave_height', 1.0),
            'marine_wave_period': features.get('coastal_wave_period', 8.0),
            'marine_wind_speed': features.get('weather_wind', 5.0),
            'marine_wind_wave_height': features.get('coastal_wave_height', 1.0),
            
            # News features
            'news_news_critical': 0,  # Would need to extract from news data
            'news_news_high': 0,  # Would need to extract from news data
            'news_news_medium': 0,  # Would need to extract from news data
            'news_news_low': 0,  # Would need to extract from news data
            'news_news_total_articles': features.get('news_article_count', 5),
            'news_news_risk_score': features.get('news_risk_score', 0.3),
            'news_alert_intensity': 1,  # Default
            
            # Geographic features
            'geo_lat': geo_data.get('lat', 32.8872),
            'geo_lon': geo_data.get('lon', 13.1913),
            'geo_elevation': geo_data.get('elevation', 25),
            'geo_distance_to_coast': geo_data.get('distance_to_coast', 0.0),
            
            # Time-series features (would need historical data)
            'wave_delta': features.get('wave_delta', 0.0),
            'pressure_diff': features.get('pressure_diff', 0.0),
            'news_spike': features.get('news_spike', 0.0)
        }
        
        return ml_features
    
    def _risk_level_to_numeric(self, risk_level: str) -> int:
        """Convert risk level string to numeric"""
        risk_map = {
            'LOW': 0,
            'MEDIUM': 1,
            'HIGH': 2,
            'CRITICAL': 3,
            'EXTREME': 3
        }
        return risk_map.get(risk_level.upper(), 1)
    
    def is_loaded(self) -> bool:
        """Check if ML model is loaded"""
        return self.model_loaded


class KnowledgeBaseIntegrator:
    """Integrates LLM AI evaluations from databases as ML knowledge base"""
    
    def __init__(self, news_repo=None, weather_repo=None, coastal_repo=None):
        """Initialize knowledge base integrator"""
        self.news_repo = news_repo
        self.weather_repo = weather_repo
        self.coastal_repo = coastal_repo
        self.llm_evaluations = {}
    
    def load_llm_evaluations(self, city: str = None) -> Dict:
        """
        Load LLM AI evaluations from databases
        
        Args:
            city: Optional city filter
            
        Returns:
            Dictionary with LLM evaluations from all sources
        """
        evaluations = {
            'news': None,
            'weather': None,
            'coastal': None,
            'combined_sentiment': 0.0,
            'combined_risk_assessment': 'UNKNOWN'
        }
        
        # Load news LLM evaluation
        if self.news_repo:
            try:
                news_data = self.news_repo.get_latest_news()
                if news_data and news_data.get('ollama_evaluation'):
                    evaluations['news'] = news_data['ollama_evaluation']
                    logger.info("Loaded news LLM evaluation", module='KNOWLEDGE_BASE')
            except Exception as e:
                logger.error(f"Failed to load news LLM evaluation: {e}", module='KNOWLEDGE_BASE')
        
        # Load weather LLM evaluation
        if self.weather_repo:
            try:
                weather_data = self.weather_repo.get_latest_weather(city)
                if weather_data and weather_data.get('ollama_evaluation'):
                    evaluations['weather'] = weather_data['ollama_evaluation']
                    logger.info("Loaded weather LLM evaluation", module='KNOWLEDGE_BASE')
            except Exception as e:
                logger.error(f"Failed to load weather LLM evaluation: {e}", module='KNOWLEDGE_BASE')
        
        # Load coastal LLM evaluation
        if self.coastal_repo:
            try:
                coastal_data = self.coastal_repo.get_latest_coastal(city)
                if coastal_data and coastal_data.get('ollama_evaluation'):
                    evaluations['coastal'] = coastal_data['ollama_evaluation']
                    logger.info("Loaded coastal LLM evaluation", module='KNOWLEDGE_BASE')
            except Exception as e:
                logger.error(f"Failed to load coastal LLM evaluation: {e}", module='KNOWLEDGE_BASE')
        
        # Combine evaluations for ML model
        evaluations['combined'] = self._combine_evaluations(evaluations)
        
        return evaluations
    
    def _combine_evaluations(self, evaluations: Dict) -> Dict:
        """Combine LLM evaluations into knowledge base features"""
        combined = {
            'has_news_evaluation': evaluations['news'] is not None,
            'has_weather_evaluation': evaluations['weather'] is not None,
            'has_coastal_evaluation': evaluations['coastal'] is not None,
            'evaluation_count': sum([
                evaluations['news'] is not None,
                evaluations['weather'] is not None,
                evaluations['coastal'] is not None
            ]),
            'news_sentiment_score': self._extract_sentiment(evaluations['news']),
            'weather_sentiment_score': self._extract_sentiment(evaluations['weather']),
            'coastal_sentiment_score': self._extract_sentiment(evaluations['coastal']),
        }
        
        # Calculate average sentiment
        sentiments = [
            combined['news_sentiment_score'],
            combined['weather_sentiment_score'],
            combined['coastal_sentiment_score']
        ]
        valid_sentiments = [s for s in sentiments if s is not None]
        if valid_sentiments:
            combined['average_sentiment'] = sum(valid_sentiments) / len(valid_sentiments)
        else:
            combined['average_sentiment'] = 0.5
        
        return combined
    
    def _extract_sentiment(self, evaluation: str) -> Optional[float]:
        """Extract sentiment score from LLM evaluation text"""
        if not evaluation:
            return None
        
        # Simple keyword-based sentiment extraction
        # In production, this would use NLP
        evaluation_lower = evaluation.lower()
        
        positive_keywords = ['safe', 'normal', 'stable', 'good', 'low risk', 'minimal']
        negative_keywords = ['danger', 'risk', 'severe', 'critical', 'high', 'warning', 'alert']
        
        positive_count = sum(1 for kw in positive_keywords if kw in evaluation_lower)
        negative_count = sum(1 for kw in negative_keywords if kw in evaluation_lower)
        
        total = positive_count + negative_count
        if total == 0:
            return 0.5
        
        # Return sentiment (0 = negative, 1 = positive)
        return positive_count / total
    
    def add_llm_features_to_ml_input(self, ml_features: Dict, llm_evaluations: Dict) -> Dict:
        """
        Add LLM evaluation features to ML model input
        
        Args:
            ml_features: Existing ML features
            llm_evaluations: LLM evaluations from knowledge base
            
        Returns:
            Enhanced ML features with LLM knowledge
        """
        combined = llm_evaluations.get('combined', {})
        
        # Add LLM-derived features
        ml_features['llm_evaluation_count'] = combined.get('evaluation_count', 0)
        ml_features['llm_average_sentiment'] = combined.get('average_sentiment', 0.5)
        ml_features['llm_news_sentiment'] = combined.get('news_sentiment_score', 0.5)
        ml_features['llm_weather_sentiment'] = combined.get('weather_sentiment_score', 0.5)
        ml_features['llm_coastal_sentiment'] = combined.get('coastal_sentiment_score', 0.5)
        
        return ml_features
