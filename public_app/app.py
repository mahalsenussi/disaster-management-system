#!/usr/bin/env python3
"""
Public Flask App for Disaster Management System
Designed for cPanel shared hosting
"""

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
import requests
import json
from datetime import datetime
import os

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configuration
DATABASE = os.path.join(os.path.dirname(__file__), 'database', 'disaster_ops.db')
ENGINE_API_URL = os.environ.get('ENGINE_API_URL', 'http://localhost:5001/route')

# Ensure database directory exists
os.makedirs(os.path.dirname(DATABASE), exist_ok=True)

# Database initialization
def init_db():
    """Initialize SQLite database with required tables using new schema."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Incidents table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            severity TEXT NOT NULL,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            status TEXT DEFAULT 'open',
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Teams table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            status TEXT DEFAULT 'available',
            color TEXT DEFAULT '#007bff',
            icon TEXT DEFAULT '🚑',
            battery_level INTEGER DEFAULT 100,
            speed REAL DEFAULT 0.0,
            heading REAL DEFAULT 0.0,
            gps_enabled INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Routes table (updated schema)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id INTEGER NOT NULL,
            team_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            distance REAL NOT NULL,
            duration REAL NOT NULL,
            status TEXT DEFAULT 'active',
            source TEXT DEFAULT 'osrm',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (incident_id) REFERENCES incidents(id),
            FOREIGN KEY (team_id) REFERENCES teams(id)
        )
    ''')
    
    # Points table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_teams_status ON teams(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_routes_incident ON routes(incident_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_routes_team ON routes(team_id)')
    
    conn.commit()
    conn.close()

def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# Validation Functions

def validate_coordinates(lat, lng):
    """Validate latitude and longitude coordinates."""
    try:
        lat = float(lat)
        lng = float(lng)
        if not (-90 <= lat <= 90):
            return False, "Latitude must be between -90 and 90"
        if not (-180 <= lng <= 180):
            return False, "Longitude must be between -180 and 180"
        return True, None
    except (ValueError, TypeError):
        return False, "Invalid coordinates format"

def validate_severity(severity):
    """Validate severity value (1-5)."""
    try:
        severity = int(severity)
        if not (1 <= severity <= 5):
            return False, "Severity must be between 1 and 5"
        return True, None
    except (ValueError, TypeError):
        return False, "Invalid severity format"

# API Routes

@app.route('/')
def index():
    """Serve the dashboard."""
    return render_template('dashboard.html')

@app.route('/dashboard')
def dashboard():
    """Serve the dashboard."""
    return render_template('dashboard.html')

@app.route('/api/incidents', methods=['GET'])
def get_incidents():
    """Get all incidents."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM incidents ORDER BY created_at DESC')
    incidents = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(incidents)

@app.route('/api/incidents', methods=['POST'])
def create_incident():
    """Create a new incident with validation."""
    data = request.get_json()
    
    # Validate required fields
    if not data.get('type'):
        return jsonify({'error': 'Incident type is required'}), 400
    
    if not data.get('severity'):
        return jsonify({'error': 'Severity is required'}), 400
    
    # Validate severity
    valid_severity, severity_error = validate_severity(data.get('severity'))
    if not valid_severity:
        return jsonify({'error': severity_error}), 400
    
    # Validate coordinates
    valid_coords, coords_error = validate_coordinates(data.get('lat'), data.get('lng'))
    if not valid_coords:
        return jsonify({'error': coords_error}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO incidents (type, severity, lat, lng, status)
        VALUES (?, ?, ?, ?, ?)
    ''', (
        data.get('type'),
        str(data.get('severity')),
        float(data.get('lat')),
        float(data.get('lng')),
        'active'
    ))
    incident_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({'id': incident_id, 'message': 'Incident created successfully'}), 201

@app.route('/api/incidents/<int:incident_id>', methods=['PUT'])
def update_incident(incident_id):
    """Update an incident."""
    data = request.get_json()
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE incidents 
        SET type = ?, severity = ?, lat = ?, lng = ?, status = ?, updated_at = ?
        WHERE id = ?
    ''', (
        data.get('type'),
        data.get('severity'),
        data.get('lat'),
        data.get('lng'),
        data.get('status'),
        datetime.now().isoformat(),
        incident_id
    ))
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Incident updated successfully'})

@app.route('/api/incidents/<int:incident_id>', methods=['PATCH'])
def patch_incident(incident_id):
    """Partially update an incident (severity, status, and assigned_team_id)."""
    data = request.get_json()
    
    updates = []
    values = []
    
    if 'severity' in data:
        valid_severity, severity_error = validate_severity(data.get('severity'))
        if not valid_severity:
            return jsonify({'error': severity_error}), 400
        updates.append('severity = ?')
        values.append(str(data.get('severity')))
    
    if 'status' in data:
        allowed_statuses = ['active', 'assigned', 'resolved']
        if data.get('status') not in allowed_statuses:
            return jsonify({'error': f'Invalid status. Allowed: {", ".join(allowed_statuses)}'}), 400
        updates.append('status = ?')
        values.append(data.get('status'))
    
    if 'assigned_team_id' in data:
        updates.append('assigned_team_id = ?')
        values.append(data.get('assigned_team_id'))
    
    if 'type' in data:
        updates.append('type = ?')
        values.append(data.get('type'))
    
    if not updates:
        return jsonify({'error': 'No valid fields to update'}), 400
    
    values.append(datetime.now().isoformat())
    values.append(incident_id)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(f'''
        UPDATE incidents 
        SET {", ".join(updates)}, updated_at = ?
        WHERE id = ?
    ''', values)
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Incident updated successfully'})

@app.route('/api/incidents/<int:incident_id>', methods=['DELETE'])
def delete_incident(incident_id):
    """Delete an incident and its related routes."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Delete related routes first
    cursor.execute('DELETE FROM routes WHERE incident_id = ?', (incident_id,))
    
    # Delete incident
    cursor.execute('DELETE FROM incidents WHERE id = ?', (incident_id,))
    
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Incident and related routes deleted successfully'})

@app.route('/api/teams', methods=['GET'])
def get_teams():
    """Get all teams with computed GPS state."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM teams ORDER BY name')
    teams = []
    
    for row in cursor.fetchall():
        team = dict(row)
        
        # Compute GPS state (read-only, no auto-fallback)
        if team.get('gps_enabled') and team.get('last_updated'):
            last_update = datetime.fromisoformat(team['last_updated'].replace('Z', '+00:00'))
            now = datetime.now(last_update.tzinfo)
            diff_seconds = (now - last_update).total_seconds()
            
            if diff_seconds < 15:
                team['gps_state'] = 'gps_active'
            elif diff_seconds < 60:
                team['gps_state'] = 'gps_lost'
            else:
                # GPS enabled but stale - show as gps_lost, don't auto-disable
                team['gps_state'] = 'gps_lost'
        else:
            team['gps_state'] = 'manual'
        
        teams.append(team)
    
    conn.close()
    return jsonify(teams)

@app.route('/api/teams', methods=['POST'])
def create_team():
    """Create a new team with validation."""
    data = request.get_json()
    
    # Validate required fields
    if not data.get('name'):
        return jsonify({'error': 'Team name is required'}), 400
    
    # Validate coordinates
    valid_coords, coords_error = validate_coordinates(data.get('lat'), data.get('lng'))
    if not valid_coords:
        return jsonify({'error': coords_error}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO teams (name, lat, lng, status, color, icon, battery_level, speed, heading, gps_enabled, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('name'),
        float(data.get('lat')),
        float(data.get('lng')),
        data.get('status', 'available'),
        data.get('color', '#3498db'),
        data.get('icon', '🚑'),
        data.get('battery_level', 100),
        data.get('speed', 0.0),
        data.get('heading', 0.0),
        data.get('gps_enabled', 0),
        datetime.now().isoformat()
    ))
    team_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({'id': team_id, 'message': 'Team created successfully'}), 201

@app.route('/api/teams/<int:team_id>', methods=['PUT'])
def update_team(team_id):
    """Update a team."""
    data = request.get_json()
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE teams 
        SET name = ?, lat = ?, lng = ?, status = ?, updated_at = ?
        WHERE id = ?
    ''', (
        data.get('name'),
        data.get('lat'),
        data.get('lng'),
        data.get('status'),
        datetime.now().isoformat(),
        team_id
    ))
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Team updated successfully'})

@app.route('/api/teams/<int:team_id>', methods=['PATCH'])
def patch_team(team_id):
    """Partially update a team (status, location, gps_enabled, color, icon)."""
    data = request.get_json()
    
    updates = []
    values = []
    
    if 'lat' in data or 'lng' in data:
        lat = data.get('lat')
        lng = data.get('lng')
        valid_coords, coords_error = validate_coordinates(lat, lng)
        if not valid_coords:
            return jsonify({'error': coords_error}), 400
        if lat is not None:
            updates.append('lat = ?')
            values.append(float(lat))
        if lng is not None:
            updates.append('lng = ?')
            values.append(float(lng))
    
    if 'status' in data:
        allowed_statuses = ['available', 'deployed', 'busy', 'offline']
        if data.get('status') not in allowed_statuses:
            return jsonify({'error': f'Invalid status. Allowed: {", ".join(allowed_statuses)}'}), 400
        updates.append('status = ?')
        values.append(data.get('status'))
    
    if 'gps_enabled' in data:
        gps_enabled = data.get('gps_enabled')
        # Handle string "1"/"0" from frontend
        if isinstance(gps_enabled, str):
            gps_enabled = int(gps_enabled)
        if not isinstance(gps_enabled, (int, bool)):
            return jsonify({'error': 'gps_enabled must be a boolean or integer'}), 400
        updates.append('gps_enabled = ?')
        values.append(1 if gps_enabled else 0)
    
    if 'color' in data:
        updates.append('color = ?')
        values.append(data.get('color'))
    
    if 'icon' in data:
        updates.append('icon = ?')
        values.append(data.get('icon'))
    
    if 'name' in data:
        updates.append('name = ?')
        values.append(data.get('name'))
    
    if not updates:
        return jsonify({'error': 'No valid fields to update'}), 400
    
    values.append(datetime.now().isoformat())
    values.append(team_id)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(f'''
        UPDATE teams 
        SET {", ".join(updates)}, updated_at = ?
        WHERE id = ?
    ''', values)
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Team updated successfully'})

@app.route('/api/teams/<int:team_id>', methods=['DELETE'])
def delete_team(team_id):
    """Delete a team and its related routes."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Delete related routes first
    cursor.execute('DELETE FROM routes WHERE team_id = ?', (team_id,))
    
    # Delete team
    cursor.execute('DELETE FROM teams WHERE id = ?', (team_id,))
    
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Team and related routes deleted successfully'})

# GPS Location Update Endpoint

@app.route('/api/teams/location', methods=['POST'])
def update_team_location():
    """Update team location via GPS tracking."""
    data = request.get_json()
    
    # Validate required fields
    team_id = data.get('team_id')
    lat = data.get('lat')
    lng = data.get('lng')
    
    if not team_id:
        return jsonify({'error': 'team_id is required'}), 400
    
    if lat is None or lng is None:
        return jsonify({'error': 'lat and lng are required'}), 400
    
    # Validate coordinates
    valid_coords, coords_error = validate_coordinates(lat, lng)
    if not valid_coords:
        return jsonify({'error': coords_error}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if team exists and has GPS enabled
    cursor.execute('SELECT id, gps_enabled FROM teams WHERE id = ?', (team_id,))
    team = cursor.fetchone()
    
    if not team:
        conn.close()
        return jsonify({'error': 'Team not found'}), 404
    
    # Check if GPS is enabled
    gps_enabled = team[1] if team[1] else 0
    if not gps_enabled:
        conn.close()
        return jsonify({'error': 'GPS tracking is not enabled for this team'}), 403
    
    # Update location and last_updated timestamp
    cursor.execute('''
        UPDATE teams 
        SET lat = ?, lng = ?, last_updated = ?, updated_at = ?
        WHERE id = ?
    ''', (
        float(lat),
        float(lng),
        datetime.now().isoformat(),
        datetime.now().isoformat(),
        team_id
    ))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'message': 'Location updated successfully',
        'team_id': team_id
    })

# Points endpoints

@app.route('/api/points', methods=['GET'])
def get_points():
    """Get all points."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM points ORDER BY name')
    points = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(points)

@app.route('/api/points', methods=['POST'])
def create_point():
    """Create a new point with validation."""
    data = request.get_json()
    
    # Validate required fields
    if not data.get('name'):
        return jsonify({'error': 'Point name is required'}), 400
    
    if not data.get('type'):
        return jsonify({'error': 'Point type is required'}), 400
    
    # Validate coordinates
    valid_coords, coords_error = validate_coordinates(data.get('lat'), data.get('lng'))
    if not valid_coords:
        return jsonify({'error': coords_error}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO points (name, type, lat, lng)
        VALUES (?, ?, ?, ?)
    ''', (
        data.get('name'),
        data.get('type'),
        float(data.get('lat')),
        float(data.get('lng'))
    ))
    point_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({'id': point_id, 'message': 'Point created successfully'}), 201

@app.route('/api/points/<int:point_id>', methods=['DELETE'])
def delete_point(point_id):
    """Delete a point."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM points WHERE id = ?', (point_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Point deleted successfully'})

@app.route('/api/points/<int:point_id>', methods=['PATCH'])
def update_point(point_id):
    """Update a point."""
    data = request.get_json()
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if point exists
    cursor.execute('SELECT id FROM points WHERE id = ?', (point_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Point not found'}), 404
    
    # Build update query dynamically based on provided fields
    update_fields = []
    update_values = []
    
    if data.get('name'):
        update_fields.append('name = ?')
        update_values.append(data.get('name'))
    
    if data.get('type'):
        update_fields.append('type = ?')
        update_values.append(data.get('type'))
    
    if data.get('lat') is not None:
        update_fields.append('lat = ?')
        update_values.append(float(data.get('lat')))
    
    if data.get('lng') is not None:
        update_fields.append('lng = ?')
        update_values.append(float(data.get('lng')))
    
    if not update_fields:
        conn.close()
        return jsonify({'error': 'No fields to update'}), 400
    
    update_values.append(point_id)
    
    cursor.execute(f'''
        UPDATE points 
        SET {', '.join(update_fields)}
        WHERE id = ?
    ''', update_values)
    
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Point updated successfully'})

# Reporting endpoint

@app.route('/api/reports/summary', methods=['GET'])
def get_reports_summary():
    """Get operational summary statistics."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Incident stats
    cursor.execute('SELECT COUNT(*) FROM incidents')
    total_incidents = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM incidents WHERE status = ?', ('active',))
    active_incidents = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM incidents WHERE status = ?', ('assigned',))
    assigned_incidents = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM incidents WHERE status = ?', ('resolved',))
    resolved_incidents = cursor.fetchone()[0]
    
    # Team stats
    cursor.execute('SELECT COUNT(*) FROM teams')
    total_teams = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM teams WHERE status = ?', ('available',))
    available_teams = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM teams WHERE status = ?', ('deployed',))
    deployed_teams = cursor.fetchone()[0]
    
    # Point stats
    cursor.execute('SELECT COUNT(*) FROM points')
    total_points = cursor.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'total_incidents': total_incidents,
        'active_incidents': active_incidents,
        'assigned_incidents': assigned_incidents,
        'resolved_incidents': resolved_incidents,
        'total_teams': total_teams,
        'available_teams': available_teams,
        'deployed_teams': deployed_teams,
        'total_points': total_points
    })

@app.route('/api/routes/generate', methods=['POST'])
def generate_route():
    """Generate a route between team and incident using external engine."""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Invalid JSON payload'}), 400
        
        team_id = data.get('team_id')
        incident_id = data.get('incident_id')
        
        if not team_id or not incident_id:
            return jsonify({'error': 'team_id and incident_id are required'}), 400
        
        # Get team and incident details
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM teams WHERE id = ?', (team_id,))
        team = cursor.fetchone()
        
        cursor.execute('SELECT * FROM incidents WHERE id = ?', (incident_id,))
        incident = cursor.fetchone()
        
        if not team or not incident:
            conn.close()
            return jsonify({'error': 'Team or incident not found'}), 404
        
        # Call external engine API
        engine_payload = {
            'team': {'lat': team['lat'], 'lng': team['lng']},
            'incident': {'lat': incident['lat'], 'lng': incident['lng']}
        }
        
        response = requests.post(ENGINE_API_URL, json=engine_payload, timeout=10)
        response.raise_for_status()
        route_data = response.json()
        
        # Store route in database with new schema
        cursor.execute('''
            INSERT INTO routes (incident_id, team_id, path, distance, duration, status, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            incident_id,
            team_id,
            json.dumps(route_data.get('path', [])),
            route_data.get('distance', 0),
            route_data.get('duration', 0),
            'active',
            route_data.get('source', 'osrm')
        ))
        route_id = cursor.lastrowid
        
        # Update incident status to 'assigned'
        cursor.execute('''
            UPDATE incidents
            SET status = 'assigned', updated_at = ?
            WHERE id = ?
        ''', (datetime.now().isoformat(), incident_id))
        
        # Update team status to 'deployed'
        cursor.execute('''
            UPDATE teams
            SET status = 'deployed', updated_at = ?
            WHERE id = ?
        ''', (datetime.now().isoformat(), team_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'id': route_id,
            'route': route_data,
            'message': 'Route generated successfully'
        }), 201
        
    except requests.exceptions.RequestException as e:
        if 'conn' in locals():
            conn.close()
        return jsonify({'error': f'Failed to call engine API: {str(e)}'}), 500
    except Exception as e:
        if 'conn' in locals():
            conn.close()
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@app.route('/api/routes', methods=['GET'])
def get_routes():
    """Get all routes."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM routes ORDER BY created_at DESC')
    routes = [dict(row) for row in cursor.fetchall()]
    
    # Parse JSON path for each route
    for route in routes:
        route['path'] = json.loads(route['path'])
    
    conn.close()
    return jsonify(routes)

@app.route('/api/routes/<int:route_id>', methods=['DELETE'])
def delete_route(route_id):
    """Delete a route."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM routes WHERE id = ?', (route_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Route deleted successfully'})

@app.route('/api/teams/<int:team_id>/route', methods=['GET'])
def get_team_route(team_id):
    """Get active route for a team."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Find active route for the team
    cursor.execute('''
        SELECT r.*, i.* 
        FROM routes r
        JOIN incidents i ON r.incident_id = i.id
        WHERE r.team_id = ? AND r.status = 'active'
        ORDER BY r.created_at DESC
        LIMIT 1
    ''', (team_id,))
    
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return jsonify({'active': False})
    
    # Convert row to dict
    route_data = dict(row)
    
    # Parse path from JSON and ensure [lat, lng] format
    path = json.loads(route_data['path'])
    # OSRM returns [lng, lat], convert to [lat, lng]
    path = [[coord[1], coord[0]] for coord in path]
    
    # Build response
    response = {
        'active': True,
        'incident': {
            'id': route_data['incident_id'],
            'type': route_data['type'],
            'severity': route_data['severity'],
            'status': route_data['status'],
            'lat': route_data['lat'],
            'lng': route_data['lng'],
            'created_at': route_data['created_at']
        },
        'route': {
            'id': route_data['id'],
            'path': path,
            'distance': route_data['distance'],
            'duration': route_data['duration']
        }
    }
    
    conn.close()
    return jsonify(response)

# Initialize database on startup
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
