"""
Marine data validator
"""
from typing import Dict, Optional
from evaluation_service.core.logger import get_logger

logger = get_logger()

class MarineValidator:
    """Validates marine data before processing"""

    @staticmethod
    def validate_rows(rows: list, required: list, numeric: list) -> tuple[bool, Optional[str]]:
        """Validate a batch of grid rows.

        Returns:
            (is_valid, error_message)
        """
        if not rows:
            return False, "No data provided"
        for idx, row in enumerate(rows):
            for field in required:
                if field not in row or row[field] is None:
                    return False, f"Row {idx} missing required field: {field}"
            for field in numeric:
                if field in row and row[field] is not None:
                    try:
                        float(row[field])
                    except (ValueError, TypeError):
                        return False, f"Row {idx} field {field} must be numeric"
        return True, None

    @staticmethod
    def sanitize_grid_row(row: Dict) -> Dict:
        """Coerce numeric fields in a marine grid row."""
        out = dict(row)
        for field in ('uo', 'vo', 'speed', 'direction_deg', 'zos',
                      'lat', 'lon', 'risk_score', 'wave_height', 'wave_period',
                      'wind_speed', 'current_speed', 'sea_level_anomaly'):
            if field in out and out[field] is not None:
                try:
                    out[field] = float(out[field])
                except (ValueError, TypeError):
                    out[field] = None
        return out