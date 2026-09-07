"""
Weather repository for database operations
"""
import os
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from evaluation_service.repositories.base_repository import BaseRepository
from evaluation_service.core.logger import get_logger

logger = get_logger()

class WeatherRepository(BaseRepository):
    """Repository for weather data operations"""
    
    def __init__(self):
        db_path = os.path.join(os.path.dirname(__file__), '..', '..', 'database', 'weather.db')
        super().__init__(db_path)
        self._init_tables()
    
    def _init_tables(self):
        """Initialize weather data table"""
        query = """
        CREATE TABLE IF NOT EXISTS weather_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT NOT NULL,
            temperature REAL,
            humidity REAL,
            pressure REAL,
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
            self.execute_update("ALTER TABLE weather_data ADD COLUMN evaluated_at TIMESTAMP")
        except:
            pass  # Column already exists
        
        try:
            self.execute_update("ALTER TABLE weather_data ADD COLUMN risk_score REAL")
        except:
            pass  # Column already exists
        
        try:
            self.execute_update("ALTER TABLE weather_data ADD COLUMN ollama_evaluation TEXT")
        except:
            pass  # Column already exists
        
        # Create indexes
        self.execute_update("CREATE INDEX IF NOT EXISTS idx_weather_city ON weather_data(city)")
        self.execute_update("CREATE INDEX IF NOT EXISTS idx_weather_collected_at ON weather_data(collected_at)")
        
        # Only create evaluated_at index if column exists
        try:
            self.execute_update("CREATE INDEX IF NOT EXISTS idx_weather_evaluated_at ON weather_data(evaluated_at)")
        except:
            pass  # Column might not exist yet
        
        logger.info("Weather database initialized", module='WEATHER_REPOSITORY')
    
    def save_weather_data(self, data: Dict) -> int:
        """Save weather data to database"""
        query = """
        INSERT INTO weather_data (city, temperature, humidity, pressure, wind_speed, risk_score, ollama_evaluation, evaluated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            data.get('city'),
            data.get('temperature'),
            data.get('humidity'),
            data.get('pressure'),
            data.get('wind_speed'),
            data.get('risk_score'),
            data.get('ollama_evaluation'),
            data.get('evaluated_at')
        )
        return self.execute_insert(query, params)
    
    def get_latest_weather(self, city: str) -> Optional[Dict]:
        """Get latest weather data for a city"""
        query = """
        SELECT * FROM weather_data 
        WHERE city = ? 
        ORDER BY collected_at DESC 
        LIMIT 1
        """
        results = self.execute_query(query, (city,))
        return results[0] if results else None
    
    def get_weather_history(self, city: str, hours: int = 24) -> List[Dict]:
        """Get weather history for a city"""
        since = datetime.utcnow() - timedelta(hours=hours)
        query = """
        SELECT * FROM weather_data 
        WHERE city = ? AND collected_at >= ?
        ORDER BY collected_at DESC
        """
        results = self.execute_query(query, (city, since.isoformat()))
        return results
    
    def get_all_cities(self) -> List[str]:
        """Get all cities with weather data"""
        query = "SELECT DISTINCT city FROM weather_data ORDER BY city"
        results = self.execute_query(query)
        return [row['city'] for row in results]
    
    def update_risk_score(self, weather_id: int, risk_score: float, ollama_evaluation: str):
        """Update risk score and evaluation for weather data"""
        query = """
        UPDATE weather_data 
        SET risk_score = ?, ollama_evaluation = ?, evaluated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """
        self.execute_update(query, (risk_score, ollama_evaluation, weather_id))
    
    def is_data_fresh(self, city: str, max_age_hours: int = 1) -> bool:
        """Check if weather data for a city is fresh (less than max_age_hours old)"""
        latest = self.get_latest_weather(city)
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
    
    def is_evaluation_fresh(self, city: str, max_age_hours: int = 1) -> bool:
        """Check if evaluation for a city is fresh (less than max_age_hours old)"""
        latest = self.get_latest_weather(city)
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
