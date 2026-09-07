"""
Danger service for business logic
"""
from typing import Dict, Optional
from evaluation_service.core.logger import get_logger
from evaluation_service.core.cache import get_cache
from evaluation_service.modules.danger.repository import DangerRepository
from evaluation_service.modules.danger.validator import DangerValidator
from evaluation_service.modules.danger.feature_store import FeatureStore
from evaluation_service.modules.danger.data_fusion import DataFusion
from evaluation_service.modules.danger.ml_risk_engine import MLRiskEngine, KnowledgeBaseIntegrator

logger = get_logger()
cache = get_cache()

class DangerService:
    """Service layer for danger prediction operations"""
    
    def __init__(self, weather_service=None, coastal_service=None, news_service=None, 
                 news_repo=None, weather_repo=None, coastal_repo=None,
                 weather_collector=None, weather_evaluator=None,
                 coastal_collector=None, coastal_evaluator=None,
                 news_collector=None, news_evaluator=None):
        self.repository = DangerRepository()
        self.validator = DangerValidator()
        self.feature_store = FeatureStore()
        self.weather_service = weather_service
        self.coastal_service = coastal_service
        self.news_service = news_service
        self.weather_collector = weather_collector
        self.weather_evaluator = weather_evaluator
        self.coastal_collector = coastal_collector
        self.coastal_evaluator = coastal_evaluator
        self.news_collector = news_collector
        self.news_evaluator = news_evaluator
        self.data_fusion = DataFusion(weather_service, coastal_service, news_service)
        
        # Initialize ML risk engine with intelligence features enabled
        self.ml_risk_engine = MLRiskEngine(use_intelligence_features=True)
        
        # Initialize knowledge base integrator
        self.knowledge_base = KnowledgeBaseIntegrator(news_repo, weather_repo, coastal_repo)
    
    def _trigger_all_evaluations(self, city: str):
        """Trigger data collection and AI evaluation for all sources"""
        logger.info(f"Triggering all evaluations for {city}", module='DANGER_SERVICE')
        
        # Trigger weather collection and evaluation
        if self.weather_collector and self.weather_evaluator and self.weather_service:
            try:
                self.weather_collector.collect_and_save(city)
                weather_data = self.weather_service.get_weather(city, use_cache=False)
                if weather_data:
                    success, risk_score, evaluation = self.weather_evaluator.evaluate_with_fallback(weather_data)
                    if success:
                        self.weather_service.update_risk_evaluation(weather_data['id'], risk_score, evaluation)
                        logger.info(f"Weather evaluation triggered for {city}: risk={risk_score}", module='DANGER_SERVICE')
            except Exception as e:
                logger.error(f"Failed to trigger weather evaluation: {e}", module='DANGER_SERVICE', exc_info=True)
        
        # Trigger coastal collection and evaluation
        if self.coastal_collector and self.coastal_evaluator and self.coastal_service:
            try:
                self.coastal_collector.collect_and_save(city)
                coastal_data = self.coastal_service.get_coastal(city, use_cache=False)
                if coastal_data:
                    success, risk_score, evaluation = self.coastal_evaluator.evaluate(coastal_data)
                    if success:
                        self.coastal_service.update_risk_evaluation(coastal_data['id'], risk_score, evaluation)
                        logger.info(f"Coastal evaluation triggered for {city}: risk={risk_score}", module='DANGER_SERVICE')
            except Exception as e:
                logger.error(f"Failed to trigger coastal evaluation: {e}", module='DANGER_SERVICE', exc_info=True)
        
        # Trigger news collection and evaluation
        if self.news_collector and self.news_evaluator and self.news_service:
            try:
                self.news_collector.collect_and_save('comprehensive')
                news_data = self.news_service.get_news('comprehensive', use_cache=False)
                if news_data:
                    articles = news_data.get('articles', [])
                    enhanced_news_data = {
                        'article_count': len(articles),
                        'keywords': news_data.get('category', ''),
                        'titles': [a.get('title', '') for a in articles if a.get('title')],
                        'summaries': [a.get('description', '')[:200] for a in articles if a.get('description')]
                    }
                    success, risk_score, evaluation = self.news_evaluator.evaluate_with_fallback(enhanced_news_data)
                    if success:
                        self.news_service.update_risk_evaluation(news_data['id'], risk_score, evaluation)
                        logger.info(f"News evaluation triggered for {city}: risk={risk_score}", module='DANGER_SERVICE')
            except Exception as e:
                logger.error(f"Failed to trigger news evaluation: {e}", module='DANGER_SERVICE', exc_info=True)
    
    def predict_danger(self, city: str, use_cache: bool = True, force_refresh: bool = False) -> Optional[Dict]:
        """Get danger prediction for a city with full ML integration
        
        Args:
            city: City name
            use_cache: Whether to use cached predictions
            force_refresh: Force refresh all data sources and evaluations
        """
        # Force refresh bypasses cache
        if force_refresh:
            use_cache = False
        
        # Try cache first
        if use_cache:
            cache_key = f"danger:{city}"
            cached_prediction = cache.get(cache_key)
            if cached_prediction:
                logger.info(f"Cache hit for danger prediction: {city}", module='DANGER_SERVICE')
                return cached_prediction
        
        # Step 1: Trigger fresh data collection and evaluations for all sources
        if force_refresh or not use_cache:
            self._trigger_all_evaluations(city)
        
        # Step 2: Get fused data from all sources
        fused_data = self.data_fusion.get_fused_data(city)
        
        if not fused_data:
            logger.error(f"Failed to get fused data for {city}", module='DANGER_SERVICE')
            return None
        
        # Extract features
        features = self.data_fusion.extract_features(fused_data)
        
        # Load LLM evaluations from knowledge base
        llm_evaluations = self.knowledge_base.load_llm_evaluations(city)
        
        # Extract news events for intelligence features
        news_events = self._extract_news_events_for_intelligence(fused_data)
        
        # Get city location for intelligence features
        location = self._get_city_location(city)
        
        # Try ML prediction if available
        ml_prediction = None
        if self.ml_risk_engine.is_loaded():
            # Add LLM features to ML input
            enhanced_features = self.knowledge_base.add_llm_features_to_ml_input(features, llm_evaluations)
            # Predict with intelligence features
            ml_prediction = self.ml_risk_engine.predict(
                enhanced_features, 
                city=city,
                news_events=news_events,
                location=location
            )
        
        if ml_prediction:
            # Use ML prediction
            prediction = {
                'city': city,
                'risk_score': round(ml_prediction['total_risk_score'], 3),
                'risk_level': ml_prediction['risk_level'],
                'confidence': round(ml_prediction['confidence'], 3),
                'component_scores': ml_prediction['component_scores'],
                'ml_weights': ml_prediction['weights'],
                'early_warning': ml_prediction['early_warning'],
                'trend_direction': ml_prediction['trend_direction'],
                'uncertainty': ml_prediction['uncertainty'],
                'prediction_source': 'ML_MODEL',
                'llm_evaluations': llm_evaluations,
                'features': features
            }
            logger.info(f"ML prediction for {city}: {ml_prediction['risk_level']}", module='DANGER_SERVICE')
        else:
            # Fallback to rule-based prediction
            normalized_features = self.feature_store.normalize_features(features)
            component_scores = self.data_fusion.calculate_component_scores(fused_data)
            
            # Calculate overall risk score (weighted average)
            weights = {
                'weather': 0.4,
                'coastal': 0.3,
                'news': 0.3
            }
            
            overall_risk = sum(
                component_scores.get(key, 0.5) * weight 
                for key, weight in weights.items()
            )
            
            # Determine risk level
            if overall_risk >= 0.8:
                risk_level = 'EXTREME'
            elif overall_risk >= 0.6:
                risk_level = 'HIGH'
            elif overall_risk >= 0.4:
                risk_level = 'MODERATE'
            elif overall_risk >= 0.2:
                risk_level = 'LOW'
            else:
                risk_level = 'VERY LOW'
            
            # Calculate confidence based on data availability
            confidence = self._calculate_confidence(fused_data)
            
            prediction = {
                'city': city,
                'risk_score': round(overall_risk, 3),
                'risk_level': risk_level,
                'confidence': round(confidence, 3),
                'component_scores': component_scores,
                'prediction_source': 'RULE_BASED',
                'llm_evaluations': llm_evaluations,
                'features': normalized_features
            }
            logger.info(f"Rule-based prediction for {city}: {risk_level}", module='DANGER_SERVICE')
        
        # Save prediction to database
        try:
            self.repository.save_prediction(prediction)
            logger.info(f"Saved danger prediction for {city}", module='DANGER_SERVICE')
        except Exception as e:
            logger.error(f"Failed to save prediction: {e}", module='DANGER_SERVICE', exc_info=True)
        
        # Cache for 5 minutes
        cache.set(f"danger:{city}", prediction, ttl=300)
        
        return prediction
    
    def _calculate_confidence(self, fused_data: Dict) -> float:
        """Calculate confidence based on data availability"""
        available_sources = 0
        total_sources = 3  # weather, coastal, news
        
        if fused_data.get('weather'):
            available_sources += 1
        if fused_data.get('coastal'):
            available_sources += 1
        if fused_data.get('news'):
            available_sources += 1
        
        return available_sources / total_sources
    
    def save_feedback(self, data: Dict) -> tuple[bool, str, Optional[int]]:
        """Save feedback for prediction"""
        # Validate data
        is_valid, error = self.validator.validate_prediction_data(data)
        if not is_valid:
            logger.error(f"Invalid feedback data: {error}", module='DANGER_SERVICE')
            return False, error, None
        
        # Save to database
        try:
            feedback_id = self.repository.save_feedback(data)
            logger.info(f"Saved feedback for {data.get('city')}", module='DANGER_SERVICE')
            return True, "Feedback saved successfully", feedback_id
        except Exception as e:
            logger.error(f"Failed to save feedback: {e}", module='DANGER_SERVICE', exc_info=True)
            return False, str(e), None
    
    def get_prediction_history(self, city: str, hours: int = 24) -> list:
        """Get prediction history for a city"""
        return self.repository.get_prediction_history(city, hours)
    
    def get_active_alerts(self, threshold: float = 0.7) -> list:
        """Get active alerts (predictions above threshold)"""
        return self.repository.get_active_alerts(threshold)
    
    def get_all_cities(self) -> list:
        """Get all cities with predictions"""
        return self.repository.get_all_cities()
    
    def _extract_news_events_for_intelligence(self, fused_data: Dict) -> list:
        """Extract news events from fused data for intelligence features"""
        news_events = []
        news = fused_data.get('news')
        
        if news and news.get('articles'):
            for article in news['articles']:
                # Extract event information from AI-evaluated articles
                event = {
                    'event_type': article.get('event_type', 'unknown'),
                    'location': article.get('location', news.get('category', 'unknown')),
                    'severity': article.get('severity', 0.0),
                    'confidence': article.get('confidence', 0.5),
                    'timestamp': article.get('publishedAt'),
                    'lat': article.get('lat'),
                    'lng': article.get('lng')
                }
                # Only include events with valid coordinates
                if event['lat'] and event['lng'] and event['timestamp']:
                    news_events.append(event)
        
        return news_events
    
    def _get_city_location(self, city: str) -> Dict:
        """Get city coordinates for intelligence features"""
        try:
            from city_geolocation import get_city_geolocation
            geo_data = get_city_geolocation(city)
            return {
                'lat': geo_data.get('lat', 32.8872),
                'lng': geo_data.get('lon', 13.1913)
            }
        except:
            # Default to Tripoli coordinates
            return {
                'lat': 32.8872,
                'lng': 13.1913
            }
