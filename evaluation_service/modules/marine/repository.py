"""
Marine repository for database operations (currents, sea surface height, vessel risk)
"""
import os
from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone
from evaluation_service.repositories.base_repository import BaseRepository
from evaluation_service.core.logger import get_logger

logger = get_logger()

class MarineRepository(BaseRepository):
    """Repository for marine data operations"""

    def __init__(self):
        db_path = os.path.join(os.path.dirname(__file__), '..', '..', 'database', 'marine.db')
        super().__init__(db_path)
        self._init_tables()

    def _init_tables(self):
        """Initialize marine data tables"""
        queries = [
            """
            CREATE TABLE IF NOT EXISTS marine_currents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time TIMESTAMP,
                lat REAL,
                lon REAL,
                uo REAL,
                vo REAL,
                speed REAL,
                direction_deg REAL,
                src TEXT,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS marine_ssh (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time TIMESTAMP,
                lat REAL,
                lon REAL,
                zos REAL,
                src TEXT,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS vessel_risk (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time TIMESTAMP,
                lat REAL,
                lon REAL,
                zone TEXT,
                risk_score REAL,
                danger_level TEXT,
                wave_height REAL,
                wave_period REAL,
                wind_speed REAL,
                current_speed REAL,
                sea_level_anomaly REAL,
                evaluation TEXT,
                evaluated_at TIMESTAMP,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """CREATE INDEX IF NOT EXISTS idx_marine_cur_time ON marine_currents(time)""",
            """CREATE INDEX IF NOT EXISTS idx_marine_ssh_time ON marine_ssh(time)""",
            """CREATE INDEX IF NOT EXISTS idx_vessel_risk_time ON vessel_risk(time)""",
        ]
        for query in queries:
            self.execute_update(query)

        logger.info("Marine database initialized", module='MARINE_REPOSITORY')

    def save_currents(self, rows: list) -> int:
        """Insert a batch of current grid points.

        Args:
            rows: list of dicts with time, lat, lon, uo, vo, speed, direction_deg, src
        """
        if not rows:
            return 0
        query = """
        INSERT INTO marine_currents (time, lat, lon, uo, vo, speed, direction_deg, src)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = [
            (
                r.get('time'), r.get('lat'), r.get('lon'),
                r.get('uo'), r.get('vo'), r.get('speed'),
                r.get('direction_deg'), r.get('src'),
            )
            for r in rows
        ]
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params)
            return cursor.rowcount

    def save_ssh(self, rows: list) -> int:
        """Insert a batch of sea-surface-height grid points."""
        if not rows:
            return 0
        query = """
        INSERT INTO marine_ssh (time, lat, lon, zos, src)
        VALUES (?, ?, ?, ?, ?)
        """
        params = [
            (r.get('time'), r.get('lat'), r.get('lon'), r.get('zos'), r.get('src'))
            for r in rows
        ]
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params)
            return cursor.rowcount

    def save_vessel_risk(self, rows: list) -> int:
        """Insert a batch of vessel-risk zone evaluations."""
        if not rows:
            return 0
        query = """
        INSERT INTO vessel_risk
            (time, lat, lon, zone, risk_score, danger_level, wave_height, wave_period,
             wind_speed, current_speed, sea_level_anomaly, evaluation, evaluated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = [
            (
                r.get('time'), r.get('lat'), r.get('lon'), r.get('zone'),
                r.get('risk_score'), r.get('danger_level'), r.get('wave_height'),
                r.get('wave_period'), r.get('wind_speed'), r.get('current_speed'),
                r.get('sea_level_anomaly'), r.get('evaluation'), r.get('evaluated_at'),
            )
            for r in rows
        ]
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params)
            return cursor.rowcount

    def clear_older_than(self, table: str, days: int = 7):
        """Prune rows older than N days to keep the marine db bounded."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        self.execute_update(f"DELETE FROM {table} WHERE time < ?", (cutoff,))

    def get_latest_time(self, table: str) -> Optional[str]:
        """Return the newest timestamp in a table (column `time`)."""
        results = self.execute_query(f"SELECT MAX(time) AS t FROM {table}")
        return results[0].get('t') if results else None

    def get_latest_grid(self, table: str, max_age_hours: int = 6) -> List[Dict]:
        """Return the most-recent snapshot's grid points if within max_age_hours."""
        latest = self.get_latest_time(table)
        if not latest:
            return []
        try:
            latest_time = datetime.fromisoformat(latest)
            if (datetime.now(timezone.utc) - latest_time).total_seconds() > (max_age_hours * 3600):
                return []
        except Exception:
            return []
        query = f"SELECT * FROM {table} WHERE time = ? ORDER BY lat, lon"
        return self.execute_query(query, (latest,))

    def get_latest_vessel_risk(self, max_age_hours: int = 6) -> List[Dict]:
        """Return most-recent vessel risk rows if within max_age_hours."""
        latest = self.get_latest_time('vessel_risk')
        if not latest:
            return []
        try:
            latest_time = datetime.fromisoformat(latest)
            if (datetime.now(timezone.utc) - latest_time).total_seconds() > (max_age_hours * 3600):
                return []
        except Exception:
            return []
        return self.execute_query(
            "SELECT * FROM vessel_risk WHERE time = ? ORDER BY risk_score DESC", (latest,))