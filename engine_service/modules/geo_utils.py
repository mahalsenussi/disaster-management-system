"""
Geo Utilities Module
Provides geographic calculations for routing
"""

import math
from typing import Tuple, List

def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calculate the great circle distance between two points on Earth.
    
    Args:
        lat1, lng1: First point coordinates (decimal degrees)
        lat2, lng2: Second point coordinates (decimal degrees)
    
    Returns:
        Distance in kilometers
    """
    # Convert decimal degrees to radians
    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    # Radius of Earth in kilometers
    r = 6371.0
    
    return c * r

def calculate_eta(distance_km: float, speed_kmh: float = 60.0) -> float:
    """
    Calculate estimated time of arrival in minutes.
    
    Args:
        distance_km: Distance in kilometers
        speed_kmh: Speed in kilometers per hour
    
    Returns:
        ETA in minutes
    """
    if speed_kmh <= 0:
        return float('inf')
    
    time_hours = distance_km / speed_kmh
    time_minutes = time_hours * 60
    return time_minutes

def generate_straight_line_path(lat1: float, lng1: float, lat2: float, lng2: float, num_points: int = 10) -> List[Tuple[float, float]]:
    """
    Generate a straight-line path between two points.
    
    Args:
        lat1, lng1: Starting point coordinates
        lat2, lng2: Ending point coordinates
        num_points: Number of intermediate points to generate
    
    Returns:
        List of (lat, lng) coordinates
    """
    path = []
    
    for i in range(num_points + 1):
        t = i / num_points
        lat = lat1 + (lat2 - lat1) * t
        lng = lng1 + (lng2 - lng1) * t
        path.append((lat, lng))
    
    return path

def bearing(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calculate bearing between two points.
    
    Args:
        lat1, lng1: First point coordinates
        lat2, lng2: Second point coordinates
    
    Returns:
        Bearing in degrees (0-360)
    """
    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    
    dlng = lng2 - lng1
    x = math.sin(dlng) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlng)
    
    bearing = math.atan2(x, y)
    bearing = math.degrees(bearing)
    bearing = (bearing + 360) % 360
    
    return bearing

def midpoint(lat1: float, lng1: float, lat2: float, lng2: float) -> Tuple[float, float]:
    """
    Calculate midpoint between two coordinates.
    
    Args:
        lat1, lng1: First point coordinates
        lat2, lng2: Second point coordinates
    
    Returns:
        (lat, lng) of midpoint
    """
    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    
    dlng = lng2 - lng1
    bx = math.cos(lat2) * math.cos(dlng)
    by = math.cos(lat2) * math.sin(dlng)
    
    lat_m = math.atan2(
        math.sin(lat1) + math.sin(lat2),
        math.sqrt((math.cos(lat1) + bx) ** 2 + by ** 2)
    )
    lng_m = lng1 + math.atan2(by, math.cos(lat1) + bx)
    
    return (math.degrees(lat_m), math.degrees(lng_m))
