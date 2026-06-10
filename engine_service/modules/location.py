"""
Location Utilities Module
Adapted from v1 modules/location for geo operations
"""

from typing import List, Dict, Any, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

class LocationUtils:
    """Utilities for location operations"""
    
    def __init__(self):
        self.locations = []
    
    def add_location(self, name: str, lat: float, lng: float, 
                    location_type: str = 'point', metadata: Dict = None) -> Dict[str, Any]:
        """
        Add a location.
        
        Args:
            name: Location name
            lat: Latitude
            lng: Longitude
            location_type: Type (point, area, facility)
            metadata: Additional metadata
        
        Returns:
            Location data
        """
        location = {
            'id': len(self.locations) + 1,
            'name': name,
            'lat': lat,
            'lng': lng,
            'type': location_type,
            'metadata': metadata or {},
            'created_at': None  # Will be set by caller
        }
        
        self.locations.append(location)
        logger.info(f"Added location: {name} at ({lat}, {lng})")
        
        return location
    
    def get_location(self, location_id: int) -> Optional[Dict[str, Any]]:
        """Get location by ID."""
        for location in self.locations:
            if location['id'] == location_id:
                return location
        return None
    
    def get_all_locations(self, location_type: str = None) -> List[Dict[str, Any]]:
        """Get all locations, optionally filtered by type."""
        if location_type:
            return [l for l in self.locations if l['type'] == location_type]
        return self.locations
    
    def find_nearest(self, lat: float, lng: float, 
                    location_type: str = None, limit: int = 1) -> List[Dict[str, Any]]:
        """
        Find nearest locations to a point.
        
        Args:
            lat: Latitude
            lng: Longitude
            location_type: Filter by type
            limit: Maximum number of results
        
        Returns:
            List of nearest locations with distance
        """
        from .geo_utils import haversine_distance
        
        candidates = self.get_all_locations(location_type)
        
        for location in candidates:
            location['distance'] = haversine_distance(
                lat, lng, location['lat'], location['lng']
            )
        
        sorted_locations = sorted(candidates, key=lambda x: x['distance'])
        
        return sorted_locations[:limit]
    
    def get_locations_in_bounds(self, min_lat: float, max_lat: float,
                               min_lng: float, max_lng: float) -> List[Dict[str, Any]]:
        """
        Get locations within geographic bounds.
        
        Args:
            min_lat, max_lat: Latitude bounds
            min_lng, max_lng: Longitude bounds
        
        Returns:
            List of locations within bounds
        """
        return [
            l for l in self.locations
            if min_lat <= l['lat'] <= max_lat and min_lng <= l['lng'] <= max_lng
        ]
    
    def calculate_center(self, locations: List[Dict[str, Any]]) -> Tuple[float, float]:
        """
        Calculate geographic center of multiple locations.
        
        Args:
            locations: List of location dictionaries
        
        Returns:
            (lat, lng) of center
        """
        if not locations:
            return (0.0, 0.0)
        
        avg_lat = sum(l['lat'] for l in locations) / len(locations)
        avg_lng = sum(l['lng'] for l in locations) / len(locations)
        
        return (avg_lat, avg_lng)
