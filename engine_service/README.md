# Engine Service - Route Generation Microservice

Flask microservice for route generation and optimization.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the service:
```bash
python app.py
```

The service will be available at `http://0.0.0.0:5001`

## API Endpoints

### Health Check
- `GET /health` - Service health check

### Route Generation
- `POST /route` - Generate a single route between team and incident

**Request:**
```json
{
  "team": { "lat": 32.8872, "lng": 13.1913 },
  "incident": { "lat": 32.9000, "lng": 13.2000 }
}
```

**Response:**
```json
{
  "path": [[32.8872, 13.1913], [32.8889, 13.1944], ...],
  "distance": 12.5,
  "eta": 12.5,
  "speed_kmh": 60.0,
  "timestamp": "2026-06-10T09:00:00"
}
```

### Batch Route Generation
- `POST /route/batch` - Generate multiple routes at once

### Route Optimization
- `POST /route/optimize` - Find the nearest team to an incident

## Features

- Haversine distance calculation
- ETA estimation (assumes 60 km/h average speed)
- Straight-line path generation
- Batch processing support
- Nearest team optimization

## Ubuntu Deployment

1. Copy files to server
2. Create systemd service:
```ini
[Unit]
Description=Disaster Engine Service
After=network.target

[Service]
User=www-data
WorkingDirectory=/path/to/engine_service
ExecStart=/usr/bin/python3 app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

3. Enable and start:
```bash
sudo systemctl enable engine-service
sudo systemctl start engine-service
```
