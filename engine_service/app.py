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
import math

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

def check_route_blocked(route_path, road_blocks):
    """
    Check if a route path intersects any road blocks.
    Checks both discrete points and line segments between points.
    
    Args:
        route_path: List of [lat, lng] coordinates
        road_blocks: List of {lat, lng, radius, status} objects
        
    Returns:
        True if route intersects any closed/restricted block, False otherwise
    """
    if not route_path or not road_blocks:
        return False
    
    logger.info(f"Checking route with {len(route_path)} points against {len(road_blocks)} blocks")
    
    # Check discrete points
    for i, point in enumerate(route_path):
        route_lat = point[0]
        route_lng = point[1]
        
        for block in road_blocks:
            block_lat = block.get('lat')
            block_lng = block.get('lng')
            block_radius_m = block.get('radius', 200)
            
            # Calculate distance using Haversine formula (returns km)
            distance_km = haversine_distance(route_lat, route_lng, block_lat, block_lng)
            distance_m = distance_km * 1000  # Convert to meters
            
            # If route point is within block radius, route is blocked
            if distance_m <= block_radius_m:
                logger.info(f"BLOCKED: Route point {route_lat:.4f},{route_lng:.4f} is {distance_m:.0f}m from block at {block_lat:.4f},{block_lng:.4f} (radius: {block_radius_m}m)")
                return True
    
    # Check line segments between points (sample intermediate points)
    for i in range(len(route_path) - 1):
        p1 = route_path[i]
        p2 = route_path[i + 1]
        
        # Sample 5 points along each segment
        for t in [0.2, 0.4, 0.6, 0.8]:
            sample_lat = p1[0] + (p2[0] - p1[0]) * t
            sample_lng = p1[1] + (p2[1] - p1[1]) * t
            
            for block in road_blocks:
                block_lat = block.get('lat')
                block_lng = block.get('lng')
                block_radius_m = block.get('radius', 200)
                
                distance_km = haversine_distance(sample_lat, sample_lng, block_lat, block_lng)
                distance_m = distance_km * 1000
                
                if distance_m <= block_radius_m:
                    logger.info(f"BLOCKED: Route segment point {sample_lat:.4f},{sample_lng:.4f} is {distance_m:.0f}m from block at {block_lat:.4f},{block_lng:.4f} (radius: {block_radius_m}m)")
                    return True
    
    logger.info(f"Route NOT blocked - checked {len(route_path)} points and segments against {len(road_blocks)} blocks")
    return False

def generate_detour_waypoint(start, end, block):
    """
    Generate a waypoint to route around a blocked area.
    Tries multiple directions to find a good detour.
    
    Args:
        start: (lat, lng) starting point
        end: (lat, lng) ending point
        block: {lat, lng, radius} block to avoid
        
    Returns:
        (lat, lng) waypoint that routes around the block
    """
    block_lat = block.get('lat')
    block_lng = block.get('lng')
    block_radius = block.get('radius', 200)
    
    # Calculate direction from start to end
    dx = end[1] - start[1]  # lng difference
    dy = end[0] - start[0]  # lat difference
    
    # Normalize direction
    length = math.sqrt(dx**2 + dy**2)
    if length == 0:
        length = 1
    dx /= length
    dy /= length
    
    # Perpendicular vector (rotate 90 degrees)
    perp_dx = -dy
    perp_dy = dx
    
    # Calculate detour distance (block radius + buffer in degrees)
    detour_distance = (block_radius + 1000) / 111000  # Convert meters to degrees (approx)
    
    # Try both sides of the block
    candidates = [
        (block_lat + perp_dy * detour_distance, block_lng + perp_dx * detour_distance),
        (block_lat - perp_dy * detour_distance, block_lng - perp_dx * detour_distance)
    ]
    
    # Return the first candidate (could be improved to choose the better one)
    return candidates[0]

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
    Supports road block avoidance by checking alternatives.
    
    Input:
    {
        "team": { "lat": ..., "lng": ... },
        "incident": { "lat": ..., "lng": ... },
        "road_blocks": [  // Optional
            { "lat": ..., "lng": ..., "radius": ..., "status": "closed|restricted" }
        ]
    }
    
    Output:
    {
        "path": [[lat, lng], [lat, lng]],
        "distance": number (km),
        "duration": number (seconds),
        "source": "osrm" or "fallback",
        "blocked": boolean  // True if route intersects blocked area
    }
    """
    try:
        data = request.get_json()
        
        team = data.get('team', {})
        incident = data.get('incident', {})
        road_blocks = data.get('road_blocks', [])
        
        team_lat = team.get('lat')
        team_lng = team.get('lng')
        incident_lat = incident.get('lat')
        incident_lng = incident.get('lng')
        manual_mode = data.get('manual_mode', False)
        manual_waypoints = data.get('waypoints', [])
        
        # Validate input
        if None in [team_lat, team_lng, incident_lat, incident_lng]:
            return jsonify({
                'error': 'Missing coordinates. Required: team.lat, team.lng, incident.lat, incident.lng'
            }), 400
        
        logger.info(f"Route request: team ({team_lat}, {team_lng}) -> incident ({incident_lat}, {incident_lng})")
        logger.info(f"Manual mode: {manual_mode}")
        
        # Handle manual mode
        if manual_mode:
            logger.info(f"Manual mode with {len(manual_waypoints)} waypoints")
            
            if not manual_waypoints or len(manual_waypoints) < 1:
                return jsonify({
                    'error': 'waypoints required for manual mode'
                }), 400
            
            # Build waypoint sequence: start -> manual waypoints -> end
            waypoints = [(team_lat, team_lng)]
            for wp in manual_waypoints:
                waypoints.append((wp['lat'], wp['lng']))
            waypoints.append((incident_lat, incident_lng))
            
            logger.info(f"Calculating manual route through {len(waypoints)} waypoints")
            route_data = route_manager.calculate_route_with_waypoints(
                points=waypoints,
                use_osrm=True
            )
            
            # Get active road blocks for validation
            active_blocks = [b for b in road_blocks if b.get('status') in ['closed', 'restricted']]
            logger.info(f"Validating against {len(active_blocks)} active road blocks")
            
            # STRICT validation: reject if route crosses ANY block
            is_blocked = check_route_blocked(route_data.get('path', []), active_blocks)
            
            if is_blocked:
                logger.warning("Manual route intersects blocked road - REJECTING")
                return jsonify({
                    'status': 'invalid',
                    'message': 'Manual route intersects blocked road'
                }), 400
            
            logger.info("Manual route validated - no block intersections")
            route_data['eta'] = route_data['duration'] / 60
            route_data['blocked'] = False
            route_data['source'] = 'manual'
            return jsonify(route_data)
        
        # Automatic mode (existing logic)
        logger.info(f"Received {len(road_blocks)} road blocks")
        
        # Filter to only closed/restricted blocks
        active_blocks = [b for b in road_blocks if b.get('status') in ['closed', 'restricted']]
        logger.info(f"Active (closed/restricted) blocks: {len(active_blocks)}")
        
        if not active_blocks:
            # No blocks, simple route calculation
            logger.info("No active blocks, using standard route calculation")
            route_data = route_manager.calculate_route(
                start=(team_lat, team_lng),
                end=(incident_lat, incident_lng),
                use_osrm=True
            )
            route_data['eta'] = route_data['duration'] / 60
            route_data['blocked'] = False
            return jsonify(route_data)
        
        # Proactive approach: Add detour waypoints for all blocks to force routing around them
        logger.info("Using proactive detour approach with waypoints")
        
        # Sort blocks by distance from start to process in order
        def distance_from_start(block):
            return haversine_distance(team_lat, team_lng, block['lat'], block['lng'])
        
        sorted_blocks = sorted(active_blocks, key=distance_from_start)
        
        # Build waypoints: start -> detour points for each block -> end
        waypoints = [(team_lat, team_lng)]
        
        for block in sorted_blocks:
            detour_point = generate_detour_waypoint(
                (team_lat, team_lng),
                (incident_lat, incident_lng),
                block
            )
            waypoints.append(detour_point)
            logger.info(f"Added detour waypoint at {detour_point[0]:.4f},{detour_point[1]:.4f} for block at {block['lat']:.4f},{block['lng']:.4f}")
        
        waypoints.append((incident_lat, incident_lng))
        
        # Calculate route with waypoints
        logger.info(f"Calculating route through {len(waypoints)} waypoints")
        route_data = route_manager.calculate_route_with_waypoints(
            points=waypoints,
            use_osrm=True
        )
        
        # Check if the detoured route is still blocked (shouldn't be, but verify)
        is_blocked = check_route_blocked(route_data.get('path', []), active_blocks)
        
        route_data['eta'] = route_data['duration'] / 60
        route_data['blocked'] = is_blocked
        route_data['waypoints_used'] = len(waypoints)
        
        if is_blocked:
            logger.warning("Detoured route still intersects blocks - returning anyway as best effort")
        else:
            logger.info("Detoured route successfully avoids all blocks")
        
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
    logger.info(f"Starting Engine Service on port {config.PORT}")
    logger.info(f"OSRM URL: {config.OSRM_URL}")
    logger.info(f"Fallback enabled: {config.FALLBACK_ENABLED}")
    logger.info(f"OSRM available: {route_manager.osrm_available}")
    
    app.run(host='0.0.0.0', port=config.PORT, debug=config.DEBUG)
