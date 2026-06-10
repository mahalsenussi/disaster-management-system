#!/usr/bin/env python3
"""
Engine Service for Route Generation
Ubuntu server microservice for heavy processing
Integrates OSRM routing with fallback to straight-line calculation
"""

from flask import Flask, request, jsonify
from datetime import datetime
import os
import logging
import sys

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import configuration
from config import get_config

# Import modules
from modules.routing import RouteManager
from modules.geo_utils import haversine_distance, calculate_eta

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Load configuration
config = get_config()

# Initialize route manager with OSRM integration
route_manager = RouteManager(
    osrm_url=config.OSRM_URL,
    osrm_timeout=config.OSRM_TIMEOUT,
    fallback_enabled=config.FALLBACK_ENABLED,
    fallback_speed=config.FALLBACK_SPEED_KMH
)

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'service': 'route-engine',
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/route', methods=['POST'])
def generate_route():
    """
    Generate a route between team and incident.
    Uses OSRM with fallback to straight-line calculation.
    
    Input:
    {
        "team": { "lat": ..., "lng": ... },
        "incident": { "lat": ..., "lng": ... }
    }
    
    Output:
    {
        "path": [[lat, lng], [lat, lng]],
        "distance": number (km),
        "duration": number (seconds),
        "source": "osrm" or "fallback"
    }
    """
    try:
        data = request.get_json()
        
        team = data.get('team', {})
        incident = data.get('incident', {})
        
        team_lat = team.get('lat')
        team_lng = team.get('lng')
        incident_lat = incident.get('lat')
        incident_lng = incident.get('lng')
        
        # Validate input
        if None in [team_lat, team_lng, incident_lat, incident_lng]:
            return jsonify({
                'error': 'Missing coordinates. Required: team.lat, team.lng, incident.lat, incident.lng'
            }), 400
        
        # Calculate route using RouteManager (OSRM with fallback)
        route_data = route_manager.calculate_route(
            start=(team_lat, team_lng),
            end=(incident_lat, incident_lng),
            use_osrm=True
        )
        
        # Add ETA in minutes for compatibility
        route_data['eta'] = route_data['duration'] / 60
        
        return jsonify(route_data)
        
    except Exception as e:
        logger.error(f"Route generation error: {e}")
        return jsonify({
            'error': f'Internal server error: {str(e)}'
        }), 500

@app.route('/route/batch', methods=['POST'])
def generate_routes_batch():
    """
    Generate multiple routes in batch.
    
    Input:
    {
        "routes": [
            {"team": {"lat": ..., "lng": ...}, "incident": {"lat": ..., "lng": ...}},
            ...
        ]
    }
    
    Output:
    {
        "routes": [
            {"path": [...], "distance": ..., "duration": ..., "source": ...},
            ...
        ]
    }
    """
    try:
        data = request.get_json()
        routes_data = data.get('routes', [])
        
        results = []
        
        for route_request in routes_data:
            team = route_request.get('team', {})
            incident = route_request.get('incident', {})
            
            team_lat = team.get('lat')
            team_lng = team.get('lng')
            incident_lat = incident.get('lat')
            incident_lng = incident.get('lng')
            
            if None in [team_lat, team_lng, incident_lat, incident_lng]:
                results.append({
                    'error': 'Missing coordinates'
                })
                continue
            
            try:
                route_data = route_manager.calculate_route(
                    start=(team_lat, team_lng),
                    end=(incident_lat, incident_lng),
                    use_osrm=True
                )
                route_data['eta'] = route_data['duration'] / 60
                results.append(route_data)
            except Exception as e:
                logger.error(f"Batch route error: {e}")
                results.append({
                    'error': str(e)
                })
        
        return jsonify({
            'routes': results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Batch route generation error: {e}")
        return jsonify({
            'error': f'Internal server error: {str(e)}'
        }), 500

@app.route('/route/optimize', methods=['POST'])
def optimize_route():
    """
    Find the nearest team to an incident.
    
    Input:
    {
        "incident": { "lat": ..., "lng": ... },
        "teams": [
            {"id": 1, "lat": ..., "lng": ...},
            ...
        ]
    }
    
    Output:
    {
        "nearest_team": {...},
        "distance": ...,
        "eta": ...
    }
    """
    try:
        data = request.get_json()
        
        incident = data.get('incident', {})
        teams = data.get('teams', [])
        
        incident_lat = incident.get('lat')
        incident_lng = incident.get('lng')
        
        if None in [incident_lat, incident_lng]:
            return jsonify({
                'error': 'Missing incident coordinates'
            }), 400
        
        if not teams:
            return jsonify({
                'error': 'No teams provided'
            }), 400
        
        # Use RouteManager to find nearest team
        nearest = route_manager.find_nearest_team(
            incident_location=(incident_lat, incident_lng),
            teams=teams
        )
        
        if nearest is None:
            return jsonify({
                'error': 'No valid teams found'
            }), 400
        
        return jsonify({
            'nearest_team': nearest,
            'distance': nearest['distance'],
            'eta': nearest['eta'],
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Route optimization error: {e}")
        return jsonify({
            'error': f'Internal server error: {str(e)}'
        }), 500

if __name__ == '__main__':
    logger.info(f"Starting Engine Service on port 5001")
    logger.info(f"OSRM URL: {config.OSRM_URL}")
    logger.info(f"Fallback enabled: {config.FALLBACK_ENABLED}")
    logger.info(f"OSRM available: {route_manager.osrm_available}")
    
    app.run(host='0.0.0.0', port=5001, debug=config.DEBUG)
