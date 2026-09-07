"""
Danger repository for database operations
"""
import os
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from evaluation_service.repositories.base_repository import BaseRepository
from evaluation_service.core.logger import get_logger

logger = get_logger()

class DangerRepository(BaseRepository):
    """Repository for danger prediction operations"""
    
    def __init__(self):
        db_path = os.path.join(os.path.dirname(__file__), '..', '..', 'database', 'danger.db')
        super().__init__(db_path)
        self._init_tables()
    
    def _init_tables(self):
        """Initialize danger prediction tables"""
        query = """
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT NOT NULL,
            risk_score REAL,
            risk_level TEXT,
            confidence REAL,
            component_scores TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        self.execute_update(query)
        
        query = """
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT,
            event_happened INTEGER,
            severity INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )
        """
        self.execute_update(query)
        
        # Create indexes
        self.execute_update("CREATE INDEX IF NOT EXISTS idx_danger_city ON predictions(city)")
        self.execute_update("CREATE INDEX IF NOT EXISTS idx_danger_timestamp ON predictions(timestamp)")
        logger.info("Danger database initialized", module='DANGER_REPOSITORY')
    
    def save_prediction(self, data: Dict) -> int:
        """Save prediction to database"""
        import json
        query = """
        INSERT INTO predictions (city, risk_score, risk_level, confidence, component_scores)
        VALUES (?, ?, ?, ?, ?)
        """
        params = (
            data.get('city'),
            data.get('risk_score'),
            data.get('risk_level'),
            data.get('confidence'),
            json.dumps(data.get('component_scores')) if data.get('component_scores') else None
        )
        return self.execute_insert(query, params)
    
    def get_latest_prediction(self, city: str) -> Optional[Dict]:
        """Get latest prediction for a city"""
        query = """
        SELECT * FROM predictions 
        WHERE city = ? 
        ORDER BY timestamp DESC 
        LIMIT 1
        """
        results = self.execute_query(query, (city,))
        return results[0] if results else None
    
    def get_prediction_history(self, city: str, hours: int = 24) -> List[Dict]:
        """Get prediction history for a city"""
        since = datetime.utcnow() - timedelta(hours=hours)
        query = """
        SELECT * FROM predictions 
        WHERE city = ? AND timestamp >= ?
        ORDER BY timestamp DESC
        """
        results = self.execute_query(query, (city, since.isoformat()))
        return results
    
    def save_feedback(self, data: Dict) -> int:
        """Save feedback to database"""
        query = """
        INSERT INTO feedback (city, event_happened, severity, notes)
        VALUES (?, ?, ?, ?)
        """
        params = (
            data.get('city'),
            data.get('event_happened'),
            data.get('severity'),
            data.get('notes')
        )
        return self.execute_insert(query, params)
    
    def get_all_cities(self) -> List[str]:
        """Get all cities with predictions"""
        query = "SELECT DISTINCT city FROM predictions ORDER BY city"
        results = self.execute_query(query)
        return [row['city'] for row in results]
    
    def get_active_alerts(self, threshold: float = 0.7) -> List[Dict]:
        """Get active alerts (predictions above threshold)"""
        since = datetime.utcnow() - timedelta(hours=1)
        query = """
        SELECT * FROM predictions 
        WHERE risk_score >= ? AND timestamp >= ?
        ORDER BY risk_score DESC
        """
        results = self.execute_query(query, (threshold, since.isoformat()))
        return results
