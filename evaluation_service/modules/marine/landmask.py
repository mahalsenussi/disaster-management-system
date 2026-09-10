"""
Land mask for the marine grid.

Filters out lat/lon cells that fall on land, so current arrows and SSH/sea-level
heat layers only render over actual sea where CMEMS data physically exists.
Uses Natural Earth 110m land polygons (public domain) shipped in data/.
"""
import json
import os
from functools import lru_cache
from typing import List, Tuple

_LAND_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'ne_110m_land.geojson')


@lru_cache(maxsize=None)
def _land_polys() -> List[Tuple[List[Tuple[float, float]], Tuple[float, float, float, float]]]:
    """Load land polygons once: (outer_ring, (min_lon, min_lat, max_lon, max_lat))."""
    polys = []
    with open(_LAND_PATH) as f:
        gj = json.load(f)
    for feat in gj['features']:
        geom = feat['geometry']
        rings = geom['coordinates'] if geom['type'] == 'MultiPolygon' else [geom['coordinates']]
        for ring in rings:
            outer = ring[0]
            xs = [p[0] for p in outer]
            ys = [p[1] for p in outer]
            polys.append((outer, (min(xs), min(ys), max(xs), max(ys))))
    return polys


def _pip(lon: float, lat: float, ring: List[Tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon test."""
    inside = False
    j = len(ring) - 1
    for i, (xi, yi) in enumerate(ring):
        xj, yj = ring[j]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def is_land(lon: float, lat: float, polys: List = None) -> bool:
    """Return True if the given lon/lat falls on a land polygon."""
    polys = polys if polys is not None else _land_polys()
    for ring, (min_lon, min_lat, max_lon, max_lat) in polys:
        if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
            continue
        if _pip(lon, lat, ring):
            return True
    return False


def filter_to_sea(rows: List[dict]) -> List[dict]:
    """Drop all grid rows that fall on land."""
    polys = _land_polys()
    return [r for r in rows if not is_land(r['lon'], r['lat'], polys)]