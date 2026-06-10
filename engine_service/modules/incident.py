"""
Incident Management Module
Adapted from v1 modules/disaster for incident handling
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class IncidentManager:
    """Manager for incident operations"""
    
    def __init__(self):
        self.incidents = []
    
    def create_incident(self, incident_type: str, severity: str, 
                      lat: float, lng: float, status: str = 'open',
                      description: str = None) -> Dict[str, Any]:
        """
        Create a new incident.
        
        Args:
            incident_type: Type of incident (fire, medical, flood, etc.)
            severity: Severity level (low, medium, high, critical)
            lat: Latitude
            lng: Longitude
            status: Status (open, assigned, closed)
            description: Optional description
        
        Returns:
            Incident data dictionary
        """
        incident = {
            'id': len(self.incidents) + 1,
            'type': incident_type,
            'severity': severity,
            'lat': lat,
            'lng': lng,
            'status': status,
            'description': description,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        self.incidents.append(incident)
        logger.info(f"Created incident: {incident_type} at ({lat}, {lng})")
        
        return incident
    
    def get_incident(self, incident_id: int) -> Optional[Dict[str, Any]]:
        """Get incident by ID."""
        for incident in self.incidents:
            if incident['id'] == incident_id:
                return incident
        return None
    
    def get_all_incidents(self, status: str = None) -> List[Dict[str, Any]]:
        """
        Get all incidents, optionally filtered by status.
        
        Args:
            status: Filter by status (open, assigned, closed)
        
        Returns:
            List of incidents
        """
        if status:
            return [i for i in self.incidents if i['status'] == status]
        return self.incidents
    
    def update_incident(self, incident_id: int, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Update incident fields.
        
        Args:
            incident_id: Incident ID
            **kwargs: Fields to update
        
        Returns:
            Updated incident or None if not found
        """
        incident = self.get_incident(incident_id)
        if not incident:
            return None
        
        for key, value in kwargs.items():
            if key in incident:
                incident[key] = value
        
        incident['updated_at'] = datetime.now().isoformat()
        logger.info(f"Updated incident {incident_id}")
        
        return incident
    
    def get_incidents_by_severity(self, severity: str) -> List[Dict[str, Any]]:
        """Get incidents by severity level."""
        return [i for i in self.incidents if i['severity'] == severity]
    
    def get_incidents_in_radius(self, center_lat: float, center_lng: float, 
                               radius_km: float) -> List[Dict[str, Any]]:
        """
        Get incidents within a radius of a point.
        
        Args:
            center_lat: Center latitude
            center_lng: Center longitude
            radius_km: Radius in kilometers
        
        Returns:
            List of incidents within radius
        """
        from .geo_utils import haversine_distance
        
        nearby = []
        for incident in self.incidents:
            distance = haversine_distance(
                center_lat, center_lng,
                incident['lat'], incident['lng']
            )
            if distance <= radius_km:
                incident['distance'] = distance
                nearby.append(incident)
        
        return sorted(nearby, key=lambda x: x['distance'])
    
    def assign_team(self, incident_id: int, team_id: int) -> Optional[Dict[str, Any]]:
        """
        Assign a team to an incident.
        
        Args:
            incident_id: Incident ID
            team_id: Team ID
        
        Returns:
            Updated incident or None if not found
        """
        return self.update_incident(incident_id, status='assigned', assigned_team_id=team_id)
    
    def close_incident(self, incident_id: int) -> Optional[Dict[str, Any]]:
        """
        Close an incident.
        
        Args:
            incident_id: Incident ID
        
        Returns:
            Updated incident or None if not found
        """
        return self.update_incident(incident_id, status='closed', closed_at=datetime.now().isoformat())
