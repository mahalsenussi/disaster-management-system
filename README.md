# Disaster Management System v2

A split-architecture emergency intelligence platform for Libya: real-time **weather, coastal & marine monitoring**, **forecast and historical climate maps**, **news intelligence**, **AI disaster-risk prediction**, **OSRM routing**, and **field operations** — all exposed as lightweight Flask microservices.

## System Overview — Microservices

| Service | Directory | Port | Description |
|---|---|---|---|
| **Evaluation Service** | `evaluation_service/` | 5006 | Core monitoring platform: weather, coastal, marine, forecast, historical, news, danger (ML), chatbot & async analysis |
| **Engine Service** | `engine_service/` | 5002 | OSRM route generation / optimization microservice with straight-line fallback |
| **Prediction / Alert API** | `ml/` | 5002 | Disaster-risk inference API (hybrid ML risk engine) |
| **Public (Operations) App** | `public_app/` | 5000 | cPanel-compatible web dashboard: incidents, teams, routes, RBAC |
| **Field Mobile App** | `field_app/` | — | Flutter app for field response teams (GPS, incidents, routing) |
| **Mobile App (legacy)** | `basic_flutter/` | — | Earlier Flutter variant with multi-platform targets |

```
                        ┌──────────────────────────────────────┐
                        │          Evaluation Service          │  :5006
                        │   weather · coastal · marine          │
                        │   forecast · historical · news        │
                        │   danger(ML) · chatbot · analysis     │
                        └───────┬──────────────▲────────────────┘
                                │ fetch        │ collect/evaluate
                  ┌─────────────▼──┐           │
                  │ Open-Meteo ● CMEMS ●      │
                  │ EM-DAT ● News APIs         │
                  └────────────────┘           │
   ┌───────────────────┬───────────────────────┼────────────┐
   ▼                   ▼                       ▼            ▼
┌────────────┐   ┌───────────────┐      ┌───────────┐   ┌──────────┐
│ Public App │◄──│ Engine (OSRM) │      │ ML Risk   │   │ Field App│
│   :5000    │   │    :5002/5003 │      │ :5002     │   │ Flutter  │
└────────────┘   └───────────────┘      └───────────┘   └──────────┘
```

## Microservice Details

### 1. Evaluation Service — `evaluation_service/` (port **5006**)
The main platform. Flask app with per-domain SQLite databases in `evaluation_service/database/`
(`weather.db`, `coastal.db`, `marine.db`, `forecast.db`, `historical.db`, `news.db`,
`danger.db`, `knowledge_base.db`).

**Modules** (`evaluation_service/modules/`):

| Module | Purpose | Data source |
|---|---|---|
| `weather` | Per-city current weather, evaluation risk scores, history | Open-Meteo |
| `coastal` | Coastal location hazard monitoring & evaluation | Open-Meteo |
| `marine` | Sea currents, sea-surface height, vessel risk — plus **deep-sea waves** from Open-Meteo; land-masked to sea cells | CMEMS (Copernicus), Open-Meteo |
| `forecast` | 17 Libyan cities: 7-day forecast, **ERA5 historical archive**, climate normals & anomalies, and a **0.5° gridded snapshot** (temp/precip/cloud/wind × 48 h) | Open-Meteo archive + forecast |
| `historical` | EM-DAT historical disasters: import, patterns, map data | EM-DAT |
| `news` | Multi-source news aggregation & evaluation | News APIs |
| `danger` | City-level disaster risk prediction, alerts, feedback loop | ML models |
| `chatbot` | General, medical & knowledge-base chat | — |
| `analysis` | Async summarization / evaluation (optional Ollama) via job queue | — |

**Web pages** (`templates/`):
- `/` — operational dashboard
- `/weather-map` — coastal & marine monitor (OSM streets ⇄ Sentinel-2 satellite toggle, deep-sea wave layer)
- `/forecast` — windy / Zoom-Earth style page: city picker + map-click selection, forecast / historical / records tabs, time-playback bar with **clouds, temperature, precipitation** layers and **static wind arrows**, Chart.js history & anomaly charts

**Key API groups** (all under `/api/…`, `GET` to read / `POST` to collect or evaluate):
`/weather`, `/coastal`, `/marine/currents|ssh|risk|waves/deepsea|zones`,
`/forecast/<city>[/history|/climate|/anomaly]`, `/forecast/grid`,
`/news`, `/danger/<city>`, `/historical/disasters`, `/chatbot/*`, `/knowledge-base/*`,
`/analysis/summarize`, `/jobs/<id>`, `/health`.

**Scheduler & queue** — `evaluation_service/scheduler/master_scheduler.py` registers periodic
collectors (`weather_<city>`, `coastal_<city>`, `marine_currents/ssh/risk/deepsea_waves`,
`forecast_<city>`, `forecast_grid`, `news_<category>`) on an hourly cadence; `queue/` provides
a background task worker for async analysis jobs.

### 2. Engine Service — `engine_service/` (port **5002**)
Route-generation microservice:
- `GET /health`, `POST /route`, `POST /route/batch`, `POST /route/optimize`
- OSRM with automatic Haversine fallback (`FALLBACK_ENABLED`, `FALLBACK_SPEED_KMH`)
- Libya-coordinate validation
- Local OSRM via Docker (`engine_service/osrm/`, pre-baked Libya OSM extract)

### 3. Prediction / Alert API — `ml/`
Hybrid risk engine (`risk_engine_v2.py`) combining XGBoost, Isolation Forest anomaly
detection, trend/time-series analysis and geographic risk; `alert_api.py` exposes the
REST API (port 5002). EM-DAT processor + feature builder included. See `ml/README.md`.

### 4. Public (Operations) App — `public_app/` (port **5000**)
cPanel-compatible Flask dashboard: incident management, team tracking, route visualization,
RBAC (`migrate_rbac.py`), Leaflet map with 5 s auto-refresh. SQLite by default,
MySQL-compatible via `schema_mysql.sql`.

### 5. Field Mobile Apps (Flutter)
- `field_app/` — current field operations app: login/qr auth, real-time GPS, active
  incidents, OSRM routing to assignments (`lib/screens`, `lib/services`).
- `basic_flutter/` — earlier Flutter build with Android/iOS/web/desktop targets.

## Project Structure

```
v2/
├── evaluation_service/          # Main monitoring platform (:5006)
│   ├── app.py                   # Flask app + routes + scheduler bootstrap
│   ├── modules/                 # weather, coastal, marine, forecast,
│   │                            #   historical, news, danger, chatbot, analysis
│   ├── scheduler/               # master_scheduler (hourly collectors)
│   ├── queue/                   # async task queue + worker
│   ├── core/                    # logger, cache, auth, jobs, ollama
│   ├── repositories/            # shared SQLite helpers
│   ├── database/                # one SQLite DB per domain
│   ├── services/  scripts/  data/
│   └── templates/               # dashboard.html, weather_map.html, forecast.html
├── engine_service/              # OSRM routing microservice (:5002)
│   ├── app.py  config.py  services/osrm_service.py
│   └── osrm/                    # docker-compose + libya-latest.osm.pbf
├── public_app/                  # Web dashboard (:5000)
│   ├── app.py  auth.py  sample_data.py
│   ├── schema.sql  schema_mysql.sql
│   └── templates/  static/  database/
├── ml/                          # risk_engine_v2, alert_api.py, emdat_processor.py
├── field_app/                   # Flutter field app
├── basic_flutter/               # Flutter legacy app
├── start_all.sh                 # boot evaluation service (+ .env)
├── disaster-management.service  # systemd unit
└── README.md
```

## Quick Start

### Evaluation Service (:5006)
```bash
cd evaluation_service
pip install -r requirements.txt
python app.py          # or via start_all.sh (uses .venv)
```
Access at `http://localhost:5006` · `/weather-map` · `/forecast`

### Engine Service (:5002)
```bash
cd engine_service
pip install -r requirements.txt
python app.py
```
Access at `http://localhost:5002` (health: `curl localhost:5002/health`)

### Public App (:5000)
```bash
cd public_app
pip install -r requirements.txt
python sample_data.py   # load sample incidents/teams
python app.py
```
Access at `http://localhost:5000`

### ML Alert API (:5002)
```bash
cd ml
python alert_api.py
```

### OSRM (Docker)
```bash
cd engine_service/osrm
chmod +x start_osrm.sh && ./start_osrm.sh
curl "http://localhost:5000/route/v1/driving/13.1913,32.8872;13.2000,32.9000?overview=false"
```

## Configuration

Create `.env` from `.env.example` (gitignored) with API keys:

```
OPENWEATHER_API_KEY, NEWSAPI_KEY, GNEWS_API_KEY, WORLDNEWS_API_KEY,
CURRENTS_API_KEY, COPERNICUS_USERNAME, COPERNICUS_PASSWORD
```

| Variable | Default | Used by |
|---|---|---|
| `EVALUATION_PORT` | 5006 | Evaluation service |
| `ENGINE_PORT` / `PORT` | 5002 | Engine service |
| `OSRM_URL` | `http://localhost:5000` | Engine routing |
| `FALLBACK_ENABLED` | true | Engine straight-line fallback |
| `FALLBACK_SPEED_KMH` | 60.0 | Engine ETA fallback |

> **Open-Meteo** (weather, forecast, ERA5 archive, deep-sea waves, marine) requires **no API key**.
> **CMEMS** (currents / sea-surface height) needs Copernicus credentials. Batch requests are
> chunked (~250 coordinates per request) with retry/backoff on rate limits.

## Deployment

- **systemd:** `disaster-management.service` runs `start_all.sh` (loads `.env`, activates
  `.venv`, starts the evaluation service). Restart with
  `systemctl restart disaster-management`.
- **Deployment:** local deployment scripts (`sync_to_remote.sh`, `setup_services.sh`) are
  intentionally **not** published — they contain environment-specific hosts and credentials.
- **cPanel (Public App):** upload `public_app/` to `public_html/disaster/`, configure the
  Python app, and point `ENGINE_API_URL` at the engine service.

## Technology Stack

- **Backend:** Flask 3.0, SQLite (MySQL-compatible schemas for public app)
- **Frontend:** HTML + vanilla JS, Leaflet, MapLibre GL JS, Chart.js
- **Data:** Open-Meteo (forecast / archive / marine), CMEMS (Copernicus), EM-DAT, news APIs
- **Routing:** OSRM with Haversine fallback
- **ML:** XGBoost, Isolation Forest, scikit-learn time-series features
- **Mobile:** Flutter (field_app)
- **Async:** background queue + APScheduler-style `master_scheduler`

## License

**Copyright © 2026 Libyan Red Crescent (LRC) — all rights reserved.**

Free to use, copy, study, modify and distribute for **humanitarian training, drills, exercises
and emergency-management education only**. Commercial use, military/weapons use, and any
suggestion of official LRC/IFRC endorsement require prior written permission.

Full terms: see [`LICENSE`](LICENSE). Third-party dependencies keep their own licences.
