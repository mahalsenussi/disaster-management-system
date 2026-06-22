"""
Engine Service Configuration
Adapted from v1 route_test/config.py
"""

import os

class Config:
    """Configuration for Engine Service"""
    
    # Flask Configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'disaster-engine-secret-key-2026'
    DEBUG = False
    PORT = int(os.environ.get('PORT') or os.environ.get('ENGINE_PORT') or '5002')
    
    # OSRM Configuration
    OSRM_URL = os.environ.get('OSRM_URL') or 'http://localhost:5003'
    OSRM_PROFILE = 'driving'  # Options: driving, walking, cycling
    OSRM_TIMEOUT = int(os.environ.get('OSRM_TIMEOUT', '30'))  # seconds
    OSRM_ALTERNATIVES = False  # For disaster response, use primary route
    OSRM_STEPS = False  # Don't need turn-by-turn for dashboard
    OSRM_OVERVIEW = 'full'
    OSRM_GEOMETRIES = 'geojson'
    
    # Fallback Configuration
    FALLBACK_ENABLED = True  # Enable straight-line fallback if OSRM fails
    FALLBACK_SPEED_KMH = 60.0  # Average speed for ETA calculation
    
    # Libya Geographic Configuration
    LIBYA_CENTER_LAT = 26.3351
    LIBYA_CENTER_LNG = 17.2283
    LIBYA_BOUNDS = {
        'min_lat': 19.5,
        'max_lat': 33.5,
        'min_lng': 9.5,
        'max_lng': 25.0
    }
    
    # Routing Limits
    MAX_ROUTE_DISTANCE = 2000  # Maximum distance in km
    MAX_ROUTE_TIME = 24  # Maximum time in hours
    MAX_WAYPOINTS = 25  # Maximum waypoints for optimization
    
    # API Configuration
    API_RATE_LIMIT = '1000/hour'
    
    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = 'engine_service.log'

class DevelopmentConfig(Config):
    DEBUG = True
    LOG_LEVEL = 'DEBUG'

class ProductionConfig(Config):
    DEBUG = False
    LOG_LEVEL = 'WARNING'

# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

def get_config():
    """Get configuration based on environment"""
    env = os.environ.get('FLASK_ENV', 'development')
    return config.get(env, config['default'])
