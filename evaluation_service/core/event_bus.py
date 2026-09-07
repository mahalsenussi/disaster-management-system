"""
Event system for decoupled communication between modules
Future feature for real-time reactions
"""
from typing import Callable, Dict, List
import threading
from datetime import datetime

class EventBus:
    """Simple event bus for decoupled communication"""
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()
    
    def subscribe(self, event_type: str, callback: Callable):
        """Subscribe to an event type"""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(callback)
    
    def unsubscribe(self, event_type: str, callback: Callable):
        """Unsubscribe from an event type"""
        with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(callback)
                except ValueError:
                    pass
    
    def publish(self, event_type: str, data: dict = None):
        """Publish an event to all subscribers"""
        with self._lock:
            callbacks = self._subscribers.get(event_type, []).copy()
        
        event = {
            'type': event_type,
            'data': data or {},
            'timestamp': datetime.utcnow().isoformat()
        }
        
        for callback in callbacks:
            try:
                callback(event)
            except Exception as e:
                print(f"Error in event callback: {e}")
    
    def get_subscribers(self, event_type: str) -> int:
        """Get number of subscribers for an event type"""
        with self._lock:
            return len(self._subscribers.get(event_type, []))

# Global event bus instance
_event_bus = None

def get_event_bus():
    """Get global event bus instance"""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus

# Event types
EVENT_WEATHER_UPDATED = 'weather_updated'
EVENT_COASTAL_UPDATED = 'coastal_updated'
EVENT_NEWS_UPDATED = 'news_updated'
EVENT_DANGER_PREDICTION = 'danger_prediction'
EVENT_ALERT_TRIGGERED = 'alert_triggered'
