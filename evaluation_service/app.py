"""
Evaluation Service Flask Application
Standalone evaluation and danger management system
"""
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional, List

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
from evaluation_service.modules.marine.service import MarineService
from evaluation_service.modules.marine.evaluator import MarineEvaluator
from evaluation_service.modules.marine.collector import MarineCollector
from evaluation_service.modules.marine import openmeteo as marine_openmeteo
from evaluation_service.modules.news.service import NewsService
from evaluation_service.modules.news.evaluator import NewsEvaluator
from evaluation_service.modules.news.collector import NewsCollector
from evaluation_service.modules.danger.service import DangerService
from evaluation_service.modules.historical.service import HistoricalService
from evaluation_service.modules.historical.importer import HistoricalImporter
from evaluation_service.modules.chatbot.general_chat import GeneralChatbot
from evaluation_service.modules.chatbot.medical_chat import MedicalChatbot
from evaluation_service.modules.analysis.summarizer import AnalysisSummarizer
from evaluation_service.modules import forecast as forecast_module
from evaluation_service.modules.forecast import openmeteo as forecast_openmeteo

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
marine_service = MarineService()
marine_evaluator = MarineEvaluator()
marine_collector = MarineCollector()
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

# ------------------------------------------------------------------ marine endpoints
@app.route('/weather-map')
@app.route('/weather-map/')
def weather_map():
    """Serve the interactive weather / sea-level / currents map."""
    return render_template('weather_map.html')

@app.route('/api/marine/currents', methods=['GET'])
def get_marine_currents():
    """Get latest sea surface current grid."""
    try:
        success, message, rows = marine_service.get_currents()
        data = [
            {'lat': r['lat'], 'lon': r['lon'], 'uo': r.get('uo'), 'vo': r.get('vo'),
             'speed': r.get('speed'), 'direction_deg': r.get('direction_deg')}
            for r in rows
        ]
        return jsonify({'status': 'success' if success else 'error',
                        'message': message, 'data': data,
                        'source': rows[0].get('src') if rows else None}), (200 if success else 404)
    except Exception as e:
        logger.error(f"Error getting marine currents: {e}", module='API', exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/marine/currents/collect', methods=['POST'])
def collect_marine_currents():
    """Collect (CMEMS or mock) and persist the current grid."""
    try:
        success, message = marine_collector.collect_currents_and_save()
        return jsonify({'status': 'success' if success else 'error', 'message': message}), (200 if success else 400)
    except Exception as e:
        logger.error(f"Error collecting marine currents: {e}", module='API', exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/marine/ssh', methods=['GET'])
def get_marine_ssh():
    """Get latest sea surface height grid."""
    try:
        success, message, rows = marine_service.get_ssh()
        data = [{'lat': r['lat'], 'lon': r['lon'], 'zos': r.get('zos')} for r in rows]
        return jsonify({'status': 'success' if success else 'error',
                        'message': message, 'data': data,
                        'source': rows[0].get('src') if rows else None}), (200 if success else 404)
    except Exception as e:
        logger.error(f"Error getting marine SSH: {e}", module='API', exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/marine/ssh/collect', methods=['POST'])
def collect_marine_ssh():
    """Collect (CMEMS or mock) and persist the SSH grid."""
    try:
        success, message = marine_collector.collect_ssh_and_save()
        return jsonify({'status': 'success' if success else 'error', 'message': message}), (200 if success else 400)
    except Exception as e:
        logger.error(f"Error collecting marine SSH: {e}", module='API', exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/marine/risk', methods=['GET'])
def get_marine_risk():
    """Get latest vessel-capsize risk zones."""
    try:
        success, message, rows = marine_service.get_vessel_risk()
        return jsonify({'status': 'success' if success else 'error',
                        'message': message, 'data': rows}), (200 if success else 404)
    except Exception as e:
        logger.error(f"Error getting marine risk: {e}", module='API', exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/marine/risk/collect', methods=['POST'])
def collect_marine_risk():
    """Collect currents+SSH, derive vessel risk, persist."""
    try:
        coastal_data = {}
        for loc in coastal_service.get_all_locations():
            row = coastal_service.get_coastal(loc, use_cache=True)
            if row:
                coastal_data[loc] = row
        success, message = marine_collector.collect_risk_and_save(coastal_data)
        return jsonify({'status': 'success' if success else 'error', 'message': message}), (200 if success else 400)
    except Exception as e:
        logger.error(f"Error collecting marine risk: {e}", module='API', exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/marine/risk/evaluate', methods=['POST'])
def evaluate_marine_risk():
    """Ollama narrative for the hottest risk zone (async job)."""
    try:
        success, message, rows = marine_service.get_vessel_risk()
        if not success or not rows:
            return jsonify({'status': 'error',
                            'message': 'No vessel risk data. Run POST /api/marine/risk/collect first'}), 404

        def _run():
            ok, result = marine_evaluator.evaluate(rows)
            if not ok:
                raise RuntimeError('Marine evaluation failed')
            return result

        job_id = submit_job(_run)
        return jsonify({'status': 'running', 'job_id': job_id,
                        'message': 'Marine evaluation started'}), 202
    except Exception as e:
        logger.error(f"Error evaluating marine risk: {e}", module='API', exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/marine/waves/deepsea', methods=['GET'])
def get_marine_deepsea_waves():
    """Deep-sea wave cross-check from Open-Meteo Marine (free, no key)."""
    try:
        success, message, rows = marine_openmeteo.get_saved_waves()
        src = 'open-meteo'
        if not success:
            success, message, rows = marine_openmeteo.get_deep_sea_waves()
        valid = [pt for pt in rows if pt.get('wave_height') is not None]
        return jsonify({'status': 'success' if success and valid else 'error',
                        'message': message, 'data': rows, 'source': src}), (200 if success else 502)
    except Exception as e:
        logger.error(f"Error getting deep-sea waves: {e}", module='API', exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/marine/waves/deepsea/collect', methods=['POST'])
def collect_marine_deepsea_waves():
    """Fetch + persist a fresh Open-Meteo deep-sea wave snapshot."""
    try:
        success, message, _ = marine_openmeteo.collect_and_save()
        return jsonify({'status': 'success' if success else 'error', 'message': message}), (200 if success else 400)
    except Exception as e:
        logger.error(f"Error collecting deep-sea waves: {e}", module='API', exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/marine/zones', methods=['GET'])
def get_marine_zones():
    """Return Libya coastal zones + transit area metadata."""
    try:
        from evaluation_service.modules.marine.collector import ZONES
        return jsonify({'status': 'success', 'data': ZONES}), 200
    except Exception as e:
        logger.error(f"Error getting marine zones: {e}", module='API', exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ---------------------------------------------------------------- forecast
@app.route('/forecast', methods=['GET'])
def forecast_page():
    """Windy-style forecast & historical weather page."""
    return render_template('forecast.html')


@app.route('/api/forecast/cities', methods=['GET'])
def get_forecast_cities():
    """List of tracked cities for the picker."""
    return jsonify({'status': 'success', 'data': forecast_openmeteo.CITIES}), 200


@app.route('/api/forecast/<city>', methods=['GET'])
def get_forecast_city(city):
    """Latest full forecast (current + hourly + daily) for a city."""
    try:
        success, message, payload = forecast_openmeteo.get_city_forecast(city)
        if not success:
            return jsonify({'status': 'error', 'message': message}), 502
        return jsonify({'status': 'success', 'message': message,
                        'data': {'payload': payload['payload'], 'how': payload['how'],
                                 'asof': payload.get('asof'), 'city': city}}), 200
    except Exception as e:
        logger.error(f"Error getting forecast for {city}: {e}", module='API', exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/forecast/<city>/collect', methods=['POST'])
def collect_forecast_city(city):
    """Force a fresh Open-Meteo forecast collection for a city."""
    try:
        success, message, _ = forecast_openmeteo.collect_city(city)
        return jsonify({'status': 'success' if success else 'error', 'message': message}), (200 if success else 400)
    except Exception as e:
        logger.error(f"Error collecting forecast for {city}: {e}", module='API', exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/forecast/<city>/history', methods=['GET'])
def get_forecast_history(city):
    """ERA5 historical daily series for a city."""
    try:
        start = request.args.get('from', (datetime.now(timezone.utc) - timedelta(days=30)).strftime('%Y-%m-%d'))
        end = request.args.get('to', datetime.now(timezone.utc).strftime('%Y-%m-%d'))
        success, message, rows = forecast_openmeteo.get_history(city, start, end)
        return jsonify({'status': 'success' if success else 'error',
                        'message': message, 'data': rows}), (200 if success else 400)
    except Exception as e:
        logger.error(f"Error getting history for {city}: {e}", module='API', exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/forecast/<city>/climate', methods=['GET'])
def get_forecast_climate(city):
    """Monthly normals, all-time records and coverage for a city."""
    try:
        success, message, clim = forecast_openmeteo.get_climate(city)
        return jsonify({'status': 'success' if success else 'error',
                        'message': message, 'data': clim}), (200 if success else 400)
    except Exception as e:
        logger.error(f"Error getting climate for {city}: {e}", module='API', exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/forecast/<city>/anomaly', methods=['GET'])
def get_forecast_anomaly(city):
    """Monthly temperature/precip anomaly for a year (default: current)."""
    try:
        year = request.args.get('year', datetime.now(timezone.utc).year, type=int)
        success, message, data = forecast_openmeteo.get_anomaly(city, year)
        return jsonify({'status': 'success' if success else 'error',
                        'message': message, 'data': data}), (200 if success else 400)
    except Exception as e:
        logger.error(f"Error getting anomaly for {city}: {e}", module='API', exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/forecast/grid', methods=['GET'])
def get_forecast_grid():
    """Gridded playback layer. ?var=temperature|precipitation|wind&hour=ISO &all=1"""
    try:
        var = request.args.get('var', 'temperature')
        hour = request.args.get('hour')
        if request.args.get('all') == '1' or not hour:
            success, message, data = forecast_openmeteo.get_grid_all(var)
        else:
            success, message, data = forecast_openmeteo.get_grid_var(var, hour)
        # Normalize response structure to match frontend expectations
        if success and isinstance(data, dict):
            return jsonify({'status': 'success', 'message': message, 'data': data}), 200
        return jsonify({'status': 'success' if success else 'error',
                        'message': message, 'data': data}), (200 if success else 400)
    except Exception as e:
        logger.error(f"Error getting forecast grid: {e}", module='API', exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/forecast/grid/collect', methods=['POST'])
def collect_forecast_grid():
    """Fetch + persist a fresh gridded playback snapshot."""
    try:
        success, message, n = forecast_openmeteo.collect_grid()
        return jsonify({'status': 'success' if success else 'error',
                        'message': message, 'count': n}), (200 if success else 400)
    except Exception as e:
        logger.error(f"Error collecting forecast grid: {e}", module='API', exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500

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


_KB_GENERIC_WORDS = {
    'libya', 'libyan', 'data', 'dataset', 'datasets', 'information', 'info',
    'numbers', 'number', 'total', 'details', 'report', 'reports', 'source',
    'sources', 'statistics', 'overview', 'summary', 'latest', 'current',
    'confirmed', 'cases', 'case', 'about', 'people', 'person', 'affected',
    'situation', 'conditions', '2024', '2025', '2026', 'last', 'years', 'year',
}


def _websearch_fallback_response(message: str, retrieval_info: dict,
                                 chat_repo=None, session_id=None,
                                 categories: Optional[list] = None):
    """Live humanitarian web search fallback (HDX + web + Wikipedia + news).
    Used when the KB has no strong match: answers from citable humanitarian
    sources instead of dumping irrelevant entries."""
    try:
        from evaluation_service.modules.chatbot.websearch import ChatbotWebSearch
        searcher = ChatbotWebSearch()
        results = searcher.search(message, categories=categories, max_results=7)
        if results:
            body = ("I couldn't find a direct match in the knowledge base, "
                    "so I checked reliable humanitarian and web sources:\n\n")
            body += searcher.format_results(results, max_items=5)
            body += ("\n\nThese are the most relevant sources. I recommend "
                     "opening the links for the exact figures and latest data.")
            model_used = "websearch (HDX + web sources)"
            routing_info = {
                'route': 'lrc_helper',
                'reasoning': 'No strong KB match → live web search (HDX/web/news)',
                'retrieval': retrieval_info
            }
            return body, model_used, routing_info
    except Exception as e:
        logger.warning(f"Websearch fallback failed: {e}", module='CHATBOT')

    response_text = ("I don't have this information in my knowledge base, and a live search of "
                     "reliable humanitarian and web sources did not return a good match. "
                     "Please try a more specific question about displacement, "
                     "food security and prices, conflict events, humanitarian funding, "
                     "health, education, or infrastructure in Libya.")
    model_used = "no reliable match (KB + web search)"
    routing_info = {
        'route': 'lrc_helper',
        'reasoning': 'LLM unavailable, no KB match, no web match'
    }
    return response_text, model_used, routing_info

def _kb_fallback_response(message: str, kb_repo, retrieval_info: dict,
                          chat_repo=None, session_id=None, recent_user_msgs=None):
    """KB-aware fallback when LLM is unavailable.
    Searches the knowledge base directly and returns matching entries ONLY if
    there is strong evidence (topic category + title keyword evidence).
    Otherwise falls back to a live humanitarian web search (HDX) instead of
    dumping loosely-matched entries.
    """
    import re

    # Use conversation context: if current message is a short follow-up,
    # merge prior user messages so the topic (e.g. food prices) stays in scope.
    context_msgs = []
    if recent_user_msgs:
        context_msgs = list(recent_user_msgs)
    elif chat_repo is not None and session_id:
        try:
            prior = chat_repo.get_session_messages(session_id, limit=20)
            context_msgs = [m['content'] for m in prior[::-1]
                            if m['message_type'] == 'user' and m['content'] != message][:3][::-1]
        except Exception:
            context_msgs = []

    stopwords = {'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had',
                 'was', 'one', 'our', 'has', 'how', 'tell', 'what', 'about', 'does',
                 'there', 'this', 'that', 'with', 'from', 'have', 'some', 'do', 'me',
                 'would', 'could', 'should', 'will', 'any', 'just', 'your', 'its',
                 'been', 'they', 'them', 'their', 'these', 'those', 'were', 'said',
                 'whats', 'lets', 'let', 'check', 'see', 'look', 'want',
                 'available', 'avilable', 'we', 'ok', 'okay', 'yeah', 'yes', 'thee'}

    # City/region lexicon for location-aware ranking
    locations = ['tripoli', 'benghazi', 'misrata', 'misurata', 'derna', 'ejdabia',
                 'al bayda', 'albaida', 'albayda', 'sabha', 'sebha', 'zawiya', 'zawia',
                 'zuwara', 'zwara', 'sirte', 'surt', 'gharyan', 'gharian', 'mizda',
                 'murzuq', 'ubari', 'kufra', 'elfeel', 'sabratha', 'al zintan', 'tarhuna',
                 'bani walid', 'gergaresh', 'janzour', 'janzur', 'abu salim', 'abusliem',
                 'souq aljumaa', 'suq aljumaa', 'east', 'west', 'south', 'north',
                 'darnah', 'gadames', 'ghat', 'nofilia', 'ras lanuf', 'brega', 'ajdabiya',
                 'misurata', 'az zintan', 'djebel', 'aljabal', 'jabal', 'alzawiya']

    found_locs = [loc for loc in locations if loc in message.lower()]

    # Topic keywords → categories
    topic_keywords = {
        'food_security': ['food', 'price', 'prices', 'market', 'wheat', 'nutrition', 'hunger', 'commodity'],
        'displacement': ['idp', 'displaced', 'refugee', 'refugees', 'migration', 'displacement', 'unhcr'],
        'conflict_security': ['conflict', 'fatali', 'violence', 'attack', 'bomb', 'security', 'war', 'militia', 'military'],
        'funding': ['funding', 'appeal', 'budget', 'cerf', 'aid', 'aids'],
        'population': ['population', 'how many people', 'demographic'],
        'operational_presence': ['organization', 'ngo', 'agency', 'who is doing'],
        'climate_data': ['rain', 'climate', 'drought', 'flood', 'storm'],
        'health': ['health', 'hospital', 'medical', 'clinic', 'tb', 'covid', 'disease', 'diseases', 'infection', 'doctor'],
        'education': ['education', 'school', 'student', 'university'],
        'infrastructure': ['road', 'transport', 'port', 'bridge', 'airport', 'power', 'electric', 'dams'],
        'humanitarian_needs': ['need', 'humanitarian', 'assessment'],
        'lrc_organization': ['lrc', 'red crescent', 'mission'],
        'contact_information': ['contact', 'phone', 'address', 'hotline'],
    }

    analysis_text_full = message
    if context_msgs:
        analysis_text_full = " ".join(context_msgs) + " " + message

    # Detect relevant categories from the merged text
    msg_lower = analysis_text_full.lower()
    relevant_cats = []
    for cat, kws in topic_keywords.items():
        if any(k in msg_lower for k in kws):
            relevant_cats.append(cat)

    # Strong signal keywords: non-generic words from the current message
    strong_kws = set()
    for w in re.findall(r"[a-zA-Z]{3,}", message.lower()):
        if w not in stopwords and w not in [l.replace(' ', '') for l in locations] \
                and w not in _KB_GENERIC_WORDS:
            strong_kws.add(w)
    if not strong_kws:
        strong_kws = set(message.lower().split())

    def _kw_hits(kw, title_l, content_l):
        """Stem-aware keyword match: exact, prefix, or contained word."""
        if kw in title_l or kw in content_l:
            return True
        for word in title_l.split() + content_l.split()[:400]:
            word = word.strip('.,;:()[]{}\"\'!?')
            if len(word) >= 3:
                if kw in word or word.startswith(kw) or kw.startswith(word):
                    return True
        return False

    final_entries = []

    # STRICT selection: require topic category AND evidence in the title,
    # otherwise the entry is too generic to claim as a relevant source.
    if relevant_cats:
        cat_entries = []
        for cat in relevant_cats:
            cat_entries.extend(kb_repo.get_entries_by_category(cat))

        scored_cat = []
        for e in cat_entries:
            score = 0
            title_l = (e.get('title') or '').lower()
            content_l = (e.get('content') or '').lower()
            title_evidence = any(_kw_hits(kw, title_l, '') for kw in strong_kws)
            title_loc = any(loc in title_l for loc in found_locs)
            if not title_evidence and not title_loc:
                continue
            score += 4 if title_evidence else 1
            for loc in found_locs:
                if loc in title_l:
                    score += 6
                elif loc in content_l:
                    score += 3
            for kw in strong_kws:
                if _kw_hits(kw, title_l, content_l):
                    score += 2
            scored_cat.append((score, e))

        scored_cat.sort(key=lambda x: -x[0])
        for score, e in scored_cat[:5]:
            final_entries.append(e)

    # If only a location provided (no topic matched), require title location hit
    if not final_entries and found_locs and not strong_kws:
        for loc in found_locs:
            for e in kb_repo.search_entries(loc, limit=5):
                if e.get('category') != 'hdx_datasets' or e.get('title', '').lower().count(loc) > 1:
                    final_entries.append(e)
        final_entries = list({e['id']: e for e in final_entries}.values())[:5]

    if final_entries:
        parts = []
        n = len(final_entries)
        
        # Extract actual data first, then provide sources
        for e in final_entries[:3]:
            content = e.get('content', '')
            if content and len(content) > 50:
                # Check if content has actual numbers/data
                import re
                if re.search(r'\d+[,\d]*', content):
                    parts.append(content)
                    break
        
        # If no data found, use the entry with highest priority
        if not parts:
            for e in final_entries[:3]:
                content = e.get('content', '')
                if content and len(content) > 50:
                    parts.append(content)
                    break
        
        # Then provide sources as references
        parts.append(f"\n\nSource information:")
        for e in final_entries[:5]:
            source = e.get('source', 'N/A')
            title = e.get('title', 'N/A')
            parts.append(f"- {title} ({source})")
        
        response_text = "\n".join(parts)
        model_used = "knowledge_base (no LLM)"
        routing_info = {
            'route': 'lrc_helper',
            'reasoning': 'KB direct lookup (LLM unavailable)',
            'retrieval': retrieval_info
        }
    else:
        # No strong KB evidence: search reliable humanitarian + web sources
        web_response, web_model, web_routing = _websearch_fallback_response(
            message, retrieval_info, chat_repo=chat_repo, session_id=session_id,
            categories=relevant_cats
        )
        return web_response, web_model, web_routing

    return response_text, model_used, routing_info


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

@app.route('/api/knowledge-base/collect-hdx', methods=['POST'])
def collect_hdx_data():
    """Trigger HDX data collection from HAPI and CKAN"""
    try:
        from evaluation_service.repositories.knowledge_base import KnowledgeBaseRepository
        from evaluation_service.modules.hdx.collector import HDXCollector

        kb_repo = KnowledgeBaseRepository()
        collector = HDXCollector()

        result = collector.collect_and_save(kb_repo)

        return jsonify({
            'success': True,
            'result': result
        }), 200

    except Exception as e:
        logger.error(f"HDX collection error: {e}", module='API', exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/knowledge-base/hdx-status', methods=['GET'])
def hdx_status():
    """Get HDX data collection status and knowledge base statistics"""
    try:
        from evaluation_service.repositories.knowledge_base import KnowledgeBaseRepository
        from evaluation_service.modules.hdx.collector import HDXCollector

        kb_repo = KnowledgeBaseRepository()
        collector = HDXCollector()

        status = collector.get_status(kb_repo)

        return jsonify({
            'success': True,
            'status': status
        }), 200

    except Exception as e:
        logger.error(f"HDX status error: {e}", module='API', exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/knowledge-base/stats', methods=['GET'])
def knowledge_base_stats():
    """Get overall knowledge base statistics"""
    try:
        from evaluation_service.repositories.knowledge_base import KnowledgeBaseRepository

        kb_repo = KnowledgeBaseRepository()
        categories = kb_repo.get_entries_count_by_category()
        total = sum(s.get('count', 0) for s in categories.values())

        all_categories = kb_repo.get_all_categories()

        return jsonify({
            'success': True,
            'total_entries': total,
            'categories': categories,
            'all_categories': all_categories
        }), 200

    except Exception as e:
        logger.error(f"KB stats error: {e}", module='API', exc_info=True)
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
                        "model": "gemma4:31b-cloud",  # Free cloud model
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
                    model_used = "gemma4:31b-cloud"
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
                        "model": "gemma4:31b-cloud",  # Free cloud model
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
                    model_used = "gemma4:31b-cloud"
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

                # Topic-aware knowledge retrieval
                kb_repo = KnowledgeBaseRepository()

                # Pull recent user messages for conversation context (follow-ups
                # like "let check ejdabia" depend on the prior topic)
                recent_user_msgs = []
                if session_id:
                    try:
                        import re as _re
                        prior_msgs = chat_repo.get_session_messages(session_id, limit=20)
                        # include current message implicitly; collect previous user turns
                        prev = [m['content'] for m in prior_msgs
                                if m['message_type'] == 'user' and m['content'] != message]
                        recent_user_msgs = prev[-4:]
                    except Exception:
                        pass

                # Map user query keywords to KB categories
                def detect_categories(message_text: str):
                    msg = message_text.lower()
                    # Merge recent user turns so short follow-ups inherit the topic
                    full_msg = msg
                    if recent_user_msgs:
                        full_msg = (" ".join(recent_user_msgs) + " " + msg)
                    topic_map = {
                        'displacement': ['displacement', 'idp', 'displaced', 'refugee', 'refugees', 'migration', 'displaced person', 'sudanese', 'asylum', 'unhcr'],
                        'humanitarian_needs': ['need', 'humanitarian need', 'population in need', 'assessment', 'un aid', 'un arms'],
                        'conflict_security': ['conflict', 'violence', 'attack', 'fatalit', 'bomb', 'terror', 'war', 'clash', 'militia', 'civilian targeting', 'military'],
                        'operational_presence': ['organization', 'ngo', 'who is doing', 'operational presence', 'agency', 'red cross'],
                        'funding': ['funding', 'appeal', 'money', 'budget', 'financial', 'cerf', 'aid', 'assistance', 'donation', 'grants'],
                        'food_security': ['food', 'hunger', 'nutrition', 'famine', 'price', 'prices', 'market', 'wheat', 'commodity', 'foodstuff', 'food stuff'],
                        'population': ['population', 'demographic', 'people in libya', 'how many people'],
                        'climate_data': ['rain', 'climate', 'drought', 'flood', 'weather', 'precipitation', 'storm'],
                        'health': ['health', 'hospital', 'medical', 'disease', 'clinic', 'doctor', 'medicine'],
                        'education': ['education', 'school', 'university', 'student'],
                        'infrastructure': ['road', 'transport', 'port', 'bridge', 'infrastructure', 'airport', 'power', 'electricity'],
                        'geodata': ['boundary', 'administrative', 'map', 'border', 'coordinate'],
                        'contact_information': ['contact', 'phone', 'address', 'hotline', 'reach', 'office'],
                        'first_aid': ['first aid', 'cpr', 'medical assistance', 'emergency help'],
                        'disaster_management': ['disaster', 'emergency', 'risk', 'hazard', 'preparedness', 'dams'],
                        'partners': ['partner', 'ifrc', 'icrc', 'united nations', 'unhcr', 'unicef', 'wfp', 'who', 'iom', 'eu', 'red cross'],
                        'lrc_organization': ['lrc', 'red crescent', 'organization', 'libyan red', 'mission'],
                    }

                    selected = []
                    for cat, keywords in topic_map.items():
                        if any(kw in full_msg for kw in keywords):
                            selected.append(cat)

                    # Always include core LRC context
                    core = ['lrc_organization', 'emergency_response', 'humanitarian_principles', 'contact_information']
                    # Query-relevant categories FIRST so the small model attends to answer data
                    return list(dict.fromkeys(selected + core))

                categories = detect_categories(message)

                # Get knowledge context: relevant categories + top priority entries
                knowledge_context = kb_repo.get_knowledge_context(
                    categories=categories,
                    max_entries=30
                )
                if len(knowledge_context.strip()) < 200:
                    # Fallback to top priority entries if category match was empty
                    knowledge_context = kb_repo.get_knowledge_context(max_entries=30)

                retrieval_info = {
                    'categories_used': categories,
                    'context_len': len(knowledge_context)
                }

                # Build prompt with knowledge base
                _conv_block = ""
                if recent_user_msgs:
                    _conv_block = "\nCONVERSATION CONTEXT (previous user questions in this session):\n" + \
                        "\n".join(f"- {u}" for u in recent_user_msgs) + \
                        "\nThe user's current question above may be a follow-up on these. Use them to understand context, but answer the current question."
                system_prompt = f"""You are the LRC (Libyan Red Crescent) Emergency Intelligence Assistant. You provide humanitarian information, operational guidance, and support for emergency response.

KNOWLEDGE BASE:
{knowledge_context}
{_conv_block}
RESPONSE GUIDELINES:
- ANSWER WITH ACTUAL NUMBERS AND DATA FIRST, then provide sources
- Extract specific numbers, statistics, and figures from the knowledge base entries
- Present the real answer clearly at the beginning of your response
- If the user asks for numbers (like "how many refugees"), provide the exact figure from the data
- Use the knowledge base entries as your source of truth - the content contains the actual data
- Answer ONLY using information from the knowledge base (LRC, IFRC, ICRC, UN sources)
- If information is not available in the knowledge base, state that clearly
- Prioritize humanitarian principles and safety
- Provide operational information when relevant
- Include contact information and addresses when available
- Be professional, accurate, and helpful
- When data is from HDX, cite the organization (IOM, WFP, OCHA, ACLED, etc.) and mention the data is from HDX
- Include specific numbers and statistics from the knowledge base when answering data questions

RESPONSE FORMAT:
- Start with the direct answer containing actual numbers/data
- Cite sources when possible (e.g., "According to LRC..." or "According to HDX data...")
- Include relevant contact information or addresses
- If unsure, recommend contacting LRC directly

You support LRC volunteers, staff, and the public with humanitarian information and operational guidance."""

                # Resolve models: prefer working cloud models → local models
                available_models = get_available_models(OLLAMA_URL)
                preferred = [m for m in [
                    os.environ.get('OLLAMA_MODEL', ''),
                    'gemma4:31b-cloud',
                    'gpt-oss:20b-cloud',
                    'nemotron-3-super:cloud',
                    'lfm2.5-thinking:latest',
                    'lrc-assistant:latest',
                    'kimi-k2.6:cloud',
                    'minimax-m3:cloud',
                ] if m]
                model_order = []
                for m in preferred:
                    if m not in model_order:
                        model_order.append(m)
                for m in available_models:
                    if m not in model_order:
                        model_order.append(m)
                # Only try models that actually exist on the server
                model_order = [m for m in model_order if m in available_models]
                # Cap attempts so users aren't stuck minutes while big models fail
                model_order = model_order[:3]

                # Try each model until one succeeds
                response_text = ""
                model_used = ""
                for model in model_order:
                    try:
                        ollama_response = requests.post(
                            f'{OLLAMA_URL}/api/generate',
                            json={
                                "model": model,
                                "prompt": message,
                                "stream": False,
                                "system": system_prompt
                            },
                            timeout=45
                        )
                        if ollama_response.status_code == 200:
                            result = ollama_response.json()
                            response_text = result.get('response', 'No response generated.')
                            model_used = model
                            routing_info = {
                                'route': 'lrc_helper',
                                'reasoning': 'Knowledge-based LRC assistance',
                                'retrieval': retrieval_info
                            }
                            break
                    except Exception as e:
                        logger.warning(f"Model {model} failed: {e}", module='CHATBOT')

                # Verify: small models sometimes claim "no data" even when the KB has it.
                # If the LLM says data unavailable but KB has matching entries, override with direct KB data.
                if response_text and response_text.strip():
                    _no_data_phrases = [
                        'does not contain', 'do not contain', 'not contain',
                        'not available', 'not directly available', 'not explicitly stated',
                        'no data', 'no information', 'not present',
                        'no specific data', 'no specific information', 'no specific figure',
                        'does not include', 'does not have', 'do not have',
                        'could not find', 'cannot find', 'no definitive',
                    ]
                    lower_resp = response_text.lower()
                    if any(p in lower_resp for p in _no_data_phrases):
                        fb_text, fb_model, fb_routing = _kb_fallback_response(
                            message, kb_repo, retrieval_info,
                            chat_repo=chat_repo, session_id=session_id
                        )
                        if len(fb_text) > 100:
                            response_text = fb_text
                            model_used += f' + {fb_model}'
                            routing_info = fb_routing
                            routing_info['reasoning'] += ' | LLM claimed no data → KB/web data'

                if not response_text:
                    # KB-aware fallback: search knowledge base directly for answers
                    response_text, model_used, routing_info = _kb_fallback_response(
                        message, kb_repo, retrieval_info,
                        chat_repo=chat_repo, session_id=session_id
                    )
            
            except Exception as e:
                # KB-aware fallback on any error
                try:
                    from evaluation_service.repositories.knowledge_base import KnowledgeBaseRepository
                    kb_repo_fb = KnowledgeBaseRepository()
                    response_text, model_used, routing_info = _kb_fallback_response(
                        message, kb_repo_fb, {'categories_used': [], 'context_len': 0},
                        chat_repo=chat_repo, session_id=session_id
                    )
                except Exception:
                    response_text = (
                        "I can help with humanitarian information about Libya. "
                        "The AI model is temporarily unavailable — please try again in a moment."
                    )
                    model_used = "unavailable"
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

        # Marine: sea currents + SSH hourly, vessel risk every 30 min
        scheduler.add_job('marine_currents',
                          marine_collector.collect_currents_and_save,
                          interval_minutes=60, at_time=f'00:{offset:02d}')
        offset += 2
        scheduler.add_job('marine_ssh',
                          marine_collector.collect_ssh_and_save,
                          interval_minutes=60, at_time=f'00:{offset:02d}')
        offset += 2
        scheduler.add_job('marine_risk',
                          marine_collector.collect_risk_and_save,
                          interval_minutes=30)
        offset += 2
        scheduler.add_job('marine_deepsea_waves',
                          marine_openmeteo.collect_and_save,
                          interval_minutes=60, at_time=f'00:{offset:02d}')

        # Forecast: each tracked city + the gridded playback layer, hourly.
        # City collects are a single request each; no top-of-hour burst needed.
        for fc_city in forecast_openmeteo.CITIES:
            scheduler.add_job(f'forecast_{fc_city["name"]}',
                              lambda n=fc_city["name"]: forecast_openmeteo.collect_city(n),
                              interval_minutes=60)
        scheduler.add_job('forecast_grid',
                          forecast_openmeteo.collect_grid,
                          interval_minutes=60)

        # HDX: daily humanitarian data collection from HDX at 6 AM
        def collect_hdx_daily():
            try:
                from evaluation_service.repositories.knowledge_base import KnowledgeBaseRepository
                from evaluation_service.modules.hdx.collector import HDXCollector
                kb_repo = KnowledgeBaseRepository()
                collector = HDXCollector()
                collector.collect_and_save(kb_repo)
                logger.info("Daily HDX collection completed", module='SCHEDULER')
            except Exception as e:
                logger.error(f"Daily HDX collection failed: {e}", module='SCHEDULER')

        scheduler.add_daily_job('hdx_daily', collect_hdx_daily, at_time="06:00")

        scheduler.start()
        logger.info(f"Scheduler started with {len(scheduler.get_jobs())} jobs", module='MAIN')
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}", module='MAIN', exc_info=True)


if __name__ == '__main__':
    logger.info(f"Starting Evaluation Service on port {EVALUATION_PORT}", module='MAIN')
    start_scheduler()
    app.run(host='0.0.0.0', port=EVALUATION_PORT, debug=True, use_reloader=False, threaded=True)
