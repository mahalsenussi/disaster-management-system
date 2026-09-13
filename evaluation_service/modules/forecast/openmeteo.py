"""
Open-Meteo service: forecast, historical (ERA5), climate analysis and the
gridded playback layer for the windy-style forecast page.

Free API, no key required. Batch-friendly: multiple coordinates per request.
"""
import json
import math
import threading
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import requests

from evaluation_service.core.logger import get_logger
from evaluation_service.modules.forecast.repository import ForecastRepository

logger = get_logger()

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HISTORY_URL = "https://archive-api.open-meteo.com/v1/archive"

# Typical Libyan cities/ports used for the picker and scheduled collection.
CITIES = [
    {"name": "Tripoli", "lat": 32.887, "lon": 13.191},
    {"name": "Benghazi", "lat": 32.116, "lon": 20.066},
    {"name": "Misrata", "lat": 32.375, "lon": 15.094},
    {"name": "Derna", "lat": 32.755, "lon": 22.633},
    {"name": "Sirte", "lat": 31.200, "lon": 16.583},
    {"name": "Tobruk", "lat": 32.083, "lon": 23.918},
    {"name": "Al Khums", "lat": 32.650, "lon": 14.267},
    {"name": "Zawiya", "lat": 32.757, "lon": 12.721},
    {"name": "Bayda", "lat": 32.760, "lon": 21.760},
    {"name": "Sabha", "lat": 27.033, "lon": 14.433},
    {"name": "Ghadames", "lat": 30.130, "lon": 9.500},
    {"name": "Zuwara", "lat": 32.930, "lon": 12.090},
    {"name": "Sabratha", "lat": 32.800, "lon": 12.480},
    {"name": "Gharyan", "lat": 32.170, "lon": 13.020},
    {"name": "Nalut", "lat": 31.870, "lon": 10.980},
    {"name": "Murzuq", "lat": 25.920, "lon": 13.910},
    {"name": "Ubari", "lat": 26.590, "lon": 12.780},
]

# A gridded playback layer over Libya (land + sea) at 0.5 degree.
GRID_LAT_MIN, GRID_LAT_MAX, GRID_LAT_STEP = 26.0, 36.5, 0.5
GRID_LON_MIN, GRID_LON_MAX, GRID_LON_STEP = 9.0, 26.0, 0.5
GRID_BATCH = 250          # coordinates per request (fits under URL + rate limits)
GRID_HOURS = 48           # playback horizon
GRID_MAX_AGE_HOURS = 36   # a grid snapshot stays usable this long

FORECAST_DAILY_VARS = (
    "weather_code,temperature_2m_max,temperature_2m_min,"
    "apparent_temperature_max,apparent_temperature_min,"
    "sunrise,sunset,daylight_duration,sunshine_duration,"
    "uv_index_max,uv_index_clear_sky_max,precipitation_sum,rain_sum,"
    "showers_sum,snowfall_sum,precipitation_hours,precipitation_probability_max,"
    "wind_speed_10m_max,wind_gusts_10m_max,wind_direction_10m_dominant,"
    "shortwave_radiation_sum,et0_fao_evapotranspiration"
)

FORECAST_HOURLY_VARS = (
    "temperature_2m,relative_humidity_2m,dew_point_2m,apparent_temperature,"
    "precipitation_probability,precipitation,rain,showers,snowfall,weather_code,"
    "pressure_msl,surface_pressure,cloud_cover,cloud_cover_low,cloud_cover_mid,"
    "cloud_cover_high,visibility,evapotranspiration,et0_fao_evapotranspiration,"
    "vapor_pressure_deficit,wind_speed_10m,wind_speed_80m,wind_speed_120m,"
    "wind_speed_180m,wind_direction_10m,wind_direction_80m,wind_direction_120m,"
    "wind_direction_180m,wind_gusts_10m,soil_moisture_0_to_1cm,soil_temperature_0cm"
)

FORECAST_CURRENT_VARS = (
    "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,"
    "precipitation,rain,showers,snowfall,weather_code,cloud_cover,"
    "pressure_msl,surface_pressure,wind_speed_10m,wind_direction_10m,wind_gusts_10m"
)

GRID_HOURLY_VARS = "temperature_2m,precipitation,cloud_cover,weather_code,wind_speed_10m,wind_direction_10m"

_cache: Dict[str, dict] = {}
_cache_ts: Dict[str, float] = {}
_lock = threading.RLock()

_HISTORY_START = "1980-01-01"   # plenty of years for normals/records


def city_lookup(name: str) -> Optional[dict]:
    for c in CITIES:
        if c["name"].lower() == name.lower():
            return c
    return None


# ----------------------------------------------------------------- shared http
def _get(url: str, params: dict, timeout: int = 90) -> Optional[dict]:
    last_err = None
    for attempt in range(5):
        try:
            r = requests.get(url, params=params, timeout=timeout,
                             headers={"User-Agent": "Libya-Disaster-Watch/1.0"})
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                wait = (attempt + 1) * 10
                logger.warning(f"Open-Meteo rate limit hit, retrying in {wait}s", module='OPENMETEO')
                time.sleep(wait)
                last_err = "rate limited"
                continue
            logger.warning(f"Open-Meteo HTTP {r.status_code} for {url}: {r.text[:120]}",
                           module='OPENMETEO')
            return None
        except Exception as e:
            last_err = e
            time.sleep(3)
    logger.warning(f"Open-Meteo request failed after retries: {last_err}", module='OPENMETEO')
    return None


def _cache_get(key: str, ttl_hours: float) -> Optional[dict]:
    with _lock:
        ts = _cache_ts.get(key)
        if ts is not None and (time.time() - ts) < ttl_hours * 3600:
            return _cache.get(key)
    return None


def _cache_set(key: str, value: dict):
    with _lock:
        _cache[key] = value or {}
        _cache_ts[key] = time.time()


# ------------------------------------------------------------------ forecast
def fetch_forecast(lat: float, lon: float, days: int = 7, model: str = "gfs_seamless"):
    params = {
        "latitude": lat, "longitude": lon,
        "current": FORECAST_CURRENT_VARS,
        "hourly": FORECAST_HOURLY_VARS,
        "daily": FORECAST_DAILY_VARS,
        "forecast_days": days,
        "timezone": "UTC",
        "wind_speed_unit": "ms",
    }
    if model:
        params["models"] = model
    return _get(FORECAST_URL, params)


def _flatten_daily(daily: dict, city: str, lat: float, lon: float,
                   collected_at: str, model: str) -> List[dict]:
    if not daily or "time" not in daily:
        return []
    times = daily.get("time") or []
    rows = []
    for i in range(len(times)):
        def g(k):
            arr = daily.get(k)
            return arr[i] if arr and i < len(arr) else None
        rows.append({
            "city": city, "lat": lat, "lon": lon, "fcst_date": times[i],
            "collected_at": collected_at, "model": model,
            "weather_code": g("weather_code"), "temperature_2m_max": g("temperature_2m_max"),
            "temperature_2m_min": g("temperature_2m_min"),
            "apparent_temperature_max": g("apparent_temperature_max"),
            "apparent_temperature_min": g("apparent_temperature_min"),
            "sunrise": g("sunrise"), "sunset": g("sunset"),
            "daylight_duration": g("daylight_duration"),
            "sunshine_duration": g("sunshine_duration"),
            "uv_index_max": g("uv_index_max"),
            "uv_index_clear_sky_max": g("uv_index_clear_sky_max"),
            "precipitation_sum": g("precipitation_sum"), "rain_sum": g("rain_sum"),
            "showers_sum": g("showers_sum"), "snowfall_sum": g("snowfall_sum"),
            "precipitation_hours": g("precipitation_hours"),
            "precipitation_probability_max": g("precipitation_probability_max"),
            "wind_speed_10m_max": g("wind_speed_10m_max"),
            "wind_gusts_10m_max": g("wind_gusts_10m_max"),
            "wind_direction_10m_dominant": g("wind_direction_10m_dominant"),
            "shortwave_radiation_sum": g("shortwave_radiation_sum"),
            "et0_fao_evapotranspiration": g("et0_fao_evapotranspiration"),
        })
    return rows


def collect_city(city_name: str, model: str = "gfs_seamless") -> Tuple[bool, str, Optional[dict]]:
    """Fetch a full forecast for one city, persist it, and return the payload."""
    c = city_lookup(city_name)
    if not c:
        return False, f"Unknown city: {city_name}", None
    key = f"fc:{city_name}"
    cached = _cache_get(key, 1.0)
    if cached and cached.get("how") == "live":
        return True, f"Forecast cached ({city_name})", cached

    payload = fetch_forecast(c["lat"], c["lon"], days=7, model=model)
    if payload is None:
        return False, f"Open-Meteo unreachable for {city_name}", None

    collected = datetime.now(timezone.utc).isoformat()
    repo = ForecastRepository()
    daily_rows = _flatten_daily(payload.get("daily") or {}, city_name, c["lat"], c["lon"],
                                collected, model)
    repo.save_forecast_daily(daily_rows)
    repo.save_snapshot(city_name, c["lat"], c["lon"], model, payload)
    repo.prune_snapshots(city_name, keep=10)
    repo.prune_forecast_daily(days=45)

    _cache_set(key, {"payload": payload, "how": "live", "asof": collected, "city": city_name})
    msg = f"Saved {len(daily_rows)} forecast days for {city_name}"
    return True, msg, {"payload": payload, "how": "live", "asof": collected, "city": city_name}


def get_city_forecast(city_name: str) -> Tuple[bool, str, Optional[dict]]:
    """Serve the latest city forecast: cache, then DB, then live fetch."""
    key = f"fc:{city_name}"
    cached = _cache_get(key, 1.0)
    if cached:
        return True, f"Open-Meteo forecast ({city_name})", cached

    repo = ForecastRepository()
    snap = repo.get_latest_snapshot(city_name, max_age_hours=36)
    if snap:
        try:
            payload = json.loads(snap['payload_json'])
            _cache_set(key, {"payload": payload, "how": "db", "asof": snap['collected_at'],
                             "city": city_name})
            return True, "Open-Meteo forecast (db)", {"payload": payload, "how": "db",
                                                      "asof": snap['collected_at'], "city": city_name}
        except Exception:
            pass

    ok, msg, payload = collect_city(city_name)
    if ok:
        return True, msg, payload
    return False, msg, None


# ------------------------------------------------------------------ history
def fetch_history_daily(lat: float, lon: float, start: str, end: str):
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": start, "end_date": end,
        "daily": FORECAST_DAILY_VARS,
        "timezone": "UTC",
        "wind_speed_unit": "ms",
    }
    return _get(HISTORY_URL, params)


def _flatten_history(daily: dict, city: str, lat: float, lon: float) -> List[dict]:
    if not daily or "time" not in daily:
        return []
    times = daily.get("time") or []
    rows = []
    for i in range(len(times)):
        def g(k):
            arr = daily.get(k)
            return arr[i] if arr and i < len(arr) else None
        tmax, tmin = g("temperature_2m_max"), g("temperature_2m_min")
        mean = None
        if tmax is not None and tmin is not None:
            mean = (tmax + tmin) / 2.0
        rows.append({
            "city": city, "lat": lat, "lon": lon, "date": times[i],
            "temperature_2m_max": tmax, "temperature_2m_min": tmin,
            "temperature_2m_mean": mean,
            "apparent_temperature_max": g("apparent_temperature_max"),
            "apparent_temperature_min": g("apparent_temperature_min"),
            "precipitation_sum": g("precipitation_sum"), "rain_sum": g("rain_sum"),
            "snowfall_sum": g("snowfall_sum"), "precipitation_hours": g("precipitation_hours"),
            "wind_speed_10m_max": g("wind_speed_10m_max"),
            "wind_gusts_10m_max": g("wind_gusts_10m_max"),
            "wind_direction_10m_dominant": g("wind_direction_10m_dominant"),
            "shortwave_radiation_sum": g("shortwave_radiation_sum"),
            "et0_fao_evapotranspiration": g("et0_fao_evapotranspiration"),
            "sunshine_duration": g("sunshine_duration"),
            "daylight_duration": g("daylight_duration"),
            "uv_index_max": g("uv_index_max"), "weather_code": g("weather_code"),
        })
    return rows


def ensure_climate(city_name: str, years: int = 5) -> Tuple[bool, str, int]:
    """Fetch + persist the missing range of historical dailies for a city."""
    c = city_lookup(city_name)
    if not c:
        return False, f"Unknown city: {city_name}", 0
    repo = ForecastRepository()
    stats = repo.get_climate_stats(city_name)
    nowy = datetime.now(timezone.utc).year
    today_dt = datetime.now(timezone.utc)
    today = today_dt.strftime("%Y-%m-%d")
    wanted_start = f"{nowy - years}-01-01"

    if stats and stats.get('last'):
        last_dt = datetime.fromisoformat(stats['last'])
        if (today_dt.date() - last_dt.date()).days <= 4 and stats.get('first', '9999') <= wanted_start:
            return True, f"Climate history up to date ({stats['last']})", stats['n']
        start = (last_dt + timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        start = wanted_start
    if start > today:
        return True, "Climate history already covers today", 0

    # chunk by calendar year to stay inside the API window
    total = 0
    y0, y1 = int(start[:4]), int(today[:4])
    for y in range(y0, y1 + 1):
        s = start if y == y0 else f"{y}-01-01"
        e = f"{y}-12-31" if y < y1 else today
        if s > e:
            continue
        payload = fetch_history_daily(c["lat"], c["lon"], s, e)
        if payload is None or "daily" not in payload:
            logger.warning(f"No history for {city_name} {s}..{e}", module='OPENMETEO')
            continue
        rows = _flatten_history(payload["daily"], city_name, c["lat"], c["lon"])
        if rows:
            total += repo.upsert_climate_daily(rows)
    repo.prune_climate(years=8)
    return True, f"Stored {total} historical days for {city_name}", total


def get_history(city_name: str, start: str, end: str,
                ensure: bool = True) -> Tuple[bool, str, List[dict]]:
    """Serve ERA5 daily history for a city (persisted first if needed)."""
    if ensure:
        ok, msg, n = ensure_climate(city_name, years=5)
        if not ok:
            return False, msg, []
    c = city_lookup(city_name)
    repo = ForecastRepository()
    rows = repo.get_climate_range(city_name, start, end)
    if not rows:
        return False, "No historical data for range", []
    return True, f"{len(rows)} days ({start} → {end})", rows


# ------------------------------------------------------------------ climate
def _month_key(d: str) -> Tuple[int, int]:
    return int(d[:4]), int(d[5:7])


def build_month_maps(rows: List[dict]):
    """month -> aggregated stats across years."""
    buckets = {}
    for r in rows:
        mk = r['date'][5:7]
        buckets.setdefault(mk, []).append(r)
    stats = {}
    for mk, items in buckets.items():
        tmax = [x['temperature_2m_max'] for x in items if x['temperature_2m_max'] is not None]
        tmin = [x['temperature_2m_min'] for x in items if x['temperature_2m_min'] is not None]
        tmean = [x['temperature_2m_mean'] for x in items if x['temperature_2m_mean'] is not None]
        prec = [x['precipitation_sum'] for x in items if x['precipitation_sum'] is not None]
        wind = [x['wind_speed_10m_max'] for x in items if x['wind_speed_10m_max'] is not None]
        stats[mk] = {
            "n": len(items),
            "mean_max": sum(tmax) / len(tmax) if tmax else None,
            "mean_min": sum(tmin) / len(tmin) if tmin else None,
            "mean_temp": sum(tmean) / len(tmean) if tmean else None,
            "mean_precip": sum(prec) / len(prec) if prec else None,
            "max_precip": max(prec) if prec else None,
            "mean_wind": sum(wind) / len(wind) if wind else None,
            "record_max": max(tmax) if tmax else None,
            "record_min": min(tmin) if tmin else None,
        }
    return {f"{int(m):02d}": v for m, v in stats.items()}


def get_climate(city_name: str) -> Tuple[bool, str, Optional[dict]]:
    """Normals (multi-year monthly), all-time records, and data coverage."""
    ok, msg, n = ensure_climate(city_name, years=5)
    if not ok:
        return False, msg, None
    repo = ForecastRepository()
    stats = repo.get_climate_stats(city_name)
    if not stats or not stats.get('first'):
        return False, "No climate data yet", None
    rows = repo.get_climate_range(city_name, stats['first'], stats['last'])
    monthly = build_month_maps(rows)
    tmax_vals = [r['temperature_2m_max'] for r in rows if r['temperature_2m_max'] is not None]
    tmin_vals = [r['temperature_2m_min'] for r in rows if r['temperature_2m_min'] is not None]
    prec_vals = [r['precipitation_sum'] for r in rows if r['precipitation_sum'] is not None]
    wind_vals = [r['wind_speed_10m_max'] for r in rows if r['wind_speed_10m_max'] is not None]
    hottest = max(rows, key=lambda r: r['temperature_2m_max'] or -999)
    coldest = min(rows, key=lambda r: r['temperature_2m_min'] or 999)
    wettest = max(rows, key=lambda r: r['precipitation_sum'] or -999)
    windiest = max(rows, key=lambda r: r['wind_speed_10m_max'] or -999)
    all_time = {
        "hottest": {"date": hottest['date'], "value": hottest['temperature_2m_max']},
        "coldest": {"date": coldest['date'], "value": coldest['temperature_2m_min']},
        "wettest": {"date": wettest['date'], "value": wettest['precipitation_sum']},
        "windiest": {"date": windiest['date'], "value": windiest['wind_speed_10m_max']},
    }
    span = {
        "from": stats['first'], "to": stats['last'], "days": stats['n'],
        "mean_temp": (sum(tmax_vals) + sum(tmin_vals)) / (len(tmax_vals) + len(tmin_vals))
                     if tmax_vals and tmin_vals else None,
        "annual_precip": sum(prec_vals) if prec_vals else None,
        "mean_wind": sum(wind_vals) / len(wind_vals) if wind_vals else None,
    }
    return True, "Climate computed", {"monthly": monthly, "all_time": all_time, "span": span}


def get_anomaly(city_name: str, year: int) -> Tuple[bool, str, Optional[dict]]:
    """Monthly temp/precip anomaly for a year vs the multi-year monthly normals."""
    ok, msg, _ = ensure_climate(city_name, years=5)
    if not ok:
        return False, msg, None
    repo = ForecastRepository()
    stats = repo.get_climate_stats(city_name)
    if not stats or not stats.get('first'):
        return False, "No climate data", None
    all_rows = repo.get_climate_range(city_name, stats['first'], stats['last'])
    monthly = build_month_maps(all_rows)
    year_rows = repo.get_climate_year(city_name, year)
    months = {}
    for r in year_rows:
        mk = r['date'][5:7]
        months.setdefault(mk, []).append(r)
    out = []
    for mk in sorted(months):
        items = months[mk]
        tmean = sum(x['temperature_2m_mean'] for x in items if x['temperature_2m_mean'] is not None)
        cnt = sum(1 for x in items if x['temperature_2m_mean'] is not None)
        avg = tmean / cnt if cnt else None
        prec = sum(x['precipitation_sum'] for x in items if x['precipitation_sum'] is not None)
        norm = monthly.get(mk, {})
        out.append({
            "month": mk,
            "temp": avg,
            "temp_normal": norm.get("mean_temp"),
            "temp_anomaly": (avg - norm["mean_temp"]) if (avg is not None and norm.get("mean_temp") is not None) else None,
            "precip": prec,
            "precip_normal": norm.get("mean_precip"),
            "precip_anomaly_pct": ((prec - norm["mean_precip"]) / norm["mean_precip"] * 100)
                                  if (norm.get("mean_precip") not in (None, 0)) else None,
            "n": cnt,
        })
    return True, f"{year} anomaly vs multi-year normals", {"year": year, "months": out}


# ------------------------------------------------------------------ grid
def _build_grid_points() -> List[Tuple[float, float]]:
    pts = []
    lat = GRID_LAT_MIN
    while lat <= GRID_LAT_MAX + 1e-9:
        lon = GRID_LON_MIN
        while lon <= GRID_LON_MAX + 1e-9:
            pts.append((round(lat, 4), round(lon, 4)))
            lon += GRID_LON_STEP
        lat += GRID_LAT_STEP
    return pts


def _u10_v10(wind_speed: Optional[float], wind_dir: Optional[float]) -> Tuple[float, float]:
    """Conventional u=-(ws)*sin(dir'); v=-(ws)*cos(dir') for 'from' direction."""
    if wind_speed is None or wind_dir is None:
        return 0.0, 0.0
    rad = math.radians(wind_dir)
    return -wind_speed * math.sin(rad), -wind_speed * math.cos(rad)


def collect_grid() -> Tuple[bool, str, int]:
    """Fetch the gridded playback layer and persist it."""
    points = _build_grid_points()
    collected = datetime.now(timezone.utc).isoformat()
    return _persist_grid_all_hours(ForecastRepository(), points, collected)


def _persist_grid_all_hours(repo, points, collected) -> Tuple[bool, str, int]:
    """Fetch every hour explicitly (one chunked pass per the near horizon)."""
    # fetch full hourly series for the first 48 hours in one or two batched calls
    # We refetch with forecast_days to cover GRID_HOURS.
    all_rows = []
    for i in range(0, len(points), GRID_BATCH):
        chunk = points[i:i + GRID_BATCH]
        lats = ",".join(str(p[0]) for p in chunk)
        lons = ",".join(str(p[1]) for p in chunk)
        data = _get(FORECAST_URL, {
            "latitude": lats, "longitude": lons,
            "hourly": GRID_HOURLY_VARS,
            "forecast_days": max(1, math.ceil(GRID_HOURS / 24)),
            "timezone": "UTC", "wind_speed_unit": "ms",
            "models": "gfs_seamless",
        })
        if not data:
            return False, "Grid fetch failed", 0
        for idx, p in enumerate(chunk):
            if idx >= len(data) or not data[idx].get("hourly"):
                continue
            h = data[idx]["hourly"]
            times = h.get("time") or []
            temps = h.get("temperature_2m") or []
            precs = h.get("precipitation") or []
            clouds = h.get("cloud_cover") or []
            wcs = h.get("weather_code") or []
            wss = h.get("wind_speed_10m") or []
            wds = h.get("wind_direction_10m") or []
            for k in range(min(len(times), GRID_HOURS)):
                ws = wss[k] if k < len(wss) else None
                wd = wds[k] if k < len(wds) else None
                u10, v10 = _u10_v10(ws, wd)
                all_rows.append({
                    "fcst_hour": times[k], "collected_at": collected,
                    "lat": p[0], "lon": p[1],
                    "temperature_2m": temps[k] if k < len(temps) else None,
                    "precipitation": precs[k] if k < len(precs) else None,
                    "cloud_cover": clouds[k] if k < len(clouds) else None,
                    "weather_code": wcs[k] if k < len(wcs) else None,
                    "wind_speed_10m": ws, "wind_direction_10m": wd,
                    "u10": u10, "v10": v10,
                })
        time.sleep(1.5)  # keep peak burst under the minutely cap
    if not all_rows:
        return False, "Grid yielded no rows", 0
    repo.save_grid(all_rows)
    repo.prune_grid(days=4)
    _cache_set("grid", {"collected": collected, "hours": sorted({r['fcst_hour'] for r in all_rows})})
    msg = f"Saved {len(all_rows)} grid pts ({len(all_rows) // GRID_HOURS} pts × {GRID_HOURS}h)"
    return True, msg, len(all_rows)


def get_grid_hours() -> List[str]:
    cached = _cache_get("grid", GRID_MAX_AGE_HOURS)
    if cached:
        return cached.get("hours") or []
    repo = ForecastRepository()
    hours = repo.get_grid_hours(max_age_hours=GRID_MAX_AGE_HOURS)
    if hours:
        _cache_set("grid", {"collected": repo.get_grid_collected_at(), "hours": hours})
    return hours


def get_grid_var(var: str, hour: Optional[str] = None) -> Tuple[bool, str, dict]:
    hours = get_grid_hours()
    if not hours:
        return False, "No grid data collected yet", {}
    repo = ForecastRepository()
    if hour and hour in hours:
        rows = repo.get_grid_var(var, hour)
        return True, f"grid {var} {hour}", {"hour": hour, "data": rows, "hours": hours}
    # fallback: nearest hour
    import datetime as dt
    target = dt.datetime.fromisoformat(hour) if hour else None
    best = min(hours, key=lambda h: abs(dt.datetime.fromisoformat(h) - target)) if target else hours[0]
    rows = repo.get_grid_var(var, best)
    return True, f"grid {var} {best} (nearest)", {"hour": best, "data": rows, "hours": hours}


def get_grid_all(var: str) -> Tuple[bool, str, dict]:
    """Return every hour of a variable for the latest collected snapshot."""
    hours = get_grid_hours()
    if not hours:
        return False, "No grid data collected yet", {}
    repo = ForecastRepository()
    collected = repo.get_grid_collected_at()
    rows = repo.execute_query(
        "SELECT fcst_hour, lat, lon, temperature_2m, precipitation, cloud_cover, weather_code, "
        "wind_speed_10m, wind_direction_10m, u10, v10 FROM forecast_grid "
        "WHERE collected_at = ? ORDER BY fcst_hour, lat, lon", (collected,))
    return True, f"grid {var} ({len(rows)} pts)", {"hours": hours, "collected": collected, "rows": rows}


def prune_everything():
    repo = ForecastRepository()
    repo.prune_grid(days=4)
    repo.prune_forecast_daily(days=45)
    repo.prune_climate(years=8)