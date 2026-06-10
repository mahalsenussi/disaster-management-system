"""
OSRM Service for Route Generation
Adapted from v1 route_test/modules/osrm_client.py
"""

import requests
import json
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class OSRMService:
    """Service for OSRM routing API"""
    
    def __init__(self, base_url: str = None, profile: str = 'driving', timeout: int = 30):
        """
        Initialize OSRM service
        
        Args:
            base_url: OSRM server URL
            profile: Routing profile (driving, walking, cycling)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url or 'http://router.project-osrm.org'
        self.profile = profile
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Disaster-Management-System/2.0',
            'Content-Type': 'application/json'
        })
        
        # Libya bounds for validation
        self.libya_bounds = {
            'min_lat': 19.5,
            'max_lat': 33.5,
            'min_lng': 9.5,
            'max_lng': 25.0
        }
    
    def get_route_osrm(self, start: Tuple[float, float], 
                       end: Tuple[float, float],
                       alternatives: bool = False) -> Dict[str, Any]:
        """
        Calculate route between two points using OSRM
        
        Args:
            start: Starting coordinates (lat, lng)
            end: Ending coordinates (lat, lng)
            alternatives: Whether to return alternative routes
            
        Returns:
            {
                "path": [[lat, lng], ...],
                "distance": number (km),
                "duration": number (seconds)
            }
        """
        try:
            coordinates = [start, end]
            
            # Format coordinates for OSRM (lng,lat format)
            coord_string = ';'.join([f"{lng},{lat}" for lat, lng in coordinates])
            
            # Build URL
            url = f"{self.base_url}/route/v1/{self.profile}/{coord_string}"
            
            params = {
                'alternatives': str(alternatives).lower(),
                'steps': 'false',
                'overview': 'full',
                'geometries': 'geojson'
            }
            
            logger.info(f"Calculating OSRM route from {start} to {end}")
            
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            
            # Validate response
            if data.get('code') != 'Ok':
                raise Exception(f"OSRM error: {data.get('message', 'Unknown error')}")
                
            if not data.get('routes'):
                raise Exception("No routes found")
            
            # Parse response to standard format
            return self.parse_osrm_response(data)
            
        except requests.exceptions.Timeout:
            logger.error("OSRM request timeout")
            raise Exception("Routing request timed out")
        except requests.exceptions.RequestException as e:
            logger.error(f"OSRM request error: {e}")
            raise Exception(f"Failed to connect to routing service: {e}")
        except Exception as e:
            logger.error(f"Route calculation error: {e}")
            raise
    
    def get_route_with_waypoints(self, points: List[Tuple[float, float]]) -> Dict[str, Any]:
        """
        Calculate route through multiple waypoints
        
        Args:
            points: List of (lat, lng) tuples to visit in order
            
        Returns:
            {
                "path": [[lat, lng], ...],
                "distance": number (km),
                "duration": number (seconds)
            }
        """
        try:
            if len(points) < 2:
                raise ValueError("At least 2 points required")
            
            # Format coordinates for OSRM
            coord_string = ';'.join([f"{lng},{lat}" for lat, lng in points])
            
            url = f"{self.base_url}/route/v1/{self.profile}/{coord_string}"
            
            params = {
                'alternatives': 'false',
                'steps': 'false',
                'overview': 'full',
                'geometries': 'geojson'
            }
            
            logger.info(f"Calculating OSRM route through {len(points)} waypoints")
            
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('code') != 'Ok':
                raise Exception(f"OSRM error: {data.get('message', 'Unknown error')}")
                
            if not data.get('routes'):
                raise Exception("No routes found")
            
            return self.parse_osrm_response(data)
            
        except Exception as e:
            logger.error(f"Waypoint route error: {e}")
            raise
    
    def parse_osrm_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse OSRM response to standard format
        
        Args:
            data: Raw OSRM response
            
        Returns:
            {
                "path": [[lat, lng], ...],
                "distance": number (km),
                "duration": number (seconds)
            }
        """
        try:
            if not data.get('routes'):
                return {}
            
            main_route = data['routes'][0]
            
            # Extract geometry (GeoJSON format)
            geometry = main_route.get('geometry')
            path = []
            
            if geometry and geometry.get('type') == 'LineString':
                # GeoJSON coordinates are [lng, lat], convert to [lat, lng]
                path = [[coord[1], coord[0]] for coord in geometry.get('coordinates', [])]
            
            # Distance in meters, convert to km
            distance_m = main_route.get('distance', 0)
            distance_km = distance_m / 1000
            
            # Duration in seconds
            duration = main_route.get('duration', 0)
            
            return {
                'path': path,
                'distance': distance_km,
                'duration': duration,
                'distance_m': distance_m,
                'source': 'osrm',
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"OSRM response parsing error: {e}")
            raise
    
    def validate_coordinates(self, coordinates: List[Tuple[float, float]]) -> bool:
        """
        Validate that coordinates are within Libya bounds
        
        Args:
            coordinates: List of (lat, lng) tuples
            
        Returns:
            True if valid, False otherwise
        """
        try:
            for lat, lng in coordinates:
                if not (self.libya_bounds['min_lat'] <= lat <= self.libya_bounds['max_lat']):
                    return False
                if not (self.libya_bounds['min_lng'] <= lng <= self.libya_bounds['max_lng']):
                    return False
            return True
        except Exception:
            return False
    
    def health_check(self) -> bool:
        """
        Check if OSRM service is available
        
        Returns:
            True if service is healthy, False otherwise
        """
        try:
            # Simple health check with a short route
            test_coords = [(32.8872, 13.1913), (32.9000, 13.2000)]
            coord_string = ';'.join([f"{lng},{lat}" for lat, lng in test_coords])
            url = f"{self.base_url}/route/v1/{self.profile}/{coord_string}"
            
            response = self.session.get(url, params={'overview': 'false'}, timeout=5)
            return response.status_code == 200
        except Exception:
            return False
