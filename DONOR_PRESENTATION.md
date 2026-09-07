# Libyan Red Crescent Emergency Intelligence System
## Presentation for Potential Donors

---

## Opening — The Why

Good afternoon. I am here to present a project that is not theoretical. It is not a proposal sitting in a drawer. It is live, it is operational, and it is already saving lives in Libya.

Libya sits at the frontline of a climate emergency that the world is not watching closely enough. In September 2023, when Storm Daniel struck the northeast coast, two dams collapsed outside Derna. Entire neighborhoods were swept into the Mediterranean. Over 11,000 people died. Twenty thousand more were injured. The true number may never be known. First responders had no early warning system. They had no real-time team tracking. They had no predictive tools to tell them where the next breach would happen. They were working blind.

We built this system so that never happens again.

---

## What This System Does

This is the Libyan Red Crescent Emergency Intelligence System — a fully integrated, multi-component platform that spans the entire disaster response lifecycle: prediction, detection, coordination, and field execution.

### 1. The AI Early Warning Engine

At the heart of the system lives a hybrid machine learning model that fuses five distinct data sources into a single calibrated risk score — a number between 0 and 1 that tells responders how dangerous a given location is, right now.

**Data sources:**
- Real-time weather from OpenWeatherMap
- Marine conditions from Copernicus Marine Service (wave height, sea level anomalies, wind speed)
- News aggregation scanning Arabic and international sources for keyword spikes
- Historical disaster records from EM-DAT international database
- Geographic vulnerability factors (elevation, coastal proximity)

**Model architecture:**
- **XGBoost Classifier** — 50% weight (isotonic calibrated for realistic confidence)
- **Isolation Forest** — 20% weight (anomaly detection)
- **Trend Analysis** — 20% weight (time-series patterns)
- **Geographic Risk** — 10% weight (coastal flooding, elevation vulnerability)

**Performance (55,023 training samples):**
- Accuracy: 99%
- F1-Score: 97%
- Disaster Recall: 100% — never missed a disaster event in testing

**Alert classification — five actionable levels:**

| Level | Threshold | Action |
|---|---|---|
| HIGH_CONFIRMED | Risk >= 0.7, Confidence > 0.8 | Send response team |
| HIGH_UNCERTAIN | Risk >= 0.7, Confidence <= 0.8 | Monitor closely |
| MEDIUM_CONFIRMED | Risk >= 0.4, Confidence > 0.8 | Prepare resources |
| MEDIUM_UNCERTAIN | Risk >= 0.4, Confidence <= 0.8 | Continue monitoring |
| LOW | Risk < 0.4 | Normal operations |

### 2. The Routing Engine

Integrates OSRM (OpenStreetMap Routing Machine) with a full Libyan road network extracted from OpenStreetMap data. Computes optimal driving routes, ETA with configurable speed assumptions, and supports road block avoidance with automatic detour waypoint generation. When OSRM is unavailable, the system falls back to Haversine great-circle routing so it never goes dark.

### 3. The Operations Dashboard

Real-time Leaflet-based dashboard served from a cPanel-compatible Flask backend. Refreshes every 5 seconds. Incident markers in red. Team markers in blue. Route visualization with dashed lines. Role-based access control with geographic branch filtering — a dispatcher in Tripoli sees only Tripoli incidents.

### 4. The Field Mobile Application

Flutter-based Android app for emergency responders:
- Live GPS tracking
- Turn-by-turn navigation powered by OSRM engine
- Automatic rerouting on >80m deviation
- Full offline resilience: queues GPS updates and retries when connectivity returns
- Color-coded markers for team status and incident priority
- QR code login for rapid deployment

### 5. The Dispatcher Mobile Application

Second Flutter application with Arabic-language UI. Supervisors manage team assignments, assign incidents, visualize routes, and coordinate across 15+ Libyan cities from mobile devices. Token-based authentication.

### 6. The Medical AI Chatbot

Ollama-powered dual-model system:
- **LRC Helper** — RAG-based knowledge assistant grounded in Red Crescent protocols
- **Medical AI** — analyzes uploaded X-rays, CT scans, and ultrasound images using medgemma1.5 and cloud models for mass-casualty triage

---

## Architecture & Deployment

Architected from day one for the infrastructure realities of Libya.

**Split architecture:**
- Lightweight Flask frontend on cPanel shared hosting (local infrastructure)
- Heavier backend (OSRM engine, ML pipeline, evaluation service) on Ubuntu server inside Libya at 10.1.30.100
- Managed by systemd services, synced via SCP scripts
- Fronted by Cloudflare tunnels for external access
- Systemd `disaster-management.service` brings everything up on boot

**Live deployment:**
- Public dashboard: `ev.onlineacademy.com.ly`
- OSRM server in Docker with 73MB Libya OSM extract
- Full stack: Flask, SQLite, Leaflet, XGBoost, OSRM, Flutter
- Chosen to minimize external dependencies and maximize local hardware capability

---

## Data Sources & Partnerships

| Source | Provider | Data Type |
|---|---|---|
| Copernicus Marine Service | European Union Earth observation | Sea state, Mediterranean |
| OpenWeatherMap | Weather service | Atmospheric conditions, Libyan cities |
| NewsAPI / GNews | News aggregation | Arabic/international news signals |
| EM-DAT | CRED, Université Catholique de Louvain | Historical disaster records |
| OpenStreetMap | Community-sourced | Road network data |

---

## Current Status

**This is not a prototype. This is an MVP transitioning to production.**

- 19,000+ lines of additions in latest integration commit
- Services deployed and running on Libyan infrastructure
- ML model trained and producing predictions with verified metrics
- Tests exist for core prediction pipeline, data collection, and field app
- Sync and deployment pipeline scripted and repeatable
- Built by a small team under severe constraints (intermittent power, limited bandwidth, evolving requirements)

---

## Areas for Donor Support

### 1. Infrastructure Hardening
Migrate SQLite to PostgreSQL/MySQL for concurrent multi-user access. Add API authentication hardening, rate limiting, audit logging. Implement CI/CD and automated testing.

### 2. Satellite Communications
The single biggest vulnerability is the network. Portable satellite backhaul (Starlink or BGAN) deployed alongside server infrastructure would make the system genuinely independent of terrestrial networks.

### 3. Formal Testing & Quality Assurance
Comprehensive unit, integration, load, and security tests to harden the system for production at national scale.

### 4. Expanded Coverage & Training
Scale from 15+ cities to all Libyan municipalities. Create Arabic training materials and conduct branch-level workshops for Red Crescent personnel.

### 5. Hardware for Field Teams
Many volunteer responders lack smartphones capable of running the Flutter field app. Ruggedized devices pre-loaded with the app would remove the single largest adoption barrier.

### 6. Continuous Model Improvement
Real-world feedback collection is active but low-volume. A data engineering role dedicated to improving training data quality, incorporating new sources, and retraining on a regular cadence.

---

## Closing — The Vision

Here is what I want you to imagine.

It is November 2027. A low-pressure system is forming over the Ionian Sea. The marine data stream shows anomalous sea level rise off the Libyan coast. The weather API shows a sharp pressure differential. The news scanner picks up reports of unusual cloud cover. None of this is visible to the human eye yet.

But the hybrid engine computes a risk score of 0.82 for Derna. HIGH_CONFIRMED. An alert fires on the dashboard. The dispatcher sees an early warning flag. She assigns a team through the mobile app. They receive turn-by-turn navigation to a pre-staged position. Three hours later, the storm makes landfall. The wadis flood. But no one dies. Because the responders were already in place.

That is what we are building. That is what we are asking you to support.

---

**Thank you.**
