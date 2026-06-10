# Public App - Disaster Management System

Flask application for cPanel shared hosting.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python app.py
```

The app will be available at `http://localhost:5000`

## API Endpoints

### Incidents
- `GET /api/incidents` - Get all incidents
- `POST /api/incidents` - Create a new incident
- `PUT /api/incidents/<id>` - Update an incident

### Teams
- `GET /api/teams` - Get all teams
- `POST /api/teams` - Create a new team
- `PUT /api/teams/<id>` - Update a team

### Routes
- `POST /api/routes/generate` - Generate a route between team and incident
- `GET /api/routes` - Get all routes
- `DELETE /api/routes/<id>` - Delete a route

## Database

SQLite database is automatically created in `database/disaster_ops.db` on first run.

## cPanel Deployment

1. Upload files to `public_html` or subdirectory
2. Set up Python app in cPanel
3. Point to `app.py` as the entry point
4. Configure port (usually provided by cPanel)
