"""
Weather data collector from OpenWeatherMap
"""
import os
import requests
from typing import Dict, Optional
from evaluation_service.core.logger import get_logger
from evaluation_service.modules.weather.service import WeatherService

logger = get_logger()

class WeatherCollector:
    """Collects weather data from OpenWeatherMap API"""
    
    def __init__(self):
        self.service = WeatherService()
        self.api_key = os.environ.get('OPENWEATHER_API_KEY')
        self.base_url = "https://api.openweathermap.org/data/2.5/weather"
        
        if not self.api_key:
            logger.warning("OpenWeatherMap API key not set", module='WEATHER_COLLECTOR')
    
    def collect_weather(self, city: str) -> tuple[bool, str, Optional[Dict]]:
        """Collect weather data for a city
        
        Returns:
            (success, message, weather_data)
        """
        if not self.api_key:
            # Use mock data for testing if no API key
            logger.warning("Using mock data for weather collection", module='WEATHER_COLLECTOR')
            return self._get_mock_data(city)
        
        # City name mapping for OpenWeatherMap API
        city_mapping = {
            'Misrata': 'Misratah',
            'Sebha': 'Sabha',
            'Bayda': 'Al Bayda'
        }
        
        # Use mapped name if available
        query_city = city_mapping.get(city, city)
        
        try:
            params = {
                'q': query_city,
                'appid': self.api_key,
                'units': 'metric'
            }
            
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract relevant data
            weather_data = {
                'city': city,  # Use original city name for consistency
                'temperature': data['main']['temp'],
                'humidity': data['main']['humidity'],
                'pressure': data['main']['pressure'],
                'wind_speed': data.get('wind', {}).get('speed', 0)
            }
            
            logger.collector_run('weather', f"Collected for {city} (queried as {query_city})", f"Temp: {weather_data['temperature']}°C")
            
            return True, "Weather data collected successfully", weather_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to collect weather for {city} (queried as {query_city}): {e}", module='WEATHER_COLLECTOR')
            # Fallback to mock data on API failure
            logger.warning("API failed, using mock data", module='WEATHER_COLLECTOR')
            return self._get_mock_data(city)
        except KeyError as e:
            logger.error(f"Invalid API response for {city}: {e}", module='WEATHER_COLLECTOR')
            return False, f"Invalid API response: {str(e)}", None
        except Exception as e:
            logger.error(f"Unexpected error collecting weather for {city}: {e}", module='WEATHER_COLLECTOR', exc_info=True)
            return False, f"Unexpected error: {str(e)}", None
    
    def _get_mock_data(self, city: str) -> tuple[bool, str, Dict]:
        """Generate mock weather data for testing"""
        import random
        
        weather_data = {
            'city': city,
            'temperature': round(random.uniform(20, 35), 1),
            'humidity': round(random.uniform(30, 80), 0),
            'pressure': round(random.uniform(1000, 1020), 0),
            'wind_speed': round(random.uniform(2, 15), 1)
        }
        
        logger.collector_run('weather', f"Collected mock data for {city}", f"Temp: {weather_data['temperature']}°C")
        
        return True, "Weather data collected successfully (mock)", weather_data
    
    def collect_and_save(self, city: str) -> tuple[bool, str]:
        """Collect and save weather data"""
        success, message, weather_data = self.collect_weather(city)
        
        if not success:
            return success, message
        
        # Save to database
        success, message, weather_id = self.service.save_weather(weather_data)
        
        if success:
            logger.info(f"Collected and saved weather for {city}", module='WEATHER_COLLECTOR')
        else:
            logger.error(f"Failed to save weather for {city}: {message}", module='WEATHER_COLLECTOR')
        
        return success, message
    
    def collect_multiple_cities(self, cities: list) -> Dict:
        """Collect weather data for multiple cities"""
        results = {}
        
        for city in cities:
            success, message, _ = self.collect_and_save(city)
            results[city] = {
                'success': success,
                'message': message
            }
        
        return results
