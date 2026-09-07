"""
Historical repository for database operations
"""
import os
from typing import List, Dict, Optional
from evaluation_service.repositories.base_repository import BaseRepository
from evaluation_service.core.logger import get_logger

logger = get_logger()

class HistoricalRepository(BaseRepository):
    """Repository for historical disaster data operations"""
    
    def __init__(self):
        db_path = os.path.join(os.path.dirname(__file__), '..', '..', 'database', 'historical.db')
        super().__init__(db_path)
        self._init_tables()
    
    def _init_tables(self):
        """Initialize historical disaster data table"""
        query = """
        CREATE TABLE IF NOT EXISTS disasters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            disaster_type TEXT,
            country TEXT,
            location TEXT,
            date TEXT,
            deaths INTEGER,
            affected INTEGER,
            damage_usd REAL,
            description TEXT,
            lat REAL,
            lng REAL
        )
        """
        self.execute_update(query)
        
        # Check if lat/lng columns exist, add if not (for existing databases)
        try:
            columns = self.execute_query("PRAGMA table_info(disasters)")
            column_names = [col['name'] for col in columns]
            
            if 'lat' not in column_names:
                self.execute_update("ALTER TABLE disasters ADD COLUMN lat REAL")
            if 'lng' not in column_names:
                self.execute_update("ALTER TABLE disasters ADD COLUMN lng REAL")
        except Exception as e:
            logger.warning(f"Error checking/adding columns: {e}", module='HISTORICAL_REPOSITORY')
        
        # Create indexes
        self.execute_update("CREATE INDEX IF NOT EXISTS idx_historical_country ON disasters(country)")
        self.execute_update("CREATE INDEX IF NOT EXISTS idx_historical_type ON disasters(disaster_type)")
        self.execute_update("CREATE INDEX IF NOT EXISTS idx_historical_date ON disasters(date)")
        logger.info("Historical database initialized", module='HISTORICAL_REPOSITORY')
    
    def save_disaster(self, data: Dict) -> int:
        """Save disaster data to database"""
        query = """
        INSERT INTO disasters (disaster_type, country, location, date, deaths, affected, damage_usd, description, lat, lng)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            data.get('disaster_type'),
            data.get('country'),
            data.get('location'),
            data.get('date'),
            data.get('deaths'),
            data.get('affected'),
            data.get('damage_usd'),
            data.get('description'),
            data.get('lat'),
            data.get('lng')
        )
        return self.execute_insert(query, params)
    
    def get_disasters_by_country(self, country: str) -> List[Dict]:
        """Get disasters by country"""
        query = """
        SELECT * FROM disasters 
        WHERE country = ? 
        ORDER BY date DESC
        """
        results = self.execute_query(query, (country,))
        return results
    
    def get_disasters_by_type(self, disaster_type: str) -> List[Dict]:
        """Get disasters by type"""
        query = """
        SELECT * FROM disasters 
        WHERE disaster_type = ? 
        ORDER BY date DESC
        """
        results = self.execute_query(query, (disaster_type,))
        return results
    
    def get_all_disasters(self, limit: int = 100) -> List[Dict]:
        """Get all disasters"""
        query = f"SELECT * FROM disasters ORDER BY date DESC LIMIT {limit}"
        results = self.execute_query(query)
        return results
    
    def get_disaster_patterns(self, country: str = None) -> Dict:
        """Get disaster patterns statistics"""
        if country:
            query = """
            SELECT disaster_type, COUNT(*) as count, AVG(deaths) as avg_deaths
            FROM disasters 
            WHERE country = ?
            GROUP BY disaster_type
            """
            results = self.execute_query(query, (country,))
        else:
            query = """
            SELECT disaster_type, COUNT(*) as count, AVG(deaths) as avg_deaths
            FROM disasters 
            GROUP BY disaster_type
            """
            results = self.execute_query(query)
        
        patterns = {}
        for row in results:
            patterns[row['disaster_type']] = {
                'count': row['count'],
                'avg_deaths': row['avg_deaths']
            }
        
        return patterns
    
    def get_all_countries(self) -> List[str]:
        """Get all countries with disaster data"""
        query = "SELECT DISTINCT country FROM disasters ORDER BY country"
        results = self.execute_query(query)
        return [row['country'] for row in results]
