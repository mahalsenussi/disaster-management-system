"""
Deep-sea wave cross-check sourced from the Open-Meteo Marine API
(https://open-meteo.com/en/docs/marine-weather-api) - free, no key required.

Samples a fixed grid of offshore points spanning the Libyan EEZ / deep sea and
returns significant wave height, period and direction for each point. This is an
independent source of truth to compare against the CMEMS coastal stations.
"""
import threading
import time
import requests
from typing import Dict, List

from evaluation_service.core.logger import get_logger

logger = get_logger()

API_BASE = "https://marine-api.open-meteo.com/v1/marine"

# Deep-sea grid inside/around the Libyan offshore area (lat, lon). Kept offshore
# so it complements (not overlaps) the onshore CMEMS coastal stations.
GRID = [
        (30.8,17.9), (30.8,18.3), (30.8,18.7), (30.8,19.1), (30.8,19.5), (31.2,16.7),
        (31.2,17.1), (31.2,17.5), (31.2,17.9), (31.2,18.3), (31.2,18.7), (31.2,19.1),
        (31.2,19.5), (31.2,19.9), (31.6,15.9), (31.6,16.3), (31.6,16.7), (31.6,17.1),
        (31.6,17.5), (31.6,17.9), (31.6,18.3), (31.6,18.7), (31.6,19.1), (31.6,19.5),
        (32.0,15.5), (32.0,15.9), (32.0,16.3), (32.0,16.7), (32.0,17.1), (32.0,17.5),
        (32.0,17.9), (32.0,18.3), (32.0,18.7), (32.0,19.1), (32.0,19.5), (32.0,19.9),
        (32.0,24.3), (32.0,24.7), (32.4,15.1), (32.4,15.5), (32.4,15.9), (32.4,16.3),
        (32.4,16.7), (32.4,17.1), (32.4,17.5), (32.4,17.9), (32.4,18.3), (32.4,18.7),
        (32.4,19.1), (32.4,19.5), (32.4,19.9), (32.4,20.3), (32.4,23.1), (32.4,23.5),
        (32.4,23.9), (32.4,24.3), (32.4,24.7), (32.8,13.5), (32.8,13.9), (32.8,14.3),
        (32.8,14.7), (32.8,15.1), (32.8,15.5), (32.8,15.9), (32.8,16.3), (32.8,16.7),
        (32.8,17.1), (32.8,17.5), (32.8,17.9), (32.8,18.3), (32.8,18.7), (32.8,19.1),
        (32.8,19.5), (32.8,19.9), (32.8,20.3), (32.8,20.7), (32.8,21.1), (32.8,21.9),
        (32.8,22.3), (32.8,22.7), (32.8,23.1), (32.8,23.5), (32.8,23.9), (32.8,24.3),
        (32.8,24.7), (33.2,11.9), (33.2,12.3), (33.2,12.7), (33.2,13.1), (33.2,13.5),
        (33.2,13.9), (33.2,14.3), (33.2,14.7), (33.2,15.1), (33.2,15.5), (33.2,15.9),
        (33.2,16.3), (33.2,16.7), (33.2,17.1), (33.2,17.5), (33.2,17.9), (33.2,18.3),
        (33.2,18.7), (33.2,19.1), (33.2,19.5), (33.2,19.9), (33.2,20.3), (33.2,20.7),
        (33.2,21.1), (33.2,21.5), (33.2,21.9), (33.2,22.3), (33.2,22.7), (33.2,23.1),
        (33.2,23.5), (33.2,23.9), (33.2,24.3), (33.2,24.7), (33.5,12.4), (33.5,19.0),
        (33.5,21.5), (33.6,11.9), (33.6,12.3), (33.6,12.7), (33.6,13.1), (33.6,13.5),
        (33.6,13.6), (33.6,13.9), (33.6,14.3), (33.6,14.7), (33.6,15.1), (33.6,15.5),
        (33.6,15.9), (33.6,16.3), (33.6,16.7), (33.6,17.1), (33.6,17.5), (33.6,17.9),
        (33.6,18.3), (33.6,18.7), (33.6,19.1), (33.6,19.5), (33.6,19.9), (33.6,20.3),
        (33.6,20.7), (33.6,21.1), (33.6,21.5), (33.6,21.9), (33.6,22.3), (33.6,22.7),
        (33.6,23.1), (33.6,23.5), (33.6,23.9), (33.6,24.3), (33.6,24.7), (33.6,25.6),
        (33.8,14.8), (33.8,17.0), (33.8,23.4), (34.0,18.0), (34.0,24.4), (34.2,16.0),
        (34.4,20.0), (34.4,22.4), (34.6,12.0), (34.6,24.8), (35.2,14.2), (35.2,16.6),
        (35.2,19.4), (35.2,22.0),
]

_cache: Dict[str, object] = {}
_lock = threading.Lock()


def get_deep_sea_waves(max_age_sec: int = 1200) -> tuple[bool, str, List[Dict]]:
    """Return latest wave state at each offshore point, using short TTL cache."""
    global _cache
    now = time.time()
    with _lock:
        if _cache and now - _cache.get('ts', 0) < max_age_sec:
            return True, f"Open-Meteo deep-sea waves (cache, {len(_cache['rows'])} pts)", _cache['rows']

    rows = []
    for lat, lon in GRID:
        try:
            r = requests.get(API_BASE, params={
                'latitude': lat, 'longitude': lon,
                'current': 'wave_height,wave_direction,wave_period',
                'timezone': 'UTC',
            }, timeout=12)
            r.raise_for_status()
            payload = r.json()
            if payload.get('elevation', 0) > 5:
                continue
            cur = payload.get('current', {})
            rows.append({
                'lat': lat, 'lon': lon,
                'wave_height': cur.get('wave_height'),
                'wave_period': cur.get('wave_period'),
                'wave_direction': cur.get('wave_direction'),
                'src': 'open-meteo',
            })
        except Exception as e:
            logger.warning(f"Open-Meteo point ({lat},{lon}) failed: {e}", module='OPENMETEO')
            rows.append({'lat': lat, 'lon': lon, 'wave_height': None,
                         'wave_period': None, 'wave_direction': None, 'src': 'open-meteo'})

    valid = [pt for pt in rows if pt['wave_height'] is not None]
    with _lock:
        _cache = {'ts': time.time(), 'rows': rows}
    if not valid:
        return False, "Open-Meteo deep-sea waves unavailable", rows
    message = (f"Open-Meteo deep-sea waves ({len(valid)}/{len(rows)} pts, "
               f"max Hs {max(p['wave_height'] for p in valid):.2f} m)")
    return True, message, rows