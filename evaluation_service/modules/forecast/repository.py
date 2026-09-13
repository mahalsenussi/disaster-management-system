"""
Forecast repository: persists Open-Meteo forecast snapshots, normalized daily
rows, the gridded playback layer, and ERA5 climate dailies for climate analysis.
"""
import os
from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone
from evaluation_service.repositories.base_repository import BaseRepository
from evaluation_service.core.logger import get_logger

logger = get_logger()


class ForecastRepository(BaseRepository):
    """Repository for forecast & historical weather data."""

    def __init__(self):
        db_path = os.path.join(os.path.dirname(__file__), '..', '..', 'database', 'forecast.db')
        super().__init__(db_path)
        self._init_tables()

    def _init_tables(self):
        queries = [
            """
            CREATE TABLE IF NOT EXISTS forecast_daily (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                city TEXT, lat REAL, lon REAL,
                fcst_date TEXT,
                collected_at TIMESTAMP,
                model TEXT,
                weather_code REAL, temperature_2m_max REAL, temperature_2m_min REAL,
                apparent_temperature_max REAL, apparent_temperature_min REAL,
                sunrise TEXT, sunset TEXT, daylight_duration REAL, sunshine_duration REAL,
                uv_index_max REAL, uv_index_clear_sky_max REAL,
                precipitation_sum REAL, rain_sum REAL, showers_sum REAL, snowfall_sum REAL,
                precipitation_hours REAL, precipitation_probability_max REAL,
                wind_speed_10m_max REAL, wind_gusts_10m_max REAL, wind_direction_10m_dominant REAL,
                shortwave_radiation_sum REAL, et0_fao_evapotranspiration REAL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS forecast_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                city TEXT, lat REAL, lon REAL,
                collected_at TIMESTAMP,
                model TEXT,
                payload_json TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS forecast_grid (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fcst_hour TEXT,
                collected_at TIMESTAMP,
                lat REAL, lon REAL,
                temperature_2m REAL, precipitation REAL, cloud_cover REAL, weather_code REAL,
                wind_speed_10m REAL, wind_direction_10m REAL, u10 REAL, v10 REAL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS climate_daily (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                city TEXT, lat REAL, lon REAL,
                date TEXT,
                temperature_2m_max REAL, temperature_2m_min REAL, temperature_2m_mean REAL,
                apparent_temperature_max REAL, apparent_temperature_min REAL,
                precipitation_sum REAL, rain_sum REAL, snowfall_sum REAL,
                precipitation_hours REAL,
                wind_speed_10m_max REAL, wind_gusts_10m_max REAL,
                wind_direction_10m_dominant REAL,
                shortwave_radiation_sum REAL, et0_fao_evapotranspiration REAL,
                sunshine_duration REAL, daylight_duration REAL,
                uv_index_max REAL, weather_code REAL,
                UNIQUE(city, date)
            )
            """,
            """CREATE INDEX IF NOT EXISTS idx_fh_city_date ON forecast_daily(city, fcst_date)""",
            """CREATE INDEX IF NOT EXISTS idx_fs_city_time ON forecast_snapshots(city, collected_at)""",
            """CREATE INDEX IF NOT EXISTS idx_fg_hour ON forecast_grid(fcst_hour)""",
            """CREATE INDEX IF NOT EXISTS idx_cd_city_date ON climate_daily(city, date)""",
        ]
        for query in queries:
            self.execute_update(query)
        # migration for DBs created before cloud_cover existed
        cols = [c.get('name') for c in self.execute_query('PRAGMA table_info(forecast_grid)')]
        if cols and 'cloud_cover' not in cols:
            self.execute_update("ALTER TABLE forecast_grid ADD COLUMN cloud_cover REAL")
        logger.info("Forecast database initialized", module='FORECAST_REPO')

    # ------------------------------------------------------------ forecast daily
    def save_forecast_daily(self, rows: list) -> int:
        if not rows:
            return 0
        query = """
        INSERT INTO forecast_daily
            (city, lat, lon, fcst_date, collected_at, model, weather_code,
             temperature_2m_max, temperature_2m_min, apparent_temperature_max,
             apparent_temperature_min, sunrise, sunset, daylight_duration,
             sunshine_duration, uv_index_max, uv_index_clear_sky_max,
             precipitation_sum, rain_sum, showers_sum, snowfall_sum,
             precipitation_hours, precipitation_probability_max,
             wind_speed_10m_max, wind_gusts_10m_max, wind_direction_10m_dominant,
             shortwave_radiation_sum, et0_fao_evapotranspiration)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """
        params = [
            (
                r.get('city'), r.get('lat'), r.get('lon'), r.get('fcst_date'),
                r.get('collected_at'), r.get('model'),
                r.get('weather_code'), r.get('temperature_2m_max'),
                r.get('temperature_2m_min'), r.get('apparent_temperature_max'),
                r.get('apparent_temperature_min'), r.get('sunrise'), r.get('sunset'),
                r.get('daylight_duration'), r.get('sunshine_duration'),
                r.get('uv_index_max'), r.get('uv_index_clear_sky_max'),
                r.get('precipitation_sum'), r.get('rain_sum'), r.get('showers_sum'),
                r.get('snowfall_sum'), r.get('precipitation_hours'),
                r.get('precipitation_probability_max'), r.get('wind_speed_10m_max'),
                r.get('wind_gusts_10m_max'), r.get('wind_direction_10m_dominant'),
                r.get('shortwave_radiation_sum'), r.get('et0_fao_evapotranspiration'),
            )
            for r in rows
        ]
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params)
            return cursor.rowcount

    def get_latest_forecast_daily(self, city: str, max_age_hours: int = 36) -> List[Dict]:
        """Return the most recent daily forecast rows for a city if fresh enough."""
        rows = self.execute_query(
            "SELECT * FROM forecast_daily WHERE city = ? ORDER BY collected_at DESC LIMIT 20", (city,))
        if not rows:
            return []
        try:
            asof = datetime.fromisoformat(rows[0]['collected_at'])
            if (datetime.now(timezone.utc) - asof).total_seconds() > max_age_hours * 3600:
                return []
        except Exception:
            return []
        latest = rows[0]['collected_at']
        return self.execute_query(
            "SELECT * FROM forecast_daily WHERE city = ? AND collected_at = ? ORDER BY fcst_date",
            (city, latest))

    # ------------------------------------------------------------ snapshots
    def save_snapshot(self, city: str, lat: float, lon: float, model: str, payload: dict):
        query = (
            "INSERT INTO forecast_snapshots (city, lat, lon, collected_at, model, payload_json) "
            "VALUES (?,?,?,?,?,?)"
        )
        now = datetime.now(timezone.utc).isoformat()
        self.execute_update(query, (city, lat, lon, now, model, str(payload)))

    def get_latest_snapshot(self, city: str, max_age_hours: int = 36):
        rows = self.execute_query(
            "SELECT * FROM forecast_snapshots WHERE city = ? ORDER BY collected_at DESC LIMIT 1",
            (city,))
        if not rows:
            return None
        try:
            asof = datetime.fromisoformat(rows[0]['collected_at'])
            if (datetime.now(timezone.utc) - asof).total_seconds() > max_age_hours * 3600:
                return None
        except Exception:
            return None
        return rows[0]

    def prune_snapshots(self, city: str, keep: int = 10):
        rows = self.execute_query(
            "SELECT id FROM forecast_snapshots WHERE city = ? ORDER BY collected_at DESC", (city,))
        ids = [r['id'] for r in rows[keep:]]
        for i in ids:
            self.execute_update("DELETE FROM forecast_snapshots WHERE id = ?", (i,))

    def prune_forecast_daily(self, days: int = 45):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        self.execute_update("DELETE FROM forecast_daily WHERE collected_at < ?", (cutoff,))

    # ------------------------------------------------------------ grid
    def save_grid(self, rows: list) -> int:
        """rows: list of dicts with fcst_hour, lat, lon, temperature_2m, precipitation,
        weather_code, wind_speed_10m, wind_direction_10m, u10, v10, collected_at."""
        if not rows:
            return 0
        query = """
        INSERT INTO forecast_grid
            (fcst_hour, collected_at, lat, lon, temperature_2m, precipitation,
             cloud_cover, weather_code, wind_speed_10m, wind_direction_10m, u10, v10)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """
        params = [
            (
                r.get('fcst_hour'), r.get('collected_at'), r.get('lat'), r.get('lon'),
                r.get('temperature_2m'), r.get('precipitation'), r.get('cloud_cover'),
                r.get('weather_code'), r.get('wind_speed_10m'), r.get('wind_direction_10m'),
                r.get('u10'), r.get('v10'),
            )
            for r in rows
        ]
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params)
            return cursor.rowcount

    def prune_grid(self, days: int = 4):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        self.execute_update("DELETE FROM forecast_grid WHERE collected_at < ?", (cutoff,))

    def get_grid_var(self, var: str, fcst_hour: str) -> List[Dict]:
        col = {'temperature': 'temperature_2m', 'precipitation': 'precipitation',
               'wind': 'wind_speed_10m'}.get(var)
        if col:
            return self.execute_query(
                f"SELECT lat, lon, {col} AS val, u10, v10, wind_direction_10m "
                "FROM forecast_grid WHERE fcst_hour = ? ORDER BY lat, lon", (fcst_hour,))
        return []

    def get_grid_hours(self, max_age_hours: int = 36) -> List[str]:
        rows = self.execute_query("SELECT DISTINCT collected_at FROM forecast_grid ORDER BY collected_at DESC LIMIT 1")
        if not rows:
            return []
        collected = rows[0]['collected_at']
        try:
            if (datetime.now(timezone.utc) - datetime.fromisoformat(collected)).total_seconds() > max_age_hours * 3600:
                return []
        except Exception:
            return []
        rows = self.execute_query(
            "SELECT fcst_hour FROM forecast_grid WHERE collected_at = ? ORDER BY fcst_hour", (collected,))
        return [r['fcst_hour'] for r in rows]

    def get_grid_collected_at(self) -> Optional[str]:
        rows = self.execute_query("SELECT DISTINCT collected_at FROM forecast_grid ORDER BY collected_at DESC LIMIT 1")
        return rows[0]['collected_at'] if rows else None

    # ------------------------------------------------------------ climate
    def upsert_climate_daily(self, rows: list) -> int:
        if not rows:
            return 0
        query = """
        INSERT INTO climate_daily
            (city, lat, lon, date, temperature_2m_max, temperature_2m_min,
             temperature_2m_mean, apparent_temperature_max, apparent_temperature_min,
             precipitation_sum, rain_sum, snowfall_sum, precipitation_hours,
             wind_speed_10m_max, wind_gusts_10m_max, wind_direction_10m_dominant,
             shortwave_radiation_sum, et0_fao_evapotranspiration,
             sunshine_duration, daylight_duration, uv_index_max, weather_code)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(city, date) DO UPDATE SET
            temperature_2m_max=excluded.temperature_2m_max,
            temperature_2m_min=excluded.temperature_2m_min,
            temperature_2m_mean=excluded.temperature_2m_mean,
            precipitation_sum=excluded.precipitation_sum,
            wind_speed_10m_max=excluded.wind_speed_10m_max,
            wind_gusts_10m_max=excluded.wind_gusts_10m_max,
            et0_fao_evapotranspiration=excluded.et0_fao_evapotranspiration
        """
        params = [
            (
                r.get('city'), r.get('lat'), r.get('lon'), r.get('date'),
                r.get('temperature_2m_max'), r.get('temperature_2m_min'),
                r.get('temperature_2m_mean'), r.get('apparent_temperature_max'),
                r.get('apparent_temperature_min'), r.get('precipitation_sum'),
                r.get('rain_sum'), r.get('snowfall_sum'), r.get('precipitation_hours'),
                r.get('wind_speed_10m_max'), r.get('wind_gusts_10m_max'),
                r.get('wind_direction_10m_dominant'), r.get('shortwave_radiation_sum'),
                r.get('et0_fao_evapotranspiration'), r.get('sunshine_duration'),
                r.get('daylight_duration'), r.get('uv_index_max'), r.get('weather_code'),
            )
            for r in rows
        ]
        with self._get_connection() as conn:
            conn.execute("BEGIN")
            cursor = conn.cursor()
            cursor.executemany(query, params)
            return cursor.rowcount

    def get_climate_range(self, city: str, start: str, end: str) -> List[Dict]:
        return self.execute_query(
            "SELECT * FROM climate_daily WHERE city = ? AND date >= ? AND date <= ? ORDER BY date",
            (city, start, end))

    def get_climate_year(self, city: str, year: int) -> List[Dict]:
        return self.execute_query(
            "SELECT * FROM climate_daily WHERE city = ? AND date LIKE ? ORDER BY date",
            (city, f"{year}%"))

    def get_climate_stats(self, city: str) -> Dict:
        rows = self.execute_query(
            "SELECT MIN(date) AS first, MAX(date) AS last, COUNT(*) AS n FROM climate_daily "
            "WHERE city = ?", (city,))
        return rows[0] if rows else {}

    def prune_climate(self, years: int = 8):
        cutoff = f"{datetime.now(timezone.utc).year - years}-01-01"
        self.execute_update("DELETE FROM climate_daily WHERE date < ?", (cutoff,))