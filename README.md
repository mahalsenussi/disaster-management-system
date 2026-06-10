# Disaster Management System v2

A production-ready, split-architecture disaster management system with geospatial capabilities and OSRM routing integration.

## Architecture

The system is split into two components:

### 1. Public App (cPanel Compatible)
- **Location:** `public_app/`
- **Purpose:** Frontend-facing application for shared hosting
- **Port:** 5000
- **Database:** SQLite (compatible with MySQL via schema_mysql.sql)
- **Features:**
  - Leaflet-based dashboard
  - Incident management
  - Team tracking
  - Route visualization (OSRM or fallback)
  - Auto-refresh every 5 seconds

### 2. Engine Service (Ubuntu Server)
- **Location:** `engine_service/`
- **Purpose:** Heavy processing microservice
- **Port:** 5001
- **Features:**
  - OSRM routing with fallback to straight-line
  - ETA calculation (configurable speed)
  - Batch route processing
  - Nearest team optimization
  - Libya coordinate validation

## Quick Start

### Public App

```bash
cd public_app
pip install -r requirements.txt
python sample_data.py  # Load sample data
python app.py
```

Access at: `http://localhost:5000`

### Engine Service

```bash
cd engine_service
pip install -r requirements.txt
python app.py
```

Access at: `http://localhost:5001`

## API Documentation

### Public App Endpoints

#### Incidents
- `GET /api/incidents` - List all incidents
- `POST /api/incidents` - Create incident
  ```json
  {
    "type": "Fire",
    "severity": "high",
    "lat": 32.8872,
    "lng": 13.1913,
    "status": "open"
  }
  ```
- `PUT /api/incidents/<id>` - Update incident

#### Teams
- `GET /api/teams` - List all teams
- `POST /api/teams` - Create team
  ```json
  {
    "name": "Team Alpha",
    "lat": 32.8800,
    "lng": 13.1900,
    "status": "available"
  }
  ```
- `PUT /api/teams/<id>` - Update team

#### Routes
- `POST /api/routes/generate` - Generate route
  ```json
  {
    "incident_id": 1,
    "team_id": 1
  }
  ```
- `GET /api/routes` - List all routes
- `DELETE /api/routes/<id>` - Delete route

### Engine Service Endpoints

#### Health
- `GET /health` - Service health check

#### Route Generation
- `POST /route` - Generate single route (OSRM with fallback)
  ```json
  {
    "team": {"lat": 32.8872, "lng": 13.1913},
    "incident": {"lat": 32.9000, "lng": 13.2000}
  }
  ```
  **Response:**
  ```json
  {
    "path": [[32.8872, 13.1913], [32.8889, 13.1944], ...],
    "distance": 12.5,
    "duration": 750.0,
    "eta": 12.5,
    "source": "osrm",
    "timestamp": "2026-06-10T10:00:00"
  }
  ```

- `POST /route/batch` - Generate multiple routes
- `POST /route/optimize` - Find nearest team

## OSRM Integration

### Running OSRM Locally (Docker)

The project includes a Docker-based OSRM setup with pre-configured Libya map data.

#### 1. Docker Permission Setup (Ubuntu/Linux)

If you get "permission denied" errors when running Docker commands, add your user to the docker group:

```bash
# Add current user to docker group
sudo usermod -aG docker $USER

# Apply group change (log out and back in, or run:)
newgrp docker

# Verify access
docker ps
```

#### 2. Start OSRM

```bash
cd engine_service/osrm
chmod +x start_osrm.sh
./start_osrm.sh
```

This will:
- Download Libya map data (~73MB) if not present
- Extract and process the OSRM data
- Start the OSRM server on `http://localhost:5000`

#### 3. Verify OSRM is running

```bash
curl "http://localhost:5000/route/v1/driving/13.1913,32.8872;13.2000,32.9000?overview=false"
```

### Manual Docker Setup

If you prefer to run OSRM manually:

```bash
cd engine_service/osrm

# Start OSRM (data will be extracted on first run)
docker compose up -d

# View logs
docker compose logs -f

# Stop OSRM
docker compose down
```

### Using Remote OSRM

The system defaults to the local OSRM server: `http://localhost:5000`

To use a custom OSRM server, set the environment variable:
```bash
export OSRM_URL=http://your-osrm-server:5000
```

### Fallback Configuration

If OSRM is unavailable, the system automatically falls back to straight-line routing using the Haversine formula.

Configure fallback in `engine_service/config.py`:
- `FALLBACK_ENABLED`: Enable/disable fallback (default: True)
- `FALLBACK_SPEED_KMH`: Average speed for ETA (default: 60.0)

## Dashboard Features

- **Fullscreen Map:** Leaflet-based interactive map
- **Incident Markers:** Red circles for active incidents
- **Team Markers:** Blue markers for available teams
- **Route Visualization:** Dashed blue lines for assigned routes
- **Real-time Updates:** Auto-refresh every 5 seconds
- **Team Assignment:** Click incident → select team → generate route
- **Status Indicators:** Online/offline status display

## Deployment

### cPanel (Public App)

1. Upload `public_app/` contents to `public_html/disaster/`
2. Set up Python application in cPanel
3. Configure domain/subdomain
4. Update `ENGINE_API_URL` in `app.py` to point to your Ubuntu server

### Ubuntu (Engine Service)

1. Upload `engine_service/` to server
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure OSRM (optional):
   ```bash
   export OSRM_URL=http://your-osrm-server:5000
   export FALLBACK_ENABLED=true
   ```
4. Create systemd service:
   ```bash
   sudo nano /etc/systemd/system/engine-service.service
   ```
   ```ini
   [Unit]
   Description=Disaster Engine Service
   After=network.target

   [Service]
   User=www-data
   WorkingDirectory=/path/to/engine_service
   Environment="OSRM_URL=http://router.project-osrm.org"
   Environment="FALLBACK_ENABLED=true"
   ExecStart=/usr/bin/python3 app.py
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```
5. Enable and start:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable engine-service
   sudo systemctl start engine-service
   ```

## Sample Data

The `public_app/sample_data.py` script includes:
- 5 sample incidents across Libya
- 5 response teams in different cities
- Locations: Tripoli, Benghazi, Misrata, Sabha, Zuwara

Run with:
```bash
python sample_data.py
```

## Configuration

### Public App
Edit `public_app/app.py` or set environment variables:
- `DATABASE`: SQLite database path
- `ENGINE_API_URL`: External engine service URL (default: http://localhost:5001/route)

### Engine Service
Edit `engine_service/config.py` or set environment variables:
- `OSRM_URL`: OSRM server URL (default: http://router.project-osrm.org)
- `OSRM_TIMEOUT`: Request timeout in seconds (default: 30)
- `FALLBACK_ENABLED`: Enable straight-line fallback (default: True)
- `FALLBACK_SPEED_KMH`: Average speed for ETA (default: 60.0)

## Database Schema

### SQLite (default)
Use `public_app/schema.sql` for SQLite databases.

### MySQL (production)
Use `public_app/schema_mysql.sql` for MySQL deployment.

Both schemas are compatible and use:
- Generic SQL syntax
- INTEGER PRIMARY KEY AUTOINCREMENT
- TEXT for JSON storage
- No SQLite-specific features

## Project Structure

```
v2/
├── public_app/
│   ├── app.py                          # Flask app (cPanel compatible)
│   ├── schema.sql                      # SQLite schema
│   ├── schema_mysql.sql                # MySQL schema
│   ├── requirements.txt                # Dependencies
│   ├── sample_data.py                  # Sample data loader
│   ├── database/                       # SQLite database dir
│   └── templates/
│       └── dashboard.html              # Leaflet dashboard
├── engine_service/
│   ├── app.py                          # Flask microservice
│   ├── config.py                       # Configuration
│   ├── requirements.txt                # Dependencies
│   ├── services/
│   │   └── osrm_service.py             # OSRM routing service
│   ├── modules/
│   │   ├── __init__.py
│   │   ├── geo_utils.py                # Geographic calculations
│   │   ├── incident.py                 # Incident management
│   │   ├── location.py                 # Location utilities
│   │   └── routing.py                  # Route manager
│   └── osrm/                           # Local OSRM setup
│       ├── docker-compose.yml          # OSRM Docker configuration
│       ├── start_osrm.sh               # OSRM startup script
│       └── data/                       # OSRM map data
│           └── libya-latest.osm.pbf    # Libya OpenStreetMap data
└── README.md                           # This file
```

## Technology Stack

- **Backend:** Flask 3.0.0
- **Frontend:** HTML + JavaScript (no frameworks)
- **Maps:** Leaflet 1.9.4
- **Routing:** OSRM (with Haversine fallback)
- **Database:** SQLite (MySQL compatible)
- **HTTP:** requests library

## Migration from v1

This v2 system integrates and refactors working modules from v1:

### Preserved v1 Logic
- **OSRM routing** from `route_test/modules/osrm_client.py`
- **Geographic calculations** (Haversine, bearing, midpoint)
- **Incident management** patterns from `modules/disaster`
- **Location utilities** from `modules/location`
- **Team tracking** with GPS data

### Key Improvements
- Split architecture for better scalability
- OSRM with automatic fallback
- Database schema compatible with both SQLite and MySQL
- Modular structure for easier maintenance
- Environment-based configuration

## Troubleshooting

### OSRM Connection Issues
If OSRM fails to connect:
1. Check `OSRM_URL` in config
2. Verify OSRM server is running
3. System will automatically use fallback
4. Check logs: `tail -f engine_service.log`

### Database Errors
For SQLite:
- Ensure `database/` directory exists
- Check file permissions

For MySQL:
- Use `schema_mysql.sql` to create tables
- Update connection string in app.py

### Route Generation Fails
1. Verify engine service is running
2. Check `ENGINE_API_URL` in public app
3. Test engine service: `curl http://localhost:5001/health`
4. Check engine service logs

## License

© 2026 Libyan Red Crescent Emergency Intelligence System
