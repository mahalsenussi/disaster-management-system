"""
Evaluation Service Flask Application
Standalone evaluation and danger management system
"""
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import os
import sys

# Add parent directory to path for package imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation_service.core.logger import get_logger
from evaluation_service.core.cache import get_cache
from evaluation_service.core.auth import get_auth_validator
from evaluation_service.core.jobs import submit_job, get_job
from evaluation_service.core.ollama import get_available_models
from evaluation_service.modules.weather.service import WeatherService
from evaluation_service.modules.weather.evaluator import WeatherEvaluator
from evaluation_service.modules.weather.collector import WeatherCollector
from evaluation_service.modules.coastal.service import CoastalService
from evaluation_service.modules.coastal.evaluator import CoastalEvaluator
from evaluation_service.modules.coastal.collector import CoastalCollector
from evaluation_service.modules.news.service import NewsService
from evaluation_service.modules.news.evaluator import NewsEvaluator
from evaluation_service.modules.news.collector import NewsCollector
from evaluation_service.modules.danger.service import DangerService
from evaluation_service.modules.historical.service import HistoricalService
from evaluation_service.modules.historical.importer import HistoricalImporter
from evaluation_service.modules.chatbot.general_chat import GeneralChatbot
from evaluation_service.modules.chatbot.medical_chat import MedicalChatbot
from evaluation_service.modules.analysis.summarizer import AnalysisSummarizer

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Initialize components
logger = get_logger()
cache = get_cache()
auth_validator = get_auth_validator()

# Initialize services
weather_service = WeatherService()
weather_evaluator = WeatherEvaluator()
weather_collector = WeatherCollector()
coastal_service = CoastalService()
coastal_evaluator = CoastalEvaluator()
coastal_collector = CoastalCollector()
news_service = NewsService()
news_evaluator = NewsEvaluator()
news_collector = NewsCollector()

# Get repository instances for knowledge base integration
from evaluation_service.modules.news.repository import NewsRepository
from evaluation_service.modules.weather.repository import WeatherRepository
from evaluation_service.modules.coastal.repository import CoastalRepository

news_repo = NewsRepository()
weather_repo = WeatherRepository()
coastal_repo = CoastalRepository()

# Initialize danger service with ML model and knowledge base
danger_service = DangerService(weather_service, coastal_service, news_service, 
                              news_repo, weather_repo, coastal_repo,
                              weather_collector=weather_collector, weather_evaluator=weather_evaluator,
                              coastal_collector=coastal_collector, coastal_evaluator=coastal_evaluator,
                              news_collector=news_collector, news_evaluator=news_evaluator)
historical_service = HistoricalService()
historical_importer = HistoricalImporter()
general_chatbot = GeneralChatbot()
medical_chatbot = MedicalChatbot()
analysis_summarizer = AnalysisSummarizer()

# Configuration
EVALUATION_PORT = int(os.environ.get('EVALUATION_PORT', 5006))
OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://localhost:11434')

@app.route('/')
def index():
    """Render evaluation dashboard"""
    return render_template('dashboard.html')

@app.route('/api/weather/<city>', methods=['GET'])
def get_weather(city):
    """Get weather data for a city"""
    try:
        auto_refresh = request.args.get('auto_refresh', 'false').lower() == 'true'
        weather_data = weather_service.get_weather(city, auto_refresh=auto_refresh)
        
        if weather_data:
            return jsonify({
                'status': 'success',
                'data': weather_data,
                'needs_refresh': False
            }), 200
        elif auto_refresh:
            # Data is stale, signal that refresh is needed
            return jsonify({
                'status': 'stale',
                'message': 'Weather data is stale, needs refresh',
                'needs_refresh': True
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': 'No weather data found for this city'
            }), 404
            
    except Exception as e:
        logger.error(f"Error getting weather for {city}: {e}", module='API', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/weather/<city>/collect', methods=['POST'])
def collect_weather(city):
    """Collect weather data for a city"""
    try:
        success, message = weather_collector.collect_and_save(city)
        
        if success:
            return jsonify({
                'status': 'success',
                'message': message
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': message
            }), 400
            
    except Exception as e:
        logger.error(f"Error collecting weather for {city}: {e}", module='API', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/weather/evaluate', methods=['POST'])
def evaluate_weather():
    """Evaluate weather data with Ollama (runs async, returns job id)"""
    try:
        data = request.get_json()
        city = data.get('city')
        
        if not city:
            return jsonify({
                'status': 'error',
                'message': 'City is required'
            }), 400
        
        # Get latest weather data
        weather_data = weather_service.get_weather(city, use_cache=False)
        
        if not weather_data:
            return jsonify({
                'status': 'error',
                'message': 'No weather data found for this city'
            }), 404
        
        # Check if evaluation is fresh (less than 1 hour old)
        if weather_service.repository.is_evaluation_fresh(city, max_age_hours=1):
            logger.info(f"Weather evaluation for {city} is fresh, skipping", module='API')
            return jsonify({
                'status': 'success',
                'data': {
                    'risk_score': weather_data.get('risk_score'),
                    'evaluation': weather_data.get('ollama_evaluation'),
                    'cached': True
                }
            }), 200

        def _run():
            success, risk_score, evaluation = weather_evaluator.evaluate_with_fallback(weather_data)
            if not success:
                raise RuntimeError('Evaluation failed')
            weather_service.update_risk_evaluation(
                weather_data['id'],
                risk_score,
                evaluation
            )
            return {
                'risk_score': risk_score,
                'evaluation': evaluation,
                'cached': False
            }

        job_id = submit_job(_run)
        return jsonify({
            'status': 'running',
            'job_id': job_id,
            'message': 'Evaluation started'
        }), 202
            
    except Exception as e:
        logger.error(f"Error evaluating weather: {e}", module='API', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/weather/<city>/history', methods=['GET'])
def get_weather_history(city):
    """Get weather history for a city"""
    try:
        hours = request.args.get('hours', 24, type=int)
        history = weather_service.get_weather_history(city, hours)
        
        return jsonify({
            'status': 'success',
            'data': history
        }), 200
            
    except Exception as e:
        logger.error(f"Error getting weather history for {city}: {e}", module='API', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/weather/cities', methods=['GET'])
def get_weather_cities():
    """Get all cities with weather data"""
    try:
        cities = weather_service.get_all_cities()
        
        return jsonify({
            'status': 'success',
            'data': cities
        }), 200
            
    except Exception as e:
        logger.error(f"Error getting weather cities: {e}", module='API', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/coastal/<location>', methods=['GET'])
def get_coastal(location):
    """Get coastal data for a location"""
    try:
        auto_refresh = request.args.get('auto_refresh', 'false').lower() == 'true'
        coastal_data = coastal_service.get_coastal(location, auto_refresh=auto_refresh)
        
        if coastal_data:
            return jsonify({
                'status': 'success',
                'data': coastal_data,
                'needs_refresh': False
            }), 200
        elif auto_refresh:
            # Data is stale, signal that refresh is needed
            return jsonify({
                'status': 'stale',
                'message': 'Coastal data is stale, needs refresh',
                'needs_refresh': True
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': 'No coastal data found for this location'
            }), 404
            
    except Exception as e:
        logger.error(f"Error getting coastal for {location}: {e}", module='API', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/coastal/<location>/collect', methods=['POST'])
def collect_coastal(location):
    """Collect coastal data for a location"""
    try:
        success, message = coastal_collector.collect_and_save(location)
        
        if success:
            return jsonify({
                'status': 'success',
                'message': message
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': message
            }), 400
            
    except Exception as e:
        logger.error(f"Error collecting coastal for {location}: {e}", module='API', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/coastal/evaluate', methods=['POST'])
def evaluate_coastal():
    """Evaluate coastal data with Ollama"""
    try:
        data = request.get_json()
        location = data.get('location')
        
        if not location:
            return jsonify({
                'status': 'error',
                'message': 'Location is required'
            }), 400
        
        # Get latest coastal data
        coastal_data = coastal_service.get_coastal(location, use_cache=False)
        
        if not coastal_data:
            return jsonify({
                'status': 'error',
                'message': 'No coastal data found for this location'
            }), 404
        
        # Check if evaluation is fresh (less than 1 hour old)
        if coastal_service.repository.is_evaluation_fresh(location, max_age_hours=1):
            logger.info(f"Coastal evaluation for {location} is fresh, skipping", module='API')
            return jsonify({
                'status': 'success',
                'data': {
                    'risk_score': coastal_data.get('risk_score'),
                    'evaluation': coastal_data.get('ollama_evaluation'),
                    'cached': True
                }
            }), 200
        
        def _run():
            success, risk_score, evaluation = coastal_evaluator.evaluate(coastal_data)
            if not success:
                raise RuntimeError('Evaluation failed')
            coastal_service.update_risk_evaluation(
                coastal_data['id'],
                risk_score,
                evaluation
            )
            return {
                'risk_score': risk_score,
                'evaluation': evaluation,
                'cached': False
            }

        job_id = submit_job(_run)
        return jsonify({
            'status': 'running',
            'job_id': job_id,
            'message': 'Evaluation started'
        }), 202
            
    except Exception as e:
        logger.error(f"Error evaluating coastal: {e}", module='API', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/coastal/<location>/history', methods=['GET'])
def get_coastal_history(location):
    """Get coastal history for a location"""
    try:
        hours = request.args.get('hours', 24, type=int)
        history = coastal_service.get_coastal_history(location, hours)
        
        return jsonify({
            'status': 'success',
            'data': history
        }), 200
            
    except Exception as e:
        logger.error(f"Error getting coastal history for {location}: {e}", module='API', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/coastal/locations', methods=['GET'])
def get_coastal_locations():
    """Get all locations with coastal data"""
    try:
        locations = coastal_service.get_all_locations()
        
        return jsonify({
            'status': 'success',
            'data': locations
        }), 200
            
    except Exception as e:
        logger.error(f"Error getting coastal locations: {e}", module='API', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/news', methods=['GET'])
def get_news():
    """Get latest news data"""
    try:
        category = request.args.get('category')
        auto_refresh = request.args.get('auto_refresh', 'false').lower() == 'true'
        use_cache = request.args.get('use_cache', 'true').lower() == 'true'
        news_data = news_service.get_news(category, use_cache=use_cache, auto_refresh=auto_refresh)
        
        if news_data:
            return jsonify({
                'status': 'success',
                'data': news_data,
                'needs_refresh': False
            }), 200
        elif auto_refresh:
            # Data is stale, signal that refresh is needed
            return jsonify({
                'status': 'stale',
                'message': 'News data is stale, needs refresh',
                'needs_refresh': True
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': 'No news data found'
            }), 404
            
    except Exception as e:
        logger.error(f"Error getting news: {e}", module='API', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/news/collect', methods=['POST'])
def collect_news():
    """Collect news data"""
    try:
        category = request.json.get('category', 'comprehensive') if request.json else 'comprehensive'
        success, message = news_collector.collect_and_save(category)
        
        if success:
            return jsonify({
                'status': 'success',
                'message': message
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': message
            }), 400
            
    except Exception as e:
        logger.error(f"Error collecting news: {e}", module='API', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/news/evaluate', methods=['POST'])
def evaluate_news():
    """Evaluate news data with Ollama"""
    try:
        data = request.get_json()
        category = data.get('category') if data else None
        
        # Get latest news data
        news_data = news_service.get_news(category, use_cache=False)
        
        if not news_data:
            return jsonify({
                'status': 'error',
                'message': 'No news data found'
            }), 404
        
        # Check if evaluation is fresh (less than 1 hour old)
        if news_service.repository.is_evaluation_fresh(category, max_age_hours=1):
            logger.info(f"News evaluation for {category or 'latest'} is fresh, skipping", module='API')
            return jsonify({
                'status': 'success',
                'data': {
                    'risk_score': news_data.get('risk_score'),
                    'evaluation': news_data.get('ollama_evaluation'),
                    'cached': True
                }
            }), 200
        
        # Prepare enhanced input for evaluator with titles and summaries
        articles = news_data.get('articles', [])
        enhanced_news_data = {
            'article_count': len(articles),
            'keywords': news_data.get('category', ''),
            'titles': [a.get('title', '') for a in articles if a.get('title')],
            'summaries': [a.get('description', '')[:200] for a in articles if a.get('description')]
        }
        
        def _run():
            success, risk_score, evaluation = news_evaluator.evaluate_with_fallback(enhanced_news_data)
            if not success:
                raise RuntimeError('Evaluation failed')
            news_service.update_risk_evaluation(
                news_data['id'],
                risk_score,
                evaluation
            )
            return {
                'risk_score': risk_score,
                'evaluation': evaluation,
                'cached': False
            }

        job_id = submit_job(_run)
        return jsonify({
            'status': 'running',
            'job_id': job_id,
            'message': 'Evaluation started'
        }), 202
            
    except Exception as e:
        logger.error(f"Error evaluating news: {e}", module='API', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/news/history', methods=['GET'])
def get_news_history():
    """Get news history"""
    try:
        hours = request.args.get('hours', 24, type=int)
        history = news_service.get_news_history(hours)
        
        return jsonify({
            'status': 'success',
            'data': history
        }), 200
            
    except Exception as e:
        logger.error(f"Error getting news history: {e}", module='API', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/danger/predict/<city>', methods=['GET'])
def predict_danger(city):
    """Get danger prediction for a city"""
    try:
        force_refresh = request.args.get('force_refresh', 'false').lower() == 'true'
        prediction = danger_service.predict_danger(city, force_refresh=force_refresh)
        
        if prediction:
            return jsonify({
                'status': 'success',
                'data': prediction
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to generate prediction'
            }), 500
            
    except Exception as e:
        logger.error(f"Error predicting danger for {city}: {e}", module='API', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/danger/predict-all', methods=['POST'])
def predict_all_danger():
    """Get danger predictions for all cities with full refresh"""
    try:
        cities = ['Tripoli', 'Benghazi', 'Misrata', 'Sabha', 'Bayda', 'Tobruk', 'Zawiya', 'Ghadames']
        predictions = {}
        
        for city in cities:
            prediction = danger_service.predict_danger(city, force_refresh=True)
            if prediction:
                predictions[city] = prediction
        
        return jsonify({
            'status': 'success',
            'data': predictions
        }), 200
            
    except Exception as e:
        logger.error(f"Error predicting all danger: {e}", module='API', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/danger/feedback', methods=['POST'])
def submit_danger_feedback():
    """Submit feedback for danger prediction"""
    try:
        data = request.get_json()
        success, message, feedback_id = danger_service.save_feedback(data)
        
        if success:
            return jsonify({
                'status': 'success',
                'message': message,
                'feedback_id': feedback_id
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': message
            }), 400
            
    except Exception as e:
        logger.error(f"Error submitting danger feedback: {e}", module='API', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/danger/alerts', methods=['GET'])
def get_danger_alerts():
    """Get active danger alerts"""
    try:
        threshold = request.args.get('threshold', 0.7, type=float)
        alerts = danger_service.get_active_alerts(threshold)
        
        return jsonify({
            'status': 'success',
            'data': alerts
        }), 200
            
    except Exception as e:
        logger.error(f"Error getting danger alerts: {e}", module='API', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/danger/<city>/history', methods=['GET'])
def get_danger_history(city):
    """Get danger prediction history for a city"""
    try:
        hours = request.args.get('hours', 24, type=int)
        history = danger_service.get_prediction_history(city, hours)
        
        return jsonify({
            'status': 'success',
            'data': history
        }), 200
            
    except Exception as e:
        logger.error(f"Error getting danger history for {city}: {e}", module='API', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/historical/disasters', methods=['GET'])
def get_historical_disasters():
    """Get historical disasters"""
    try:
        country = request.args.get('country')
        disaster_type = request.args.get('type')
        limit = request.args.get('limit', 100, type=int)
        
        if country:
            disasters = historical_service.get_disasters_by_country(country)
        elif disaster_type:
            disasters = historical_service.get_disasters_by_type(disaster_type)
        else:
            disasters = historical_service.get_all_disasters(limit)
        
        return jsonify({
            'status': 'success',
            'data': disasters
        }), 200
            
    except Exception as e:
        logger.error(f"Error getting historical disasters: {e}", module='API', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/historical/map-data', methods=['GET'])
def get_historical_map_data():
    """Get historical disasters with coordinates for map visualization"""
    try:
        country = request.args.get('country')  # Optional filter by country
        limit = request.args.get('limit', 100, type=int)
        
        if country:
            disasters = historical_service.get_disasters_by_country(country)
        else:
            disasters = historical_service.get_all_disasters(limit)
        
        # Filter disasters with coordinates
        map_data = []
        for disaster in disasters:
            if disaster.get('lat') and disaster.get('lng'):
                map_data.append({
                    'id': disaster.get('id'),
                    'disaster_type': disaster.get('disaster_type'),
                    'country': disaster.get('country'),
                    'location': disaster.get('location'),
                    'date': disaster.get('date'),
                    'deaths': disaster.get('deaths'),
                    'affected': disaster.get('affected'),
                    'damage_usd': disaster.get('damage_usd'),
                    'description': disaster.get('description'),
                    'lat': disaster.get('lat'),
                    'lng': disaster.get('lng')
                })
        
        return jsonify({
            'status': 'success',
            'data': map_data,
            'count': len(map_data)
        }), 200
            
    except Exception as e:
        logger.error(f"Error getting historical map data: {e}", module='API', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/historical/patterns', methods=['GET'])
def get_historical_patterns():
    """Get disaster patterns"""
    try:
        country = request.args.get('country')
        patterns = historical_service.get_disaster_patterns(country)
        
        return jsonify({
            'status': 'success',
            'data': patterns
        }), 200
            
    except Exception as e:
        logger.error(f"Error getting historical patterns: {e}", module='API', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/historical/countries', methods=['GET'])
def get_historical_countries():
    """Get all countries with historical data"""
    try:
        countries = historical_service.get_all_countries()
        
        return jsonify({
            'status': 'success',
            'data': countries
        }), 200
            
    except Exception as e:
        logger.error(f"Error getting historical countries: {e}", module='API', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/historical/import-sample', methods=['POST'])
def import_sample_historical():
    """Import sample historical data"""
    try:
        success_count, error_count = historical_importer.import_sample_data()
        
        return jsonify({
            'status': 'success',
            'message': f'Imported {success_count} sample disasters',
            'success_count': success_count,
            'error_count': error_count
        }), 200
            
    except Exception as e:
        logger.error(f"Error importing sample historical data: {e}", module='API', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/historical/import-excel', methods=['POST'])
def import_excel_historical():
    """Import historical data from EM-DAT Excel file"""
    try:
        data = request.json
        excel_path = data.get('path')
        limit = data.get('limit', None)
        
        if not excel_path:
            return jsonify({
                'status': 'error',
                'message': 'Excel file path is required'
            }), 400
        
        success_count, error_count = historical_importer.import_from_excel(excel_path, limit)
        
        return jsonify({
            'status': 'success',
            'message': f'Imported {success_count} disasters from Excel',
            'success_count': success_count,
            'error_count': error_count
        }), 200
            
    except Exception as e:
        logger.error(f"Error importing Excel historical data: {e}", module='API', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/chatbot/general', methods=['POST'])
def general_chatbot():
    """General chatbot endpoint"""
    try:
        data = request.get_json()
        message = data.get('message')
        
        if not message:
            return jsonify({
                'status': 'error',
                'message': 'Message is required'
            }), 400
        
        success, response = general_chatbot.respond(message)
        
        if success:
            return jsonify({
                'status': 'success',
                'response': response
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': response
            }), 500
            
    except Exception as e:
        logger.error(f"Error in general chatbot: {e}", module='API', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/chatbot/medical', methods=['POST'])
def medical_chatbot():
    """Medical chatbot endpoint"""
    try:
        data = request.get_json()
        message = data.get('message')
        
        if not message:
            return jsonify({
                'status': 'error',
                'message': 'Message is required'
            }), 400
        
        success, response = medical_chatbot.respond(message)
        
        if success:
            return jsonify({
                'status': 'success',
                'response': response
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': response
            }), 500
            
    except Exception as e:
        logger.error(f"Error in medical chatbot: {e}", module='API', exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/chatbot/status', methods=['GET'])
def chatbot_status():
    """Get chatbot system status"""
    try:
        # Check if medgemma1.5 is available via Ollama
        medical_ai_available = False
        try:
            import requests
            response = requests.get('http://localhost:11434/api/tags', timeout=2)
            if response.status_code == 200:
                models = response.json().get('models', [])
                medical_ai_available = any('medgemma1.5' in m.get('name', '') for m in models)
        except:
            pass
        
        return jsonify({
            'success': True,
            'lrc_helper': {
                'available': True,
                'model': 'cloud-based'
            },
            'medical_ai': {
                'available': medical_ai_available,
                'model': 'medgemma1.5:latest' if medical_ai_available else 'not available'
            }
        }), 200
            
    except Exception as e:
        logger.error(f"Error getting chatbot status: {e}", module='API', exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/knowledge-base/entries', methods=['GET'])
def get_knowledge_entries():
    """Get knowledge base entries"""
    try:
        from evaluation_service.repositories.knowledge_base import KnowledgeBaseRepository
        
        kb_repo = KnowledgeBaseRepository()
        category = request.args.get('category')
        search = request.args.get('search')
        
        if category:
            entries = kb_repo.get_entries_by_category(category)
        elif search:
            entries = kb_repo.search_entries(search)
        else:
            entries = kb_repo.get_knowledge_context(max_entries=100)
            # Parse context back to entries format
            entries = kb_repo.execute_query("SELECT * FROM knowledge_entries WHERE is_active = 1 ORDER BY priority DESC, created_at DESC LIMIT 100")
        
        return jsonify({
            'success': True,
            'entries': entries,
            'count': len(entries)
        }), 200
            
    except Exception as e:
        logger.error(f"Error getting knowledge entries: {e}", module='API', exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/knowledge-base/entries', methods=['POST'])
def add_knowledge_entry():
    """Add a new knowledge base entry"""
    try:
        from evaluation_service.repositories.knowledge_base import KnowledgeBaseRepository
        
        data = request.get_json()
        kb_repo = KnowledgeBaseRepository()
        
        entry_id = kb_repo.add_entry(
            category=data.get('category'),
            title=data.get('title'),
            content=data.get('content'),
            source=data.get('source'),
            source_url=data.get('source_url'),
            tags=data.get('tags'),
            priority=data.get('priority', 0)
        )
        
        return jsonify({
            'success': True,
            'entry_id': entry_id,
            'message': 'Knowledge entry added successfully'
        }), 200
            
    except Exception as e:
        logger.error(f"Error adding knowledge entry: {e}", module='API', exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/knowledge-base/categories', methods=['GET'])
def get_knowledge_categories():
    """Get knowledge base categories"""
    try:
        from evaluation_service.repositories.knowledge_base import KnowledgeBaseRepository
        
        kb_repo = KnowledgeBaseRepository()
        categories = kb_repo.get_all_categories()
        
        return jsonify({
            'success': True,
            'categories': categories
        }), 200
            
    except Exception as e:
        logger.error(f"Error getting categories: {e}", module='API', exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/chatbot/message', methods=['POST'])
def chatbot_message():
    """Enhanced chatbot endpoint with file upload and routing"""
    try:
        from evaluation_service.repositories.chat_repository import ChatRepository
        import requests
        import base64
        import tempfile
        import os
        
        message = request.form.get('message', '')
        mode = request.form.get('mode', 'auto')
        session_id = request.form.get('session_id', '')
        file = request.files.get('file')
        
        # Initialize chat repository
        chat_repo = ChatRepository()
        
        # Create session if not exists
        if session_id and not chat_repo.get_session_info(session_id):
            chat_repo.create_session(session_id)
        
        # Store user message
        if session_id:
            chat_repo.add_message(session_id, 'user', message, metadata={'mode': mode, 'has_file': bool(file)})
        
        # Routing logic
        response_text = ""
        model_used = ""
        routing_info = {}
        file_path = None
        
        if file:
            # Save uploaded file temporarily
            temp_dir = tempfile.mkdtemp()
            file_path = os.path.join(temp_dir, file.filename)
            file.save(file_path)
            
            # Read and encode image
            with open(file_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            
            # Call Ollama medgemma1.5 for image analysis
            prompt = message if message else "Please analyze this medical image. Describe what you see, identify any abnormalities, and provide your assessment."
            
            try:
                ollama_response = requests.post(
                    'http://localhost:11434/api/generate',
                    json={
                        "model": "minimax-m3:cloud",  # Using cloud model for faster response
                        "prompt": prompt,
                        "images": [image_data],
                        "stream": False,
                        "system": """You are a Medical AI Assistant for the Libyan Red Crescent (LRC). Your role is to provide professional medical image analysis to support emergency medical teams.

ANALYSIS FORMAT:
1. CLINICAL IMPRESSION: Brief summary of findings
2. DETAILED FINDINGS: Specific observations (anatomical structures, abnormalities, patterns)
3. DIFFERENTIAL DIAGNOSIS: Possible conditions based on findings
4. URGENCY LEVEL: LOW/MEDIUM/HIGH/CRITICAL
5. RECOMMENDATIONS: Next steps and follow-up actions
6. DISCLAIMER: Standard medical disclaimer

GUIDELINES:
- Use professional medical terminology
- Be specific and precise in your observations
- Prioritize life-threatening findings
- Consider resource constraints in emergency settings
- Always include appropriate medical disclaimer
- Recommend verification with qualified medical personnel
- Flag urgent findings prominently

RESPONSE STYLE:
- Professional and clinical
- Concise but comprehensive
- Action-oriented for emergency situations
- Culturally appropriate for Libyan context"""
                    },
                    timeout=180  # 3 minutes for cloud model
                )
                
                if ollama_response.status_code == 200:
                    result = ollama_response.json()
                    response_text = result.get('response', 'Analysis completed but no response generated.')
                    model_used = "minimax-m3:cloud"
                    routing_info = {'route': 'medical_ai', 'reasoning': 'File upload detected - medical image analysis'}
                else:
                    response_text = f"Error calling medical AI: {ollama_response.status_code}"
                    model_used = "medical_ai (error)"
                    routing_info = {'route': 'medical_ai', 'reasoning': 'File upload - API error'}
            
            except Exception as e:
                response_text = f"Medical AI error: {str(e)}"
                model_used = "medical_ai (error)"
                routing_info = {'route': 'medical_ai', 'reasoning': 'File upload - processing error'}
            
            # Clean up temp file
            try:
                os.remove(file_path)
                os.rmdir(temp_dir)
            except:
                pass
        
        elif mode == 'medical_ai':
            # Medical AI text query
            try:
                ollama_response = requests.post(
                    'http://localhost:11434/api/generate',
                    json={
                        "model": "minimax-m3:cloud",  # Using cloud model for faster response
                        "prompt": message,
                        "stream": False,
                        "system": """You are a Medical AI Assistant for the Libyan Red Crescent (LRC). Provide professional medical guidance for emergency situations.

RESPONSE FORMAT:
1. ASSESSMENT: Clinical evaluation
2. RECOMMENDATIONS: Actionable steps
3. URGENCY: Priority level
4. DISCLAIMER: Medical disclaimer

GUIDELINES:
- Use professional medical terminology
- Prioritize life-threatening conditions
- Consider emergency resource constraints
- Always recommend professional verification
- Be concise and action-oriented"""
                    },
                    timeout=60
                )
                
                if ollama_response.status_code == 200:
                    result = ollama_response.json()
                    response_text = result.get('response', 'No response generated.')
                    model_used = "minimax-m3:cloud"
                    routing_info = {'route': 'medical_ai', 'reasoning': 'Manual mode selection'}
                else:
                    response_text = f"Error calling medical AI: {ollama_response.status_code}"
                    model_used = "medical_ai (error)"
                    routing_info = {'route': 'medical_ai', 'reasoning': 'API error'}
            
            except Exception as e:
                response_text = f"Medical AI error: {str(e)}"
                model_used = "medical_ai (error)"
                routing_info = {'route': 'medical_ai', 'reasoning': 'Processing error'}
        
        else:
            # Default to LRC helper with knowledge base
            try:
                from evaluation_service.repositories.knowledge_base import KnowledgeBaseRepository
                
                # Get knowledge context
                kb_repo = KnowledgeBaseRepository()
                knowledge_context = kb_repo.get_knowledge_context(max_entries=30)
                
                # Build prompt with knowledge base
                system_prompt = f"""You are the LRC (Libyan Red Crescent) Emergency Intelligence Assistant. You provide humanitarian information, operational guidance, and support for emergency response.

KNOWLEDGE BASE:
{knowledge_context}

RESPONSE GUIDELINES:
- Answer ONLY using information from the knowledge base (LRC, IFRC, ICRC, UN sources)
- If information is not available in the knowledge base, state that clearly
- Prioritize humanitarian principles and safety
- Provide operational information when relevant
- Include contact information and addresses when available
- Be professional, accurate, and helpful
- For weather, danger, or technical data, acknowledge but focus on humanitarian aspects

RESPONSE FORMAT:
- Direct and actionable
- Cite sources when possible (e.g., "According to LRC...")
- Include relevant contact information or addresses
- If unsure, recommend contacting LRC directly

You support LRC volunteers, staff, and the public with humanitarian information and operational guidance."""

                ollama_response = requests.post(
                    'http://localhost:11434/api/generate',
                    json={
                        "model": "minimax-m3:cloud",
                        "prompt": message,
                        "stream": False,
                        "system": system_prompt
                    },
                    timeout=60
                )
                
                if ollama_response.status_code == 200:
                    result = ollama_response.json()
                    response_text = result.get('response', 'No response generated.')
                    model_used = "minimax-m3:cloud"
                    routing_info = {'route': 'lrc_helper', 'reasoning': 'Knowledge-based LRC assistance'}
                else:
                    # Fallback to simple responses
                    message_lower = message.lower()
                    if 'weather' in message_lower:
                        response_text = "I can help you with weather information. Our system provides real-time weather data for Libyan cities including Tripoli, Benghazi, and Misrata. Would you like me to check current conditions for a specific location?"
                    elif 'danger' in message_lower or 'risk' in message_lower:
                        response_text = "I can provide danger assessment based on multiple data sources including weather patterns, news analysis, and historical incident data. Our AI system evaluates risks and provides recommendations for emergency response teams."
                    elif 'help' in message_lower:
                        response_text = "I'm the LRC Emergency Intelligence System Assistant. I can help with:\n\n• Weather monitoring and analysis\n• Marine and coastal safety data\n• Danger assessment and risk evaluation\n• Team and resource coordination\n• Emergency response planning\n• Medical image analysis (upload X-rays, CT scans)\n\nHow can I assist you today?"
                    else:
                        response_text = f"I'm here to help with the LRC Emergency Intelligence System. I can provide information about weather conditions, marine safety, danger assessments, and coordinate emergency response efforts. For medical image analysis, please upload the image."
                    model_used = "lrc_helper (fallback)"
                    routing_info = {'route': 'lrc_helper', 'reasoning': 'API error - fallback response'}
            
            except Exception as e:
                # Fallback to simple responses
                message_lower = message.lower()
                if 'weather' in message_lower:
                    response_text = "I can help you with weather information. Our system provides real-time weather data for Libyan cities including Tripoli, Benghazi, and Misrata. Would you like me to check current conditions for a specific location?"
                elif 'danger' in message_lower or 'risk' in message_lower:
                    response_text = "I can provide danger assessment based on multiple data sources including weather patterns, news analysis, and historical incident data. Our AI system evaluates risks and provides recommendations for emergency response teams."
                elif 'help' in message_lower:
                    response_text = "I'm the LRC Emergency Intelligence System Assistant. I can help with:\n\n• Weather monitoring and analysis\n• Marine and coastal safety data\n• Danger assessment and risk evaluation\n• Team and resource coordination\n• Emergency response planning\n• Medical image analysis (upload X-rays, CT scans)\n\nHow can I assist you today?"
                else:
                    response_text = f"I'm here to help with the LRC Emergency Intelligence System. I can provide information about weather conditions, marine safety, danger assessments, and coordinate emergency response efforts. For medical image analysis, please upload the image."
                model_used = "lrc_helper (fallback)"
                routing_info = {'route': 'lrc_helper', 'reasoning': f'Error: {str(e)}'}
        
        # Store assistant response
        if session_id:
            chat_repo.add_message(session_id, 'assistant', response_text, model=model_used, metadata=routing_info)
            chat_repo.update_session_activity(session_id, model_used)
        
        return jsonify({
            'success': True,
            'response': response_text,
            'model': model_used,
            'routing': routing_info,
            'session_id': session_id
        }), 200
            
    except Exception as e:
        logger.error(f"Error in chatbot message: {e}", module='API', exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/analysis/summarize', methods=['POST'])
def analysis_summarize():
    """Aggregate context -> structured AI summary (used by public_app).

    Defaults to synchronous (cloud-backed, ~1-3s). Pass ?async=1 for a
    job_id + polling model instead.
    """
    data = request.get_json() or {}
    kind = data.get('kind') or 'poi_category'
    contexts = data.get('contexts') or []
    if request.args.get('async') == '1':
        job_id = submit_job(analysis_summarizer.summarize, contexts, kind)
        return jsonify({'job_id': job_id, 'status': 'running'}), 202
    return jsonify(analysis_summarizer.summarize(contexts, kind))

@app.route('/api/analysis/status', methods=['GET'])
def analysis_status():
    """Report summarizer health and available Ollama models."""
    try:
        models = get_available_models(OLLAMA_URL)
        if not models:
            models = analysis_summarizer.model_priority
        return jsonify({'status': 'ok', 'models': models, 'priority': analysis_summarizer.model_priority})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/jobs/<job_id>', methods=['GET'])
def job_status(job_id):
    """Check the status of an async evaluation job"""
    job = get_job(job_id)
    if job is None:
        return jsonify({
            'status': 'error',
            'message': 'Job not found'
        }), 404

    response = {
        'status': job['status'],
        'job_id': job_id
    }
    if job['status'] == 'success':
        response['data'] = job['result']
    elif job['status'] == 'error':
        response['message'] = job.get('error') or 'Evaluation failed'
    return jsonify(response), 200

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'evaluation_service',
        'version': '1.0.0'
    }), 200

def start_scheduler():
    """Start background scheduler for periodic news/weather/coastal collection.

    Keeps live data fresh for the operations dashboard. Jobs are staggered
    to respect third-party API rate limits. Never crashes the service.
    """
    try:
        from evaluation_service.scheduler.master_scheduler import get_scheduler
        scheduler = get_scheduler()

        news_categories = ['comprehensive', 'libya-danger-assessment', 'libya_cities',
                           'humanitarian', 'disasters', 'mediterranean', 'north_africa', 'lrc_operations']
        weather_cities = ['Tripoli', 'Benghazi', 'Misrata', 'Sabha', 'Bayda',
                          'Ghadames', 'Tobruk', 'Zawiya']
        coastal_locations = ['Tripoli', 'Benghazi', 'Misrata', 'Derna',
                             'Sirte', 'Tobruk', 'Zawiya', 'Al Khums']

        # Stagger jobs 2 minutes apart within each hour to avoid rate limits
        offset = 0
        for cat in news_categories:
            scheduler.add_job(f'news_{cat}', lambda c=cat: news_collector.collect_and_save(c),
                              interval_minutes=60, at_time=f'00:{offset:02d}')
            offset += 2
        for city in weather_cities:
            scheduler.add_job(f'weather_{city}', lambda c=city: weather_collector.collect_and_save(c),
                              interval_minutes=60, at_time=f'00:{offset:02d}')
            offset += 2
        for loc in coastal_locations:
            scheduler.add_job(f'coastal_{loc}', lambda l=loc: coastal_collector.collect_and_save(l),
                              interval_minutes=60, at_time=f'00:{offset:02d}')
            offset += 2

        scheduler.start()
        logger.info(f"Scheduler started with {len(scheduler.get_jobs())} jobs", module='MAIN')
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}", module='MAIN', exc_info=True)


if __name__ == '__main__':
    logger.info(f"Starting Evaluation Service on port {EVALUATION_PORT}", module='MAIN')
    start_scheduler()
    app.run(host='0.0.0.0', port=EVALUATION_PORT, debug=True, use_reloader=False, threaded=True)
