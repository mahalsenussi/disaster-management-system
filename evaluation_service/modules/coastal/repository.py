"""
Coastal repository for database operations
"""
import os
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from evaluation_service.repositories.base_repository import BaseRepository
from evaluation_service.core.logger import get_logger

logger = get_logger()

class CoastalRepository(BaseRepository):
    """Repository for coastal data operations"""
    
    def __init__(self):
        db_path = os.path.join(os.path.dirname(__file__), '..', '..', 'database', 'coastal.db')
        super().__init__(db_path)
        self._init_tables()
    
    def _init_tables(self):
        """Initialize coastal data table"""
        query = """
        CREATE TABLE IF NOT EXISTS coastal_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            location TEXT NOT NULL,
            wave_height REAL,
            wave_period REAL,
            sea_level_anomaly REAL,
            wind_speed REAL,
            collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            evaluated_at TIMESTAMP,
            risk_score REAL,
            ollama_evaluation TEXT
        )
        """
        self.execute_update(query)
        
        # Add columns if they don't exist (migration for existing databases)
        try:
            self.execute_update("ALTER TABLE coastal_data ADD COLUMN evaluated_at TIMESTAMP")
        except:
            pass  # Column already exists
        
        try:
            self.execute_update("ALTER TABLE coastal_data ADD COLUMN risk_score REAL")
        except:
            pass  # Column already exists
        
        try:
            self.execute_update("ALTER TABLE coastal_data ADD COLUMN ollama_evaluation TEXT")
        except:
            pass  # Column already exists
        
        # Create indexes
        self.execute_update("CREATE INDEX IF NOT EXISTS idx_coastal_location ON coastal_data(location)")
        self.execute_update("CREATE INDEX IF NOT EXISTS idx_coastal_collected_at ON coastal_data(collected_at)")
        
        # Only create evaluated_at index if column exists
        try:
            self.execute_update("CREATE INDEX IF NOT EXISTS idx_coastal_evaluated_at ON coastal_data(evaluated_at)")
        except:
            pass  # Column might not exist yet
        
        logger.info("Coastal database initialized", module='COASTAL_REPOSITORY')
    
    def save_coastal_data(self, data: Dict) -> int:
        """Save coastal data to database"""
        query = """
        INSERT INTO coastal_data (location, wave_height, wave_period, sea_level_anomaly, wind_speed, risk_score, ollama_evaluation, evaluated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            data.get('location'),
            data.get('wave_height'),
            data.get('wave_period'),
            data.get('sea_level_anomaly'),
            data.get('wind_speed'),
            data.get('risk_score'),
            data.get('ollama_evaluation'),
            data.get('evaluated_at')
        )
        return self.execute_insert(query, params)
    
    def get_latest_coastal(self, location: str) -> Optional[Dict]:
        """Get latest coastal data for a location"""
        query = """
        SELECT * FROM coastal_data 
        WHERE location = ? 
        ORDER BY collected_at DESC 
        LIMIT 1
        """
        results = self.execute_query(query, (location,))
        return results[0] if results else None
    
    def get_coastal_history(self, location: str, hours: int = 24) -> List[Dict]:
        """Get coastal history for a location"""
        since = datetime.utcnow() - timedelta(hours=hours)
        query = """
        SELECT * FROM coastal_data 
        WHERE location = ? AND collected_at >= ?
        ORDER BY collected_at DESC
        """
        results = self.execute_query(query, (location, since.isoformat()))
        return results
    
    def get_all_locations(self) -> List[str]:
        """Get all locations with coastal data"""
        query = "SELECT DISTINCT location FROM coastal_data ORDER BY location"
        results = self.execute_query(query)
        return [row['location'] for row in results]
    
    def update_risk_score(self, coastal_id: int, risk_score: float, ollama_evaluation: str):
        """Update risk score and evaluation for coastal data"""
        query = """
        UPDATE coastal_data 
        SET risk_score = ?, ollama_evaluation = ?, evaluated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """
        self.execute_update(query, (risk_score, ollama_evaluation, coastal_id))
    
    def is_data_fresh(self, location: str, max_age_hours: int = 1) -> bool:
        """Check if coastal data for a location is fresh (less than max_age_hours old)"""
        latest = self.get_latest_coastal(location)
        if not latest:
            return False
        
        collected_at = latest.get('collected_at')
        if not collected_at:
            return False
        
        try:
            collected_time = datetime.fromisoformat(collected_at)
            age = datetime.utcnow() - collected_time
            return age.total_seconds() < (max_age_hours * 3600)
        except:
            return False
    
    def is_evaluation_fresh(self, location: str, max_age_hours: int = 1) -> bool:
        """Check if evaluation for a location is fresh (less than max_age_hours old)"""
        latest = self.get_latest_coastal(location)
        if not latest:
            return False
        
        evaluated_at = latest.get('evaluated_at')
        if not evaluated_at:
            return False
        
        try:
            evaluated_time = datetime.fromisoformat(evaluated_at)
            age = datetime.utcnow() - evaluated_time
            return age.total_seconds() < (max_age_hours * 3600)
        except:
            return False
