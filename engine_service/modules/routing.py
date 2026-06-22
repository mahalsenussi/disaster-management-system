"""
Routing Module
Main route manager using OSRM service with fallback
"""

from typing import List, Dict, Any, Tuple, Optional
import logging
from datetime import datetime
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.osrm_service import OSRMService
from modules.geo_utils import haversine_distance, calculate_eta, generate_straight_line_path

logger = logging.getLogger(__name__)

class RouteManager:
    """Manager for routing operations"""
    
    def __init__(self, osrm_url: str = None, osrm_timeout: int = 30, 
                 fallback_enabled: bool = True, fallback_speed: float = 60.0):
        """
        Initialize route manager.
        
        Args:
            osrm_url: OSRM server URL
            osrm_timeout: OSRM request timeout
            fallback_enabled: Enable straight-line fallback
            fallback_speed: Speed for ETA calculation in fallback
        """
        self.osrm_service = OSRMService(base_url=osrm_url, timeout=osrm_timeout)
        self.fallback_enabled = fallback_enabled
        self.fallback_speed = fallback_speed
        self.osrm_available = self._check_osrm_health()
        
        if self.osrm_available:
            logger.info("OSRM service is available")
        else:
            logger.warning("OSRM service not available, using fallback")
    
    def _check_osrm_health(self) -> bool:
        """Check if OSRM service is healthy."""
        try:
            return self.osrm_service.health_check()
        except Exception as e:
            logger.error(f"OSRM health check failed: {e}")
            return False
    
    def calculate_route(self, start: Tuple[float, float], 
                       end: Tuple[float, float],
                       use_osrm: bool = True,
                       alternatives: bool = False) -> Dict[str, Any]:
        """
        Calculate route between two points.
        
        Args:
            start: Starting coordinates (lat, lng)
            end: Ending coordinates (lat, lng)
            use_osrm: Try OSRM first, fallback to straight-line
            alternatives: Request alternative routes from OSRM
        
        Returns:
            {
                "path": [[lat, lng], ...],
                "distance": number (km),
                "duration": number (seconds),
                "source": "osrm" or "fallback"
            }
        """
        # Try OSRM first if enabled and available
        if use_osrm and self.osrm_available:
            try:
                logger.info(f"Calculating OSRM route from {start} to {end} (alternatives={alternatives})")
                route_data = self.osrm_service.get_route_osrm(start, end, alternatives=alternatives)
                route_data['source'] = 'osrm'
                return route_data
            except Exception as e:
                logger.warning(f"OSRM route calculation failed: {e}, using fallback")
        
        # Fallback to straight-line
        if self.fallback_enabled:
            logger.info(f"Using straight-line fallback from {start} to {end}")
            return self._calculate_fallback_route(start, end)
        
        raise Exception("OSRM unavailable and fallback disabled")
    
    def _calculate_fallback_route(self, start: Tuple[float, float], 
                                  end: Tuple[float, float]) -> Dict[str, Any]:
        """
        Calculate straight-line fallback route.
        
        Args:
            start: Starting coordinates
            end: Ending coordinates
        
        Returns:
            Route data with straight-line path
        """
        distance = haversine_distance(start[0], start[1], end[0], end[1])
        duration = calculate_eta(distance, self.fallback_speed) * 60  # Convert to seconds
        path = generate_straight_line_path(start[0], start[1], end[0], end[1])
        
        return {
            'path': path,
            'distance': distance,
            'duration': duration,
            'source': 'fallback',
            'timestamp': datetime.now().isoformat()
        }
    
    def calculate_route_with_waypoints(self, points: List[Tuple[float, float]],
                                      use_osrm: bool = True) -> Dict[str, Any]:
        """
        Calculate route through multiple waypoints.
        
        Args:
            points: List of (lat, lng) tuples
            use_osrm: Try OSRM first
        
        Returns:
            Route data
        """
        if len(points) < 2:
            raise ValueError("At least 2 points required")
        
        if use_osrm and self.osrm_available:
            try:
                logger.info(f"Calculating OSRM route through {len(points)} waypoints")
                route_data = self.osrm_service.get_route_with_waypoints(points)
                route_data['source'] = 'osrm'
                return route_data
            except Exception as e:
                logger.warning(f"OSRM waypoint route failed: {e}, using fallback")
        
        # Fallback: calculate straight-line segments
        if self.fallback_enabled:
            return self._calculate_multi_segment_route(points)
        
        raise Exception("OSRM unavailable and fallback disabled")
    
    def _calculate_multi_segment_route(self, points: List[Tuple[float, float]]) -> Dict[str, Any]:
        """Calculate route through waypoints using straight-line segments."""
        total_distance = 0.0
        total_duration = 0.0
        full_path = []
        
        for i in range(len(points) - 1):
            start = points[i]
            end = points[i + 1]
            
            segment = self._calculate_fallback_route(start, end)
            total_distance += segment['distance']
            total_duration += segment['duration']
            
            # Add path points (avoid duplicating junction points)
            if i == 0:
                full_path.extend(segment['path'])
            else:
                full_path.extend(segment['path'][1:])
        
        return {
            'path': full_path,
            'distance': total_distance,
            'duration': total_duration,
            'source': 'fallback',
            'segments': len(points) - 1,
            'timestamp': datetime.now().isoformat()
        }
    
    def find_nearest_team(self, incident_location: Tuple[float, float],
                         teams: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Find the nearest team to an incident.
        
        Args:
            incident_location: (lat, lng) of incident
            teams: List of team dictionaries with lat, lng
        
        Returns:
            Nearest team with distance or None
        """
        if not teams:
            return None
        
        nearest = None
        min_distance = float('inf')
        
        for team in teams:
            team_lat = team.get('lat')
            team_lng = team.get('lng')
            
            if team_lat is None or team_lng is None:
                continue
            
            distance = haversine_distance(
                incident_location[0], incident_location[1],
                team_lat, team_lng
            )
            
            if distance < min_distance:
                min_distance = distance
                nearest = team
                nearest['distance'] = distance
                nearest['eta'] = calculate_eta(distance, self.fallback_speed)
        
        return nearest
    
    def optimize_route_order(self, start: Tuple[float, float],
                            waypoints: List[Tuple[float, float]],
                            end: Tuple[float, float] = None) -> List[Tuple[float, float]]:
        """
        Optimize the order of waypoints (simplified TSP).
        
        Args:
            start: Starting point
            waypoints: List of waypoints to visit
            end: Optional ending point
        
        Returns:
            Optimized order of points
        """
        if not waypoints:
            return [start] if end else [start]
        
        # Simple nearest-neighbor heuristic
        unvisited = waypoints.copy()
        route = [start]
        current = start
        
        while unvisited:
            nearest = None
            min_dist = float('inf')
            
            for point in unvisited:
                dist = haversine_distance(current[0], current[1], point[0], point[1])
                if dist < min_dist:
                    min_dist = dist
                    nearest = point
            
            if nearest:
                route.append(nearest)
                unvisited.remove(nearest)
                current = nearest
            else:
                break
        
        if end:
            route.append(end)
        
        return route
