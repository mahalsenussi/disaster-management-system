# Libya Weather & Sea Level Interactive Map — Implementation Plan (v2)

## 1. Objective

Build a dynamic, interactive weather / sea-level / ocean-current monitoring map for Libya,
reusing the data infrastructure already running on the emergency system server
(10.147.18.194, public `ev.onlineacademy.com.ly`). Accessible to outside users.

## 2. Confirmed On-This-System Data Sources

| Source | Access path on system | Data | Dataset / API | Status |
|--------|----------------------|------|---------------|--------|
| Weather (temp/humidity/pressure/wind) | OpenWeatherMap | point data per city | `api.openweathermap.org/data/2.5/weather` | Verified running (eval svc) |
| Waves (height/period/direction/wind) | `copernicusmarine` CLI + `xarray` | Med wave forecast, hourly | `cmems_mod_med_wav_anfc_4.2km_PT1H-i` | Verified in coastal collector |
| **Sea surface currents (uo/vo)** | `copernicusmarine` CLI | Med physics anal/forecast, hourly 2D | `cmems_mod_med_phy-cur_anfc_4.2km-2D_PT1H-m` (product MEDSEA_ANALYSISFORECAST_PHY_006_013) | ✅ confirmed variables uo/vo via `describe` |
| **Sea surface height (zos)** | `copernicusmarine` CLI | Med SSH, daily | `cmems_mod_med_phy-ssh_anfc_4.2km_P1D-m` | ✅ confirmed `zos` variable |
| Sea level anomaly (observed) | UNESCO-IOC SLSMF | station gauge data, no auth | `www.ioc-sealevelmonitoring.org/service.php?format=json&station={loc}` | ✅ HTTP 200 reachable |
| AI risk evaluation / predictions | Ollama (localhost:11434) | risk_score + text eval | `/api/weather/evaluate`, `/api/coastal/evaluate`, `/api/danger/predict/{city}` | Running (eval svc) |
| Geospatial layers (EEZ, coastline, inundation) | GeoServer 2.25.2 systemd svc on 127.0.0.1:8080, PostGIS `lrc_ops` | WMS/WFS | workspaces `lrc` (sea_level_points, affected_areas, branches, incidents, teams), `ne` (osm_libya, libya-shp, NaturalEarth) | Running |

> Note: GeoServer here runs as a **systemd service** (`geoserver.service`), not Docker.
> CONFIRMED with user: Copernicus is installed as a Python package (`copernicusmarine`
> 2.4.1) on the emergency server — **not Docker**. That is the access path we use.
> The `my_geonode` docker-compose (GeoNode/GeoServer) exists under `/home/mahmoud/my_geonode`
> but is not currently running.
>
> **CMEMS credentials decision (2026-09-10):** none stored yet
> (`~/.copernicusmarine/.copernicusmarine-credentials` ABSENT, no env vars in the
> eval svc). Build all collectors with mock-data fallback now; document the login hook
> (`copernicusmarine login`, then set `COPERNICUS_USERNAME`/`COPERNICUS_PASSWORD` in the
> eval svc environment) so real uo/vo/zos pulls can be switched on in one env change.
>
> **Deploy decision (2026-09-10):** serve at `ev.onlineacademy.com.ly/weather-map`
> (port 5006 Flask route). Future: new subdomain if needed.

## 3. EXPANDED SCOPE (v2 — sea currents + Libyan maritime area + vessel risk)

### 3.1 Sea Surface Currents Layer
- Data: `uo` (eastward), `vo` (northward) from `cmems_mod_med_phy-cur_anfc_4.2km-2D_PT1H-m`.
- Current speed = hypot(uo, vo); direction = atan2(vo, uo).
- Rendering: animated particle flow layer on the map (MapLibre custom layer / canvas particles),
  with direction arrows at coarse grid.
- Coverage: full Mediterranean bbox clipped to Libya EEZ + transit corridor.

### 3.2 Libyan Maritime / Naval Area Layer
- Purpose: monitoring of sea level & currents over **Libya's territorial waters / EEZ**
  and the **central-med transit corridor** (off Tripoli–Zuwara–Sabratha, Benghazi, Derna →
  toward Italy/Malta/Greece) — the zone of recurring boat-vessel incidents/drownings.
- Data: Libya EEZ + 12nm territorial sea polygons.
  - Source: existing `ne` workspace (libya-shp/osm_libya) via GeoServer WMS, plus a static
    GeoJSON EEZ polygon (Marine Regions / Flanders Marine Institute EEZ dataset cached locally).
- Rendering: semi-transparent fill + dashed border, toggle layer.

### 3.3 Vessel-Capsize / Distress Risk Prediction
- Combine per-hourly: wind speed (µ), significant wave height (VHM0), wave period (VTM02),
  sea surface current speed (cur), and sea level anomaly (from closest IOC gauge / zos).
- Risk model (small craft / inflatable / migrant boat hazard):
  - `capsize_risk` thresholds: wave height > 1.5 m, wave period < 7 s (steep chop),
    wind > 10 m/s, current > 0.5 m/s, sea state Douglas scale ≥ 5.
  - Composite risk score 0–1 per bbox grid cell + per coastal zone.
  - Emits: EXTERNAL danger alerts for offshore grid cells, prioritized by proximity to
    known departure points (Tripoli, Zuwara, Sabratha, Benghazi, Tobruk, Derna) and to
    search-localization zones.
- Expose as new eval-svc endpoints:
  - `GET /api/marine/currents?bbox=...&time=...` → grid of uo/vo.
  - `GET /api/marine/ssh?bbox=...` → zos grid.
  - `GET /api/marine/vessel_risk?bbox=...` → composite risk grid + hot cells.
  - `POST /api/marine/vessel_risk/evaluate` → Ollama narrative for hottest cell.
- Background scheduler pulls CMEMS hourly (currents, waves) + daily (zos) for the Libya box;
  stores in PostGIS (new tables `marine_currents`, `marine_ssh`, `vessel_risk`) so the
  frontend reads fast local data instead of hitting CMEMS per request.

## 4. Frontend (new, dynamic)

- MapLibre GL JS v5 (globe or mercator, Libya-centric), dark theme, WebGL wind/current particles.
- Layers (toggle panel + opacity):
  - Base: OSM / GeoServer `ne` Libya vector.
  - Wind particles (OpenWeatherMap gridded or Open-Meteo free tiles).
  - **Current particles + speed heat layer (Copernicus uo/vo)**.
  - **Sea level: IOC gauge markers + zos heatmap**, time series (echarts) on click.
  - **Waves: VHM0/VTM02 marker or heat layer**.
  - **Vessel-capsize risk heat layer + alert markers (new)**.
  - **Libya EEZ / 12nm maritime zone overlay (new)**.
- Sidebar: layer list, legend, city/zone list, alerts feed, "Collect now / Evaluate now" buttons
  (POST to existing `collect`+`evaluate` endpoints), last-updated timestamps.
- Auto-refresh every 5 min; manual time slider for archive extrapolation.
- Served by eval-svc Flask at `/weather-map` and `/weather-map/`.

## 5. Database additions (PostGIS `lrc_ops` or eval svc DB)

```sql
-- marine grids (regular ~4.2km CMEMS grid over Libya box)
CREATE TABLE IF NOT EXISTS marine_currents (
  id SERIAL PRIMARY KEY,
  time TIMESTAMPTZ NOT NULL,
  lat DOUBLE PRECISION NOT NULL,
  lon DOUBLE PRECISION NOT NULL,
  uo DOUBLE PRECISION, vo DOUBLE PRECISION,
  speed DOUBLE PRECISION, direction_deg DOUBLE PRECISION,
  src TEXT DEFAULT 'cmems_med_phy-cur_anfc_4.2km-2D_PT1H-m'
);
CREATE TABLE IF NOT EXISTS marine_ssh (
  id SERIAL PRIMARY KEY,
  time TIMESTAMPTZ NOT NULL,
  lat DOUBLE PRECISION NOT NULL,
  lon DOUBLE PRECISION NOT NULL,
  zos DOUBLE PRECISION,
  src TEXT DEFAULT 'cmems_mod_med_phy-ssh_anfc_4.2km_P1D-m'
);
CREATE TABLE IF NOT EXISTS vessel_risk (
  id SERIAL PRIMARY KEY,
  time TIMESTAMPTZ NOT NULL,
  lat DOUBLE PRECISION NOT NULL,
  lon DOUBLE PRECISION NOT NULL,
  risk_score DOUBLE PRECISION,         -- 0..1 composite
  wave_height DOUBLE PRECISION,
  wave_period DOUBLE PRECISION,
  wind_speed DOUBLE PRECISION,
  current_speed DOUBLE PRECISION,
  sea_level_anomaly DOUBLE PRECISION,
  danger_level TEXT DEFAULT 'LOW',    -- LOW/MEDIUM/HIGH/EXTREME
  cluster_id INT
);
CREATE INDEX IF NOT EXISTS idx_marine_cur_time ON marine_currents(time);
CREATE INDEX IF NOT EXISTS idx_marine_ssh_time ON marine_ssh(time);
CREATE INDEX IF NOT EXISTS idx_vessel_risk_time ON vessel_risk(time);
```

## 6. API Endpoints (new, on eval svc 5006)

```
GET  /api/marine/currents?bbox=25,30,35,34&time=<iso>   → geojson grid uo/vo/speed/dir
GET  /api/marine/ssh?bbox=25,30,35,34&time=<iso>        → geojson grid zos
GET  /api/marine/vessel_risk?bbox=25,30,35,34           → geojson risk + alerts
POST /api/marine/vessel_risk/evaluate                   → Ollama narrative (async job)
GET  /api/marine/zones                                  → Libya EEZ + 12nm + departures GeoJSON
```

## 7. Implementation Phases (updated)

| Phase | Scope | Est. |
|-------|-------|------|
| 1 | New frontend shell + layers (wind, temp, waves, sea level, zones, currents, vessel risk) | 1 wk |
| 2 | Marine collectors: CMEMS currents/ssh hourly+daily into PostGIS; scheduler job | 1 wk |
| 3 | Vessel risk model + alerts + Ollama evaluation endpoint | 3-4 days |
| 4 | Deploy `/weather-map` on ev.onlineacademy.com.ly (cloudflared already routes :5006) | 0.5 day |

## 8. Dependencies / Setup on server

- `pip install copernicusmarine xarray netCDF4` (CLI already present; ensure package importable
  by eval-svc Python, add to requirements).
- **CMEMS credentials** (deferred): on server run
  `copernicusmarine login --username <user> --password <pass>`, then add
  `COPERNICUS_USERNAME`/`COPERNICUS_PASSWORD` to the eval svc env
  (`systemctl edit evaluation-service.service`). Without them collectors use mock fallback.
- `requirements.txt` += maplibre `maplibre-gl`, `maplibre-wind-gl`, `echarts` (frontend CDN).

## 9. Access

- Internal: `http://10.147.18.194:5006/weather-map`
- Public: `https://ev.onlineacademy.com.ly/weather-map` (cloudflared → :5006, no auth)

## 10. Summary

| Aspect | Detail |
|--------|--------|
| Currents | Copernicus MEDSEA hourly uo/vo → particle animation + heat layer |
| Sea level | IOC gauges + CMEMS zos daily heatmap + time series |
| Marine area | Libya EEZ + 12nm polygons; transit corridor focus for rescue support |
| Vessel risk | composite wind+wave+current+SSL model → alerts + Ollama narrative |
| Backend | new `/api/marine/*` endpoints + PostGIS tables, scheduler pulls |
| Frontend | MapLibre GL dark map at `/weather-map`, toggle layers, auto-refresh |
| Hosting | same server, cloudflared tunnel already routes :5006 |