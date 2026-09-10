"""
Marine service for business logic
"""
from typing import Dict, List, Optional
from evaluation_service.core.logger import get_logger
from evaluation_service.core.cache import get_cache
from evaluation_service.modules.marine.repository import MarineRepository
from evaluation_service.modules.marine.validator import MarineValidator

logger = get_logger()
cache = get_cache()


class MarineService:
    """Service layer for marine operations"""

    def __init__(self):
        self.repository = MarineRepository()
        self.validator = MarineValidator()

    # ------------------------------------------------------------- currents
    def get_currents(self, use_cache: bool = True) -> tuple[bool, str, List[Dict]]:
        if use_cache:
            cached = cache.get("marine:currents")
            if cached:
                return True, "Sea currents (cache)", cached
        rows = self.repository.get_latest_grid('marine_currents', max_age_hours=6)
        if rows:
            cache.set("marine:currents", rows, ttl=300)
            return True, "Sea currents (db)", rows
        return False, "No current data collected yet. Run POST /api/marine/currents/collect", []

    def save_currents(self, rows: List[Dict]) -> tuple[bool, str, Optional[int]]:
        is_valid, error = self.validator.validate_rows(
            rows, required=['time', 'lat', 'lon'], numeric=['uo', 'vo', 'speed'])
        if not is_valid:
            return False, error, None
        try:
            count = self.repository.save_currents([self.validator.sanitize_grid_row(r) for r in rows])
            self.repository.clear_older_than('marine_currents')
            cache.delete("marine:currents")
            return True, f"Saved {count} current points", count
        except Exception as e:
            logger.error(f"Failed to save currents: {e}", module='MARINE_SERVICE', exc_info=True)
            return False, str(e), None

    # ------------------------------------------------------------- ssh
    def get_ssh(self, use_cache: bool = True) -> tuple[bool, str, List[Dict]]:
        if use_cache:
            cached = cache.get("marine:ssh")
            if cached:
                return True, "Sea surface height (cache)", cached
        rows = self.repository.get_latest_grid('marine_ssh', max_age_hours=6)
        if rows:
            cache.set("marine:ssh", rows, ttl=300)
            return True, "Sea surface height (db)", rows
        return False, "No SSH data collected yet. Run POST /api/marine/ssh/collect", []

    def save_ssh(self, rows: List[Dict]) -> tuple[bool, str, Optional[int]]:
        is_valid, error = self.validator.validate_rows(
            rows, required=['time', 'lat', 'lon'], numeric=['zos'])
        if not is_valid:
            return False, error, None
        try:
            count = self.repository.save_ssh([self.validator.sanitize_grid_row(r) for r in rows])
            self.repository.clear_older_than('marine_ssh')
            cache.delete("marine:ssh")
            return True, f"Saved {count} SSH points", count
        except Exception as e:
            logger.error(f"Failed to save SSH: {e}", module='MARINE_SERVICE', exc_info=True)
            return False, str(e), None

    # ------------------------------------------------------------- vessel risk
    def get_vessel_risk(self, use_cache: bool = True) -> tuple[bool, str, List[Dict]]:
        if use_cache:
            cached = cache.get("marine:vessel_risk")
            if cached:
                return True, "Vessel risk (cache)", cached
        rows = self.repository.get_latest_vessel_risk(max_age_hours=6)
        if rows:
            cache.set("marine:vessel_risk", rows, ttl=300)
            return True, "Vessel risk (db)", rows
        return False, "No vessel risk data. Run POST /api/marine/risk/collect", []

    def save_vessel_risk(self, rows: List[Dict]) -> tuple[bool, str, Optional[int]]:
        is_valid, error = self.validator.validate_rows(
            rows, required=['time', 'lat', 'lon', 'zone'], numeric=['risk_score'])
        if not is_valid:
            return False, error, None
        try:
            count = self.repository.save_vessel_risk([self.validator.sanitize_grid_row(r) for r in rows])
            self.repository.clear_older_than('vessel_risk')
            cache.delete("marine:vessel_risk")
            return True, f"Saved {count} risk zones", count
        except Exception as e:
            logger.error(f"Failed to save vessel risk: {e}", module='MARINE_SERVICE', exc_info=True)
            return False, str(e), None