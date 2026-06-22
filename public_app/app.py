#!/usr/bin/env python3
"""
Public Flask App for Disaster Management System
Designed for cPanel shared hosting
"""

import traceback
from flask import Flask, request, jsonify, render_template, g
from flask_cors import CORS
import sqlite3
import requests
import json
from datetime import datetime
import os
import time
import logging
from logging.handlers import RotatingFileHandler

# Import RBAC auth module
from auth import (
    require_auth, require_user_auth, require_team_auth, require_role,
    generate_user_token, generate_team_token, hash_password, verify_password,
    apply_branch_filter, enforce_branch_on_write, log_action,
    is_in_branch_area, get_branches_for_geo_filtering
)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configuration
DATABASE = os.path.join(os.path.dirname(__file__), 'database', 'disaster_ops.db')
ENGINE_API_URL = os.environ.get('ENGINE_API_URL', 'http://localhost:5002/route')
LOG_FILE = os.path.join(os.path.dirname(__file__), 'system.log')

# Configure system logging with rotation
system_logger = logging.getLogger('disaster_ops')
system_logger.setLevel(logging.INFO)

# Rotating file handler - 5MB max, 5 backup files
file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=5*1024*1024,
    backupCount=5
)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))
system_logger.addHandler(file_handler)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))
system_logger.addHandler(console_handler)

# Simple in-memory event store for notifications
events = []  # Format: {"type": "incident_new"|"team_enter", "lat": float, "lng": float, "timestamp": str, "team_id": int|None}

def get_user_info(user):
    """Extract user info for logging traceability."""
    if not user:
        return {"user_id": None, "username": None, "role": None}
    # Handle sqlite3.Row objects by converting to dict
    if hasattr(user, 'keys') and not hasattr(user, 'get'):
        user = {key: user[key] for key in user.keys()}
    return {
        "user_id": user.get("user_id") or user.get("id"),
        "username": user.get("username"),
        "role": user.get("role")
    }

def system_log(action, entity_type, entity_id, user, details=None):
    """Log system operation to system.log file - NEVER crashes."""
    try:
        user_info = get_user_info(user)
        user_str = f"user_id={user_info['user_id']} username={user_info['username']} role={user_info['role']}"
        details_str = f" - {json.dumps(details)}" if details else ""
        system_logger.info(f"{action.upper()} - {entity_type} - id={entity_id} - {user_str}{details_str}")
    except Exception as e:
        system_logger.error(f"Error in system_log: {e}")

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
            status TEXT DEFAULT 'active',
            description TEXT,
            branch_id INTEGER,
            assigned_teams TEXT DEFAULT '[]',
            created_by INTEGER,
            resolved_at TIMESTAMP,
            closed_at TIMESTAMP,
            is_archived INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Add new columns if they don't exist (for existing databases)
    try:
        cursor.execute('ALTER TABLE incidents ADD COLUMN branch_id INTEGER')
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE incidents ADD COLUMN assigned_teams TEXT DEFAULT "[]"')
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE incidents ADD COLUMN created_by INTEGER')
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE incidents ADD COLUMN resolved_at TIMESTAMP')
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE incidents ADD COLUMN closed_at TIMESTAMP')
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE incidents ADD COLUMN is_archived INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass
    
    # Teams table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_number INTEGER UNIQUE,
            name TEXT NOT NULL,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            status TEXT DEFAULT 'available',
            current_status TEXT DEFAULT 'available',
            color TEXT DEFAULT '#007bff',
            icon TEXT DEFAULT '🚑',
            battery_level INTEGER DEFAULT 100,
            speed REAL DEFAULT 0.0,
            heading REAL DEFAULT 0.0,
            gps_enabled INTEGER DEFAULT 0,
            branch_id INTEGER,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Add new columns to teams if they don't exist
    try:
        cursor.execute('ALTER TABLE teams ADD COLUMN current_status TEXT DEFAULT "available"')
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE teams ADD COLUMN branch_id INTEGER')
    except sqlite3.OperationalError:
        pass
    
    # Routes table (updated schema)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id INTEGER NOT NULL,
            team_id INTEGER NOT NULL,
            data TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            path TEXT DEFAULT '[]',
            distance REAL DEFAULT 0,
            duration REAL DEFAULT 0,
            source TEXT DEFAULT 'osrm',
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
    
    # Incident logs table (audit trail)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS incident_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            performed_by INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            details TEXT
        )
    ''')
    
    # Incident reports table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS incident_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id INTEGER NOT NULL,
            summary TEXT,
            actions_taken TEXT,
            casualties TEXT,
            resources_used TEXT,
            notes TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Road blocks table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS road_blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            radius INTEGER DEFAULT 200,
            status TEXT CHECK(status IN ('closed','open','restricted')) NOT NULL,
            reason TEXT,
            severity INTEGER DEFAULT 3,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            active INTEGER DEFAULT 1
        )
    ''')
    
    # Manual routes table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS manual_routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER,
            incident_id INTEGER,
            waypoints TEXT NOT NULL,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            active INTEGER DEFAULT 1
        )
    ''')
    
    # Team reports table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS team_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            incident_id INTEGER,
            type TEXT NOT NULL,
            priority INTEGER DEFAULT 1,
            message TEXT,
            lat REAL,
            lng REAL,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            active INTEGER DEFAULT 1
        )
    ''')
    
    # Create indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_teams_status ON teams(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_routes_incident ON routes(incident_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_routes_team ON routes(team_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_road_blocks_active ON road_blocks(active)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_road_blocks_location ON road_blocks(lat, lng)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_manual_routes_team ON manual_routes(team_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_manual_routes_incident ON manual_routes(incident_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_team_reports_team ON team_reports(team_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_team_reports_incident ON team_reports(incident_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_team_reports_time ON team_reports(created_at)')
    
    conn.commit()
    conn.close()

def get_db():
    """Get database connection with WAL mode and timeout."""
    conn = sqlite3.connect(DATABASE, timeout=30.0)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrency
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=30000')
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

def log_incident_action(incident_id, action, user, details=None, conn=None, cursor=None):
    """Log incident action to incident_logs table for audit trail - NEVER crashes."""
    close_conn = False
    max_retries = 3
    retry_delay = 0.1
    
    for attempt in range(max_retries):
        try:
            if conn is None:
                conn = sqlite3.connect(DATABASE, timeout=10.0)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                close_conn = True
            user_info = get_user_info(user)
            details_json = json.dumps(details) if details else None
            system_logger.info(f"Logging incident action: incident_id={incident_id}, action={action}, user_id={user_info['user_id']}")
            cursor.execute('''
                INSERT INTO incident_logs (incident_id, action, performed_by, details)
                VALUES (?, ?, ?, ?)
            ''', (incident_id, action, user_info['user_id'], details_json))
            if close_conn:
                conn.commit()
                conn.close()
                conn = None
            system_logger.info(f"Successfully logged incident action for incident {incident_id}")
            return
        except sqlite3.OperationalError as e:
            if close_conn and conn:
                try:
                    conn.close()
                except Exception:
                    pass
                conn = None
            if 'database is locked' in str(e) and attempt < max_retries - 1:
                system_logger.warning(f"Database locked while logging incident action, retrying ({attempt + 1}/{max_retries})...")
                time.sleep(retry_delay * (attempt + 1))
                continue
            system_logger.error(f"Error logging incident action: {e}")
            traceback.print_exc()
            return
        except Exception as e:
            # Non-blocking - don't fail the operation if logging fails
            system_logger.error(f"Error logging incident action: {e}")
            traceback.print_exc()
            if close_conn and conn:
                try:
                    conn.close()
                except Exception:
                    pass
            return

# API Routes

@app.route('/')
def index():
    """Serve login page."""
    return render_template('login.html')

@app.route('/login')
def login_page():
    """Serve the login page."""
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    """Serve the dashboard (auth handled by frontend)."""
    return render_template('dashboard.html')

@app.route('/api/incidents', methods=['GET'])
@require_auth
def get_incidents():
    """Get incidents - filtered by GEOGRAPHIC area for operators, regional_admin, teams."""
    conn = get_db()
    cursor = conn.cursor()
    
    user = g.user
    
    # Admin sees all incidents (non-archived)
    if user.get('role') == 'admin':
        cursor.execute('SELECT * FROM incidents WHERE is_archived = 0 ORDER BY created_at DESC')
        incidents = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify(incidents)
    
    branches = get_branches_for_geo_filtering(conn, user)
    
    cursor.execute('SELECT * FROM incidents WHERE is_archived = 0 ORDER BY created_at DESC')
    all_incidents = [dict(row) for row in cursor.fetchall()]
    
    filtered_incidents = []
    user_id = user.get('user_id')
    team_id = user.get('team_id')
    
    for incident in all_incidents:
        # Teams always see incidents assigned to them
        if team_id:
            assigned_teams = json.loads(incident.get('assigned_teams') or '[]') if incident.get('assigned_teams') else []
            if team_id in assigned_teams:
                filtered_incidents.append(incident)
                continue
        # Otherwise filter by geography
        if branches:
            for branch in branches:
                if is_in_branch_area(incident['lat'], incident['lng'], branch):
                    filtered_incidents.append(incident)
                    break
    
    conn.close()
    return jsonify(filtered_incidents)

@app.route('/api/incidents', methods=['POST'])
@require_user_auth
def create_incident():
    """Create a new incident with validation - branch enforced from user context."""
    try:
        data = request.get_json()
        system_logger.info(f"Creating incident with data: {data}")
        
        if not data.get('type'):
            return jsonify({'error': 'Incident type is required'}), 400
        
        if not data.get('severity'):
            return jsonify({'error': 'Severity is required'}), 400
        
        valid_severity, severity_error = validate_severity(data.get('severity'))
        if not valid_severity:
            return jsonify({'error': severity_error}), 400
        
        valid_coords, coords_error = validate_coordinates(data.get('lat'), data.get('lng'))
        if not valid_coords:
            return jsonify({'error': coords_error}), 400
        
        data = enforce_branch_on_write(data)
        system_logger.info(f"After enforce_branch_on_write: branch_id={data.get('branch_id')}")
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO incidents (type, severity, lat, lng, status, branch_id, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('type'),
            str(data.get('severity')),
            float(data.get('lat')),
            float(data.get('lng')),
            'active',
            data.get('branch_id'),  # Can be None for admin users
            g.user.get('user_id')
        ))
        incident_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        events.append({
            'type': 'incident_new',
            'lat': float(data.get('lat')),
            'lng': float(data.get('lng')),
            'timestamp': datetime.now().isoformat(),
            'incident_id': incident_id
        })
        
        # System logging
        system_log('created', 'incident', incident_id, g.user, {
            'type': data['type'],
            'severity': data['severity'],
            'lat': data['lat'],
            'lng': data['lng'],
            'branch_id': data.get('branch_id')
        })
        
        # Log to incident timeline after connection is closed to avoid database lock
        try:
            log_incident_action(incident_id, 'created', g.user, {'type': data['type'], 'branch_id': data.get('branch_id')})
        except Exception:
            pass
        
        return jsonify({'id': incident_id, 'message': 'Incident created successfully'}), 201
    except Exception as e:
        system_logger.error(f"Error creating incident: {e}")
        import traceback
        system_logger.error(traceback.format_exc())
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

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
@require_user_auth
def patch_incident(incident_id):
    """Partially update an incident (severity, status, and multi-team assignment)."""
    data = request.get_json()
    user = g.user
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM incidents WHERE id = ?', (incident_id,))
    incident = cursor.fetchone()
    
    if not incident:
        conn.close()
        return jsonify({'error': 'Incident not found'}), 404
    
    incident = dict(incident)
    
    warnings = []
    
    if user.get('role') == 'operator':
        branches = get_branches_for_geo_filtering(conn, user)
        if not branches or not is_in_branch_area(incident['lat'], incident['lng'], branches[0]):
            conn.close()
            return jsonify({'error': 'Incident is outside your operational area'}), 403
    
    cursor.execute('SELECT * FROM incidents WHERE id = ? AND is_archived = 0', (incident_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Incident not found or archived'}), 404
    
    updates = []
    values = []
    
    if 'severity' in data:
        valid_severity, severity_error = validate_severity(data.get('severity'))
        if not valid_severity:
            conn.close()
            return jsonify({'error': severity_error}), 400
        updates.append('severity = ?')
        values.append(str(data.get('severity')))
    
    if 'status' in data:
        allowed_statuses = ['active', 'assigned', 'resolved', 'closed']
        if data.get('status') not in allowed_statuses:
            conn.close()
            return jsonify({'error': f'Invalid status. Allowed: {", ".join(allowed_statuses)}'}), 400
        updates.append('status = ?')
        values.append(data.get('status'))
        
        if data.get('status') == 'resolved':
            cursor.execute('UPDATE incidents SET resolved_at = ? WHERE id = ?', (datetime.now().isoformat(), incident_id))
            events.append({
                'type': 'incident_resolved',
                'lat': incident['lat'],
                'lng': incident['lng'],
                'timestamp': datetime.now().isoformat(),
                'incident_id': incident_id
            })
            try:
                cursor.execute('SELECT id FROM incident_reports WHERE incident_id = ?', (incident_id,))
                if not cursor.fetchone():
                    events.append({
                        'type': 'report_pending',
                        'timestamp': datetime.now().isoformat(),
                        'incident_id': incident_id,
                        'lat': incident['lat'],
                        'lng': incident['lng']
                    })
            except Exception:
                pass
            log_incident_action(incident_id, 'resolved', g.user, {'status': data.get('status')}, conn, cursor)
        
        if data.get('status') == 'closed':
            cursor.execute('UPDATE incidents SET closed_at = ? WHERE id = ?', (datetime.now().isoformat(), incident_id))
            log_incident_action(incident_id, 'closed', g.user, {'status': data.get('status')}, conn, cursor)
    
    if 'assign_team_id' in data:
        team_id = data.get('assign_team_id')
        cursor.execute('SELECT * FROM teams WHERE id = ?', (team_id,))
        team = cursor.fetchone()
        
        if team:
            team = dict(team)
            current_status = team.get('current_status', team.get('status', 'available'))
            if current_status not in ['available']:
                warnings.append(f"Team already handling another incident (status: {current_status})")
            
            cursor.execute('SELECT assigned_teams FROM incidents WHERE id = ?', (incident_id,))
            row = cursor.fetchone()
            assigned_teams = json.loads(row['assigned_teams']) if row and row['assigned_teams'] else []
            
            if team_id not in assigned_teams:
                assigned_teams.append(team_id)
                updates.append('assigned_teams = ?')
                values.append(json.dumps(assigned_teams))
            
            cursor.execute('UPDATE teams SET current_status = ?, status = ? WHERE id = ?', ('en_route', 'en_route', team_id))
            
            events.append({
                'type': 'incident_assigned',
                'timestamp': datetime.now().isoformat(),
                'incident_id': incident_id,
                'team_id': team_id,
                'lat': incident['lat'],
                'lng': incident['lng']
            })
            
            log_incident_action(incident_id, 'assigned_team', g.user, {'team_id': team_id}, conn, cursor)
        else:
            pass
    
    if 'type' in data:
        updates.append('type = ?')
        values.append(data.get('type'))
    
    if not updates:
        conn.close()
        return jsonify({'error': 'No valid fields to update'}), 400
    
    values.append(datetime.now().isoformat())
    values.append(incident_id)
    
    cursor.execute(f'''
        UPDATE incidents 
        SET {", ".join(updates)}, updated_at = ?
        WHERE id = ?
    ''', values)
    conn.commit()
    conn.close()
    
    # System logging
    system_log('updated', 'incident', incident_id, g.user, {
        'updates': data,
        'warnings': warnings
    })
    
    response = {'message': 'Incident updated successfully'}
    if warnings:
        response['warnings'] = warnings
    
    return jsonify(response)

@app.route('/api/incidents/<int:incident_id>/archive', methods=['PATCH'])
@require_user_auth
def archive_incident(incident_id):
    """Archive an incident (admin only) - soft delete."""
    if g.user.get('role') != 'admin':
        return jsonify({'error': 'Admin access required to archive incidents'}), 403
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM incidents WHERE id = ?', (incident_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Incident not found'}), 404
    
    cursor.execute('UPDATE incidents SET is_archived = 1, status = ? WHERE id = ?', ('archived', incident_id))
    conn.commit()
    conn.close()
    
    # System logging
    system_log('archived', 'incident', incident_id, g.user, {})
    
    log_incident_action(incident_id, 'archived', g.user, {})
    
    return jsonify({'message': 'Incident archived successfully'})

@app.route('/api/incidents/<int:incident_id>', methods=['DELETE'])
def delete_incident(incident_id):
    """Archive an incident (deprecated - use archive endpoint)."""
    return jsonify({'error': 'DELETE deprecated. Use PATCH /api/incidents/<id>/archive'}), 400

@app.route('/api/teams', methods=['GET'])
@require_auth
def get_teams():
    """Get teams with computed GPS state - filtered by GEOGRAPHIC area for operators, regional_admin, teams."""
    conn = get_db()
    cursor = conn.cursor()
    
    user = g.user
    
    if user.get('role') == 'admin':
        cursor.execute('SELECT * FROM teams ORDER BY name')
        teams = [dict(row) for row in cursor.fetchall()]
        for team in teams:
            team['current_status'] = team.get('current_status') or team.get('status', 'available')
            if not team.get('gps_enabled'):
                team['gps_state'] = 'manual'
            elif not team.get('last_updated'):
                team['gps_state'] = 'waiting_for_connect'
            else:
                last_update = datetime.fromisoformat(team['last_updated'].replace('Z', '+00:00'))
                now = datetime.now(last_update.tzinfo)
                diff_seconds = (now - last_update).total_seconds()
                
                if diff_seconds < 15:
                    team['gps_state'] = 'gps_active'
                elif diff_seconds < 60:
                    team['gps_state'] = 'gps_lost'
                else:
                    team['gps_state'] = 'gps_lost'
            
            # Count active incidents for this team
            cursor.execute('''
                SELECT COUNT(*) FROM incidents 
                WHERE is_archived = 0 
                AND status IN (?, ?, ?) 
                AND assigned_teams LIKE ?
            ''', ('active', 'assigned', 'resolved', f'%{team["id"]}%'))
            team['active_incidents'] = cursor.fetchone()[0]
        conn.close()
        return jsonify(teams)
    
    branches = get_branches_for_geo_filtering(conn, user)
    
    if not branches:
        conn.close()
        return jsonify([])
    
    cursor.execute('SELECT * FROM teams ORDER BY name')
    all_teams = [dict(row) for row in cursor.fetchall()]
    
    filtered_teams = []
    for team in all_teams:
        for branch in branches:
            if is_in_branch_area(team['lat'], team['lng'], branch):
                team['current_status'] = team.get('current_status') or team.get('status', 'available')
                if not team.get('gps_enabled'):
                    team['gps_state'] = 'manual'
                elif not team.get('last_updated'):
                    team['gps_state'] = 'waiting_for_connect'
                else:
                    last_update = datetime.fromisoformat(team['last_updated'].replace('Z', '+00:00'))
                    now = datetime.now(last_update.tzinfo)
                    diff_seconds = (now - last_update).total_seconds()
                    
                    if diff_seconds < 15:
                        team['gps_state'] = 'gps_active'
                    elif diff_seconds < 60:
                        team['gps_state'] = 'gps_lost'
                    else:
                        team['gps_state'] = 'gps_lost'
                
                # Count active incidents for this team
                cursor.execute('''
                    SELECT COUNT(*) FROM incidents 
                    WHERE is_archived = 0 
                    AND status IN (?, ?, ?) 
                    AND assigned_teams LIKE ?
                ''', ('active', 'assigned', 'resolved', f'%{team["id"]}%'))
                team['active_incidents'] = cursor.fetchone()[0]
                
                filtered_teams.append(team)
                break
    
    conn.close()
    return jsonify(filtered_teams)

@app.route('/api/teams', methods=['POST'])
@require_user_auth
def create_team():
    """Create a new team with validation - branch enforced from user context."""
    data = request.get_json()
    
    if not data.get('name'):
        return jsonify({'error': 'Team name is required'}), 400
    
    valid_coords, coords_error = validate_coordinates(data.get('lat'), data.get('lng'))
    if not valid_coords:
        return jsonify({'error': coords_error}), 400
    
    data = enforce_branch_on_write(data)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO teams (team_number, name, lat, lng, status, current_status, color, icon, battery_level, speed, heading, gps_enabled, branch_id, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('team_number'),
        data.get('name'),
        float(data.get('lat')),
        float(data.get('lng')),
        data.get('status', 'available'),
        data.get('status', 'available'),
        data.get('color', '#3498db'),
        data.get('icon', '🚑'),
        data.get('battery_level', 100),
        data.get('speed', 0.0),
        data.get('heading', 0.0),
        data.get('gps_enabled', 0),
        data['branch_id'],
        datetime.now().isoformat()
    ))
    team_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # System logging
    system_log('created', 'team', team_id, g.user, {
        'name': data['name'],
        'team_number': data.get('team_number'),
        'branch_id': data.get('branch_id')
    })
    
    log_action('created', 'team', team_id, None, {'name': data['name'], 'branch_id': data['branch_id']})
    
    return jsonify({'id': team_id, 'message': 'Team created successfully'}), 201

@app.route('/api/teams/<int:team_id>', methods=['PUT'])
def update_team(team_id):
    """Update a team."""
    data = request.get_json()
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE teams 
        SET team_number = ?, name = ?, lat = ?, lng = ?, status = ?, updated_at = ?
        WHERE id = ?
    ''', (
        data.get('team_number'),
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
@require_user_auth
def patch_team(team_id):
    """Partially update a team (status, location, gps_enabled, color, icon)."""
    data = request.get_json()
    user = g.user
    
    # Get team to check geo access
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM teams WHERE id = ?', (team_id,))
    team = cursor.fetchone()
    
    if not team:
        conn.close()
        return jsonify({'error': 'Team not found'}), 404
    
    team = dict(team)
    
    # Geo validation for operators - can only update teams in their area
    if user.get('role') == 'operator':
        branches = get_branches_for_geo_filtering(conn, user)
        if not branches or not is_in_branch_area(team['lat'], team['lng'], branches[0]):
            conn.close()
            return jsonify({'error': 'Team is outside your operational area'}), 403
    
    updates = []
    values = []
    
    if 'lat' in data or 'lng' in data:
        lat = data.get('lat')
        lng = data.get('lng')
        valid_coords, coords_error = validate_coordinates(lat, lng)
        if not valid_coords:
            conn.close()
            return jsonify({'error': coords_error}), 400
        if lat is not None:
            updates.append('lat = ?')
            values.append(float(lat))
        if lng is not None:
            updates.append('lng = ?')
            values.append(float(lng))
    
    if 'status' in data:
        allowed_statuses = ['available', 'en_route', 'on_scene', 'busy', 'offline']
        if data.get('status') not in allowed_statuses:
            conn.close()
            return jsonify({'error': f'Invalid status. Allowed: {", ".join(allowed_statuses)}'}), 400
        updates.append('status = ?')
        values.append(data.get('status'))
        updates.append('current_status = ?')
        values.append(data.get('status'))
    
    if 'gps_enabled' in data:
        gps_enabled = data.get('gps_enabled')
        # Handle string "1"/"0" from frontend
        if isinstance(gps_enabled, str):
            gps_enabled = int(gps_enabled)
        if not isinstance(gps_enabled, (int, bool)):
            conn.close()
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
    
    if 'team_number' in data:
        updates.append('team_number = ?')
        values.append(data.get('team_number'))
    
    if 'branch_id' in data:
        branch_id = data.get('branch_id')
        if branch_id is not None:
            updates.append('branch_id = ?')
            values.append(int(branch_id))
    
    if not updates:
        conn.close()
        return jsonify({'error': 'No valid fields to update'}), 400
    
    values.append(datetime.now().isoformat())
    values.append(team_id)
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
    
    cursor.execute('DELETE FROM routes WHERE team_id = ?', (team_id,))
    cursor.execute('DELETE FROM teams WHERE id = ?', (team_id,))
    
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Team and related routes deleted successfully'})

@app.route('/api/teams/<int:team_id>/status', methods=['PATCH'])
@require_user_auth
def update_team_status(team_id):
    """Update team status with logging and notifications."""
    data = request.get_json()
    user = g.user
    
    allowed_statuses = ['available', 'en_route', 'on_scene', 'busy', 'offline']
    if 'status' not in data or data.get('status') not in allowed_statuses:
        return jsonify({'error': f'Invalid or missing status. Allowed: {", ".join(allowed_statuses)}'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM teams WHERE id = ?', (team_id,))
    team = cursor.fetchone()
    
    if not team:
        conn.close()
        return jsonify({'error': 'Team not found'}), 404
    
    team = dict(team)
    
    if user.get('role') == 'operator':
        branches = get_branches_for_geo_filtering(conn, user)
        if not branches or not is_in_branch_area(team['lat'], team['lng'], branches[0]):
            conn.close()
            return jsonify({'error': 'Team is outside your operational area'}), 403
    
    cursor.execute('UPDATE teams SET current_status = ?, status = ?, updated_at = ? WHERE id = ?', 
                   (data['status'], data['status'], datetime.now().isoformat(), team_id))
    conn.commit()
    conn.close()
    
    cursor_team = get_db()
    cursor_team_exec = cursor_team.cursor()
    cursor_team_exec.execute('SELECT incident_id FROM routes WHERE team_id = ? AND status = ? ORDER BY created_at DESC LIMIT 1', (team_id, 'active'))
    route = cursor_team_exec.fetchone()
    cursor_team.close()
    
    incident_id = route['incident_id'] if route else None
    
    # System logging
    system_log('status_updated', 'team', team_id, g.user, {
        'status': data['status'],
        'incident_id': incident_id
    })
    
    if incident_id:
        log_incident_action(incident_id, 'team_status_updated', g.user, {'team_id': team_id, 'status': data['status']})
    
    events.append({
        'type': 'team_status_changed',
        'timestamp': datetime.now().isoformat(),
        'team_id': team_id,
        'status': data['status'],
        'incident_id': incident_id,
        'lat': team['lat'],
        'lng': team['lng']
    })
    
    return jsonify({'message': 'Team status updated successfully'})

@app.route('/api/incidents/<int:incident_id>/report', methods=['GET'])
@require_auth
def get_incident_report(incident_id):
    """Get incident report if exists."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM incident_reports WHERE incident_id = ?', (incident_id,))
    report = cursor.fetchone()
    conn.close()
    
    if not report:
        return jsonify({'exists': False, 'report': None}), 200
    
    report_data = dict(report)
    report_data['exists'] = True
    return jsonify(report_data)

@app.route('/api/incidents/<int:incident_id>/report', methods=['POST'])
@require_user_auth
def create_incident_report(incident_id):
    """Create incident report (non-blocking, can be done after resolved)."""
    data = request.get_json()
    user = g.user
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM incidents WHERE id = ? AND is_archived = 0', (incident_id,))
    incident = cursor.fetchone()
    
    if not incident:
        conn.close()
        return jsonify({'error': 'Incident not found or archived'}), 404
    
    incident = dict(incident)
    
    if user.get('role') == 'operator':
        branches = get_branches_for_geo_filtering(conn, user)
        if not branches or not is_in_branch_area(incident['lat'], incident['lng'], branches[0]):
            conn.close()
            return jsonify({'error': 'Incident is outside your operational area'}), 403
    
    cursor.execute('''
        INSERT INTO incident_reports (incident_id, summary, actions_taken, casualties, resources_used, notes, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        incident_id,
        data.get('summary'),
        data.get('actions_taken'),
        data.get('casualties'),
        data.get('resources_used'),
        data.get('notes'),
        user.get('user_id')
    ))
    report_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # System logging
    system_log('report_created', 'incident', incident_id, g.user, {
        'report_id': report_id,
        'summary': data.get('summary')
    })
    
    log_incident_action(incident_id, 'report_created', g.user, {'report_id': report_id})
    
    return jsonify({'id': report_id, 'message': 'Report created successfully'}), 201

@app.route('/api/incidents/<int:incident_id>/logs', methods=['GET'])
@require_auth
def get_incident_logs(incident_id):
    """Get timeline of incident actions (audit trail)."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM incidents WHERE id = ?', (incident_id,))
    incident = cursor.fetchone()
    
    if not incident:
        conn.close()
        return jsonify({'error': 'Incident not found'}), 404
    
    incident = dict(incident)
    
    user = g.user
    # Geo validation for operators - can only view logs for incidents in their area
    if user.get('role') == 'operator':
        branches = get_branches_for_geo_filtering(conn, user)
        if not branches or not is_in_branch_area(incident['lat'], incident['lng'], branches[0]):
            conn.close()
            return jsonify({'error': 'Incident is outside your operational area'}), 403
    
    cursor.execute('SELECT * FROM incident_logs WHERE incident_id = ? ORDER BY timestamp ASC', (incident_id,))
    logs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify(logs)

@app.route('/api/incidents/archived', methods=['GET'])
@require_user_auth
def get_archived_incidents():
    """Get archived incidents (admin only)."""
    if g.user.get('role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM incidents WHERE is_archived = 1 ORDER BY created_at DESC')
    incidents = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify(incidents)

# GPS Location Update Endpoint (SECURE + RATE LIMITED)

@app.route('/api/teams/location', methods=['POST'])
@require_team_auth  # JWT auth required - team_id from token ONLY
def update_team_location():
    """
    Update team location via GPS tracking.
    SECURE: team_id comes ONLY from JWT token, never from request payload.
    RATE LIMITED: minimum 2 seconds between updates.
    """
    data = request.get_json()
    
    # STRICT: Get team_id and branch_id from JWT token ONLY
    team_id = g.user['team_id']
    branch_id = g.user['branch_id']
    
    system_logger.info(f"Location update request: team_id={team_id}, branch_id={branch_id}, gps_user={g.user}")
    
    lat = data.get('lat')
    lng = data.get('lng')
    
    if lat is None or lng is None:
        return jsonify({'error': 'lat and lng are required'}), 400
    
    # Validate coordinates
    valid_coords, coords_error = validate_coordinates(lat, lng)
    if not valid_coords:
        return jsonify({'error': coords_error}), 400
    
    # Use retry logic for database operations to handle concurrent access
    max_retries = 3
    retry_delay = 0.1
    
    for attempt in range(max_retries):
        conn = None
        try:
            conn = get_db()
            cursor = conn.cursor()
            
            # RATE LIMITING: Check last update time (minimum 2 seconds between updates)
            cursor.execute('SELECT last_updated, gps_enabled FROM teams WHERE id = ?', (team_id,))
            team = cursor.fetchone()
            
            if not team:
                conn.close()
                return jsonify({'error': 'Team not found'}), 404
            
            # Check if GPS is enabled
            system_logger.info(f"Location update team check: team_id={team_id}, gps_enabled={team['gps_enabled']}, raw={dict(team)}")
            if not team['gps_enabled']:
                conn.close()
                system_logger.warning(f"GPS tracking disabled for team {team_id}")
                return jsonify({'error': 'GPS tracking is not enabled for this team'}), 403
            
            # Rate limit check
            if team['last_updated']:
                last_update = datetime.fromisoformat(team['last_updated'].replace('Z', '+00:00'))
                now = datetime.now(last_update.tzinfo)
                diff_seconds = (now - last_update).total_seconds()
                
                if diff_seconds < 2:  # 2 second minimum interval
                    conn.close()
                    return jsonify({
                        'message': 'Update throttled',
                        'team_id': team_id,
                        'retry_after': int(2 - diff_seconds)
                    }), 429  # Too Many Requests
            
            # Update location
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
            conn = None
            
            return jsonify({
                'message': 'Location updated successfully',
                'team_id': team_id,
                'branch_id': branch_id
            })
            
        except sqlite3.OperationalError as e:
            if conn:
                try:
                    conn.close()
                except:
                    pass
                conn = None
            
            if 'database is locked' in str(e) and attempt < max_retries - 1:
                print(f'Database locked, retrying ({attempt + 1}/{max_retries})...')
                time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                continue
            else:
                print(f'Database error after {attempt + 1} attempts: {e}')
                return jsonify({'error': 'Database temporarily unavailable, please retry'}), 503
        except Exception as e:
            if conn:
                try:
                    conn.close()
                except:
                    pass
            print(f'Error in update_team_location: {e}')
            return jsonify({'error': 'Internal server error'}), 500
    
    # Should not reach here, but just in case
    return jsonify({'error': 'Failed to update location after retries'}), 503

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
    
    cursor.execute('SELECT COUNT(*) FROM incidents WHERE is_archived = 0')
    total_incidents = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM incidents WHERE status = ? AND is_archived = 0', ('active',))
    active_incidents = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM incidents WHERE status = ? AND is_archived = 0', ('assigned',))
    assigned_incidents = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM incidents WHERE status = ? AND is_archived = 0', ('resolved',))
    resolved_incidents = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM incidents WHERE status = ? AND is_archived = 0', ('closed',))
    closed_incidents = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM teams')
    total_teams = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM teams WHERE current_status = ?', ('available',))
    available_teams = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM teams WHERE current_status IN (?, ?)', ('en_route', 'on_scene'))
    active_teams = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM points')
    total_points = cursor.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'total_incidents': total_incidents,
        'active_incidents': active_incidents,
        'assigned_incidents': assigned_incidents,
        'resolved_incidents': resolved_incidents,
        'closed_incidents': closed_incidents,
        'total_teams': total_teams,
        'available_teams': available_teams,
        'active_teams': active_teams,
        'total_points': total_points
    })

@app.route('/api/routes/generate', methods=['POST'])
@require_auth
def generate_route():
    """Generate a route between team and incident using external engine.
    Supports manual mode with waypoints for human-defined routing."""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Invalid JSON payload'}), 400
        
        team_id = data.get('team_id')
        incident_id = data.get('incident_id')
        manual_mode = data.get('manual_mode', False)
        waypoints = data.get('waypoints', [])
        
        if not team_id or not incident_id:
            return jsonify({'error': 'team_id and incident_id are required'}), 400
        
        # Validate manual mode requirements
        if manual_mode:
            if not waypoints or len(waypoints) < 1:
                return jsonify({'error': 'waypoints required for manual mode'}), 400
        
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
        
        # Get active road blocks for route avoidance
        expire_road_blocks(conn, cursor)
        cursor.execute('SELECT * FROM road_blocks WHERE active = 1')
        road_blocks = [dict(row) for row in cursor.fetchall()]
        
        # Call external engine API with road blocks
        engine_payload = {
            'team': {'lat': team['lat'], 'lng': team['lng']},
            'incident': {'lat': incident['lat'], 'lng': incident['lng']},
            'road_blocks': road_blocks,
            'manual_mode': manual_mode,
            'waypoints': waypoints
        }
        
        response = requests.post(ENGINE_API_URL, json=engine_payload, timeout=10)
        response.raise_for_status()
        route_data = response.json()
        
        # Check if manual route was rejected due to road blocks
        if manual_mode and route_data.get('status') == 'invalid':
            conn.close()
            return jsonify({
                'status': 'invalid',
                'message': route_data.get('message', 'Manual route intersects blocked road')
            }), 400
        
        # Store route in database
        route_path = json.dumps(route_data.get('path', []))
        cursor.execute('''
            INSERT INTO routes (incident_id, team_id, data, path, distance, duration, status, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            incident_id,
            team_id,
            route_path,
            route_path,
            route_data.get('distance', 0),
            route_data.get('duration', 0),
            'active',
            route_data.get('source', 'osrm')
        ))
        route_id = cursor.lastrowid
        
        # Log manual route usage
        if manual_mode:
            system_log('manual_route_used', 'user', g.user.get('user_id'), {
                'route_id': route_id,
                'team_id': team_id,
                'incident_id': incident_id,
                'waypoints_count': len(waypoints)
            })
        
        cursor.execute('''
            UPDATE teams
            SET status = ?, current_status = ?, updated_at = ?
            WHERE id = ?
        ''', ('en_route', 'en_route', datetime.now().isoformat(), team_id))
        
        cursor.execute('''
            UPDATE incidents
            SET status = ?, updated_at = ?
            WHERE id = ?
        ''', ('assigned', datetime.now().isoformat(), incident_id))
        
        cursor.execute('SELECT assigned_teams FROM incidents WHERE id = ?', (incident_id,))
        row = cursor.fetchone()
        assigned_teams = json.loads(row['assigned_teams']) if row and row['assigned_teams'] else []
        if team_id not in assigned_teams:
            assigned_teams.append(team_id)
            cursor.execute('UPDATE incidents SET assigned_teams = ? WHERE id = ?', (json.dumps(assigned_teams), incident_id))
        
        log_incident_action(incident_id, 'assigned_team', g.user, {'team_id': team_id}, conn, cursor)
        
        events.append({
            'type': 'incident_assigned',
            'timestamp': datetime.now().isoformat(),
            'incident_id': incident_id,
            'team_id': team_id,
            'lat': incident['lat'],
            'lng': incident['lng']
        })
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'id': route_id,
            'route': route_data,
            'message': 'Route generated successfully'
        }), 201
        
    except requests.exceptions.RequestException as e:
        system_logger.error(f"Failed to call engine API: {e}")
        if 'conn' in locals():
            conn.close()
        return jsonify({'error': f'Failed to call engine API: {str(e)}'}), 500
    except Exception as e:
        system_logger.error(f"Internal server error in route generation: {e}")
        import traceback
        system_logger.error(traceback.format_exc())
        if 'conn' in locals():
            conn.close()
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@app.route('/api/routes', methods=['GET'])
@require_auth
def get_routes():
    """Get routes - filtered by GEOGRAPHIC area for operators, regional_admin, teams."""
    conn = get_db()
    cursor = conn.cursor()
    
    user = g.user
    
    # Admin sees all routes
    if user.get('role') == 'admin':
        cursor.execute('SELECT * FROM routes ORDER BY created_at DESC')
        routes = [dict(row) for row in cursor.fetchall()]
        for route in routes:
            route['path'] = json.loads(route['path'])
        conn.close()
        return jsonify(routes)
    
    # Get branches for geo filtering based on user role
    branches = get_branches_for_geo_filtering(conn, user)
    
    if not branches:
        conn.close()
        return jsonify([])
    
    # Fetch all routes with their incident locations
    cursor.execute('''
        SELECT r.*, i.lat as incident_lat, i.lng as incident_lng
        FROM routes r
        LEFT JOIN incidents i ON r.incident_id = i.id
        ORDER BY r.created_at DESC
    ''')
    all_routes = [dict(row) for row in cursor.fetchall()]
    
    # Filter by geography: route's incident must be within ANY relevant branch area
    filtered_routes = []
    for route in all_routes:
        for branch in branches:
            if is_in_branch_area(route['incident_lat'], route['incident_lng'], branch):
                route['path'] = json.loads(route['path'])
                filtered_routes.append(route)
                break  # Match found, no need to check other branches
    
    conn.close()
    return jsonify(filtered_routes)

@app.route('/api/routes/<int:route_id>', methods=['DELETE'])
def delete_route(route_id):
    """Delete a route."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM routes WHERE id = ?', (route_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Route deleted successfully'})

# ============== ROAD BLOCKS API ==============

def expire_road_blocks(conn=None, cursor=None):
    """Auto-expire road blocks where expires_at has passed."""
    close_conn = False
    try:
        if conn is None:
            conn = get_db()
            cursor = conn.cursor()
            close_conn = True
        
        cursor.execute('''
            UPDATE road_blocks
            SET active = 0
            WHERE active = 1 AND expires_at IS NOT NULL AND expires_at < datetime('now')
        ''')
        if close_conn:
            conn.commit()
    except Exception as e:
        system_logger.error(f"Error expiring road blocks: {e}")
    finally:
        if close_conn and conn:
            conn.close()

@app.route('/api/road-blocks', methods=['GET'])
@require_auth
def get_road_blocks():
    """Get all active road blocks."""
    expire_road_blocks()
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM road_blocks WHERE active = 1 ORDER BY created_at DESC
    ''')
    blocks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify(blocks)

@app.route('/api/road-blocks', methods=['POST'])
@require_user_auth
def create_road_block():
    """Create a new road block."""
    data = request.get_json()
    
    lat = data.get('lat')
    lng = data.get('lng')
    radius = data.get('radius', 200)
    status = data.get('status', 'closed')
    reason = data.get('reason', '')
    severity = data.get('severity', 3)
    expires_at = data.get('expires_at')
    
    # Validate coordinates
    valid_coords, coords_error = validate_coordinates(lat, lng)
    if not valid_coords:
        return jsonify({'error': coords_error}), 400
    
    # Validate status
    if status not in ['closed', 'open', 'restricted']:
        return jsonify({'error': 'Status must be closed, open, or restricted'}), 400
    
    # Validate severity
    valid_severity, severity_error = validate_severity(severity)
    if not valid_severity:
        return jsonify({'error': severity_error}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO road_blocks (lat, lng, radius, status, reason, severity, created_by, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (lat, lng, radius, status, reason, severity, g.user.get('user_id'), expires_at))
        
        block_id = cursor.lastrowid
        conn.commit()
        
        # System log
        system_log('road_block_created', 'user', g.user.get('user_id'), {
            'block_id': block_id,
            'lat': lat,
            'lng': lng,
            'radius': radius,
            'status': status,
            'reason': reason
        })
        
        conn.close()
        
        return jsonify({
            'id': block_id,
            'lat': lat,
            'lng': lng,
            'radius': radius,
            'status': status,
            'reason': reason,
            'severity': severity,
            'expires_at': expires_at
        }), 201
    except Exception as e:
        conn.close()
        system_logger.error(f"Error creating road block: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/road-blocks/<int:block_id>', methods=['PATCH'])
@require_user_auth
def update_road_block(block_id):
    """Update a road block."""
    data = request.get_json()
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM road_blocks WHERE id = ?', (block_id,))
    block = cursor.fetchone()
    
    if not block:
        conn.close()
        return jsonify({'error': 'Road block not found'}), 404
    
    # Build update query dynamically
    updates = []
    params = []
    
    if 'status' in data:
        if data['status'] not in ['closed', 'open', 'restricted']:
            conn.close()
            return jsonify({'error': 'Status must be closed, open, or restricted'}), 400
        updates.append('status = ?')
        params.append(data['status'])
    
    if 'radius' in data:
        updates.append('radius = ?')
        params.append(data['radius'])
    
    if 'reason' in data:
        updates.append('reason = ?')
        params.append(data['reason'])
    
    if 'severity' in data:
        valid_severity, severity_error = validate_severity(data['severity'])
        if not valid_severity:
            conn.close()
            return jsonify({'error': severity_error}), 400
        updates.append('severity = ?')
        params.append(data['severity'])
    
    if 'expires_at' in data:
        updates.append('expires_at = ?')
        params.append(data['expires_at'])
    
    if 'active' in data:
        updates.append('active = ?')
        params.append(1 if data['active'] else 0)
    
    if not updates:
        conn.close()
        return jsonify({'error': 'No valid fields to update'}), 400
    
    params.append(block_id)
    
    try:
        cursor.execute(f'''
            UPDATE road_blocks SET {', '.join(updates)} WHERE id = ?
        ''', params)
        
        conn.commit()
        
        # System log
        system_log('road_block_updated', 'user', g.user.get('user_id'), {
            'block_id': block_id,
            'updates': data
        })
        
        conn.close()
        
        return jsonify({'message': 'Road block updated successfully'})
    except Exception as e:
        conn.close()
        system_logger.error(f"Error updating road block: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/road-blocks/<int:block_id>', methods=['DELETE'])
@require_user_auth
def delete_road_block(block_id):
    """Soft delete a road block (set active = 0)."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM road_blocks WHERE id = ?', (block_id,))
    block = cursor.fetchone()
    
    if not block:
        conn.close()
        return jsonify({'error': 'Road block not found'}), 404
    
    cursor.execute('UPDATE road_blocks SET active = 0 WHERE id = ?', (block_id,))
    conn.commit()
    
    # System log
    system_log('road_block_removed', 'user', g.user.get('user_id'), {
        'block_id': block_id,
        'lat': block['lat'],
        'lng': block['lng']
    })
    
    conn.close()
    
    return jsonify({'message': 'Road block deleted successfully'})

# ============== MANUAL ROUTES ENDPOINTS ==============

@app.route('/api/manual-routes', methods=['POST'])
@require_user_auth
def create_manual_route():
    """Create a manual route with waypoints."""
    data = request.get_json()
    team_id = data.get('team_id')
    incident_id = data.get('incident_id')
    waypoints = data.get('waypoints')
    
    if not team_id or not incident_id or not waypoints:
        return jsonify({'error': 'team_id, incident_id, and waypoints are required'}), 400
    
    if not isinstance(waypoints, list) or len(waypoints) < 1:
        return jsonify({'error': 'waypoints must be a non-empty array'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Validate team and incident exist
    cursor.execute('SELECT id FROM teams WHERE id = ?', (team_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Team not found'}), 404
    
    cursor.execute('SELECT id FROM incidents WHERE id = ?', (incident_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Incident not found'}), 404
    
    # Store manual route
    cursor.execute('''
        INSERT INTO manual_routes (team_id, incident_id, waypoints, created_by, active)
        VALUES (?, ?, ?, ?, 1)
    ''', (team_id, incident_id, json.dumps(waypoints), g.user.get('user_id')))
    
    route_id = cursor.lastrowid
    conn.commit()
    
    # System log
    system_log('manual_route_created', 'user', g.user.get('user_id'), {
        'route_id': route_id,
        'team_id': team_id,
        'incident_id': incident_id,
        'waypoints_count': len(waypoints)
    })
    
    conn.close()
    
    return jsonify({
        'id': route_id,
        'message': 'Manual route created successfully'
    }), 201

@app.route('/api/manual-routes/<int:incident_id>', methods=['GET'])
@require_user_auth
def get_manual_routes(incident_id):
    """Get all manual routes for an incident."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM manual_routes 
        WHERE incident_id = ? AND active = 1
        ORDER BY created_at DESC
    ''', (incident_id,))
    
    routes = []
    for row in cursor.fetchall():
        route = dict(row)
        route['waypoints'] = json.loads(route['waypoints'])
        routes.append(route)
    
    conn.close()
    return jsonify(routes)

@app.route('/api/manual-routes/<int:route_id>', methods=['DELETE'])
@require_user_auth
def delete_manual_route(route_id):
    """Soft delete a manual route (set active = 0)."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM manual_routes WHERE id = ?', (route_id,))
    route = cursor.fetchone()
    
    if not route:
        conn.close()
        return jsonify({'error': 'Manual route not found'}), 404
    
    cursor.execute('UPDATE manual_routes SET active = 0 WHERE id = ?', (route_id,))
    conn.commit()
    
    # System log
    system_log('manual_route_deleted', 'user', g.user.get('user_id'), {
        'route_id': route_id,
        'incident_id': route['incident_id'],
        'team_id': route['team_id']
    })
    
    conn.close()
    
    return jsonify({'message': 'Manual route deleted successfully'})

# Team Reports API endpoints
@app.route('/api/team-reports', methods=['POST'])
@require_user_auth
def create_team_report():
    """Create a new team report."""
    data = request.get_json()
    team_id = data.get('team_id')
    incident_id = data.get('incident_id')
    report_type = data.get('type')
    priority = data.get('priority', 1)
    message = data.get('message')
    lat = data.get('lat')
    lng = data.get('lng')
    
    # Validate required fields
    if not team_id:
        return jsonify({'error': 'team_id is required'}), 400
    if not report_type:
        return jsonify({'error': 'type is required'}), 400
    
    # Validate type
    valid_types = ['status', 'hazard', 'update', 'request']
    if report_type not in valid_types:
        return jsonify({'error': f'type must be one of: {", ".join(valid_types)}'}), 400
    
    # Validate priority
    if priority and (not isinstance(priority, int) or priority < 1 or priority > 5):
        return jsonify({'error': 'priority must be an integer between 1 and 5'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO team_reports (team_id, incident_id, type, priority, message, lat, lng, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (team_id, incident_id, report_type, priority, message, lat, lng, g.user.get('user_id')))
    report_id = cursor.lastrowid
    conn.commit()
    
    # System log
    system_log('team_report_created', 'user', g.user.get('user_id'), {
        'report_id': report_id,
        'team_id': team_id,
        'incident_id': incident_id,
        'type': report_type,
        'priority': priority
    })
    
    conn.close()
    
    return jsonify({'status': 'success', 'report_id': report_id}), 201

@app.route('/api/team-reports/<int:incident_id>', methods=['GET'])
@require_user_auth
def get_team_reports_by_incident(incident_id):
    """Get all active team reports for a specific incident, sorted by newest first."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM team_reports
        WHERE incident_id = ? AND active = 1
        ORDER BY created_at DESC
    ''', (incident_id,))
    reports = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify(reports)

@app.route('/api/team-reports/recent', methods=['GET'])
@require_user_auth
def get_recent_team_reports():
    """Get recent team reports with optional filters."""
    minutes = request.args.get('minutes', type=int)
    report_type = request.args.get('type')
    priority = request.args.get('priority', type=int)
    
    conn = get_db()
    cursor = conn.cursor()
    
    query = 'SELECT * FROM team_reports WHERE active = 1'
    params = []
    
    if minutes:
        query += ' AND created_at >= datetime("now", "-" || ? || " minutes")'
        params.append(minutes)
    
    if report_type:
        query += ' AND type = ?'
        params.append(report_type)
    
    if priority:
        query += ' AND priority = ?'
        params.append(priority)
    
    query += ' ORDER BY created_at DESC'
    
    cursor.execute(query, params)
    reports = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify(reports)

@app.route('/api/team-reports/<int:report_id>', methods=['DELETE'])
@require_user_auth
def delete_team_report(report_id):
    """Soft delete a team report (set active = 0)."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM team_reports WHERE id = ?', (report_id,))
    report = cursor.fetchone()
    
    if not report:
        conn.close()
        return jsonify({'error': 'Team report not found'}), 404
    
    cursor.execute('UPDATE team_reports SET active = 0 WHERE id = ?', (report_id,))
    conn.commit()
    
    # System log
    system_log('team_report_deleted', 'user', g.user.get('user_id'), {
        'report_id': report_id,
        'team_id': report['team_id'],
        'incident_id': report['incident_id']
    })
    
    conn.close()
    
    return jsonify({'message': 'Team report deleted successfully'})

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
    
    # Parse path from JSON - engine service already returns [lat, lng]
    path = json.loads(route_data['path'])
    
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

# ============== RBAC AUTHENTICATION ENDPOINTS ==============

@app.route('/api/auth/login', methods=['POST'])
def user_login():
    """Dashboard user login - returns JWT token"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ? AND is_active = 1', (username,))
    user = cursor.fetchone()
    conn.close()
    
    if not user or not verify_password(password, user['password_hash']):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    # Generate JWT token
    token = generate_user_token(user['id'], user['role'], user['branch_id'])
    
    # Get branch name
    branch_name = None
    if user['branch_id']:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT name FROM branches WHERE id = ?', (user['branch_id'],))
        branch = cursor.fetchone()
        if branch:
            branch_name = branch['name']
        conn.close()
    
    # System logging
    system_log('login', 'user', user['id'], user, {
        'username': user['username'],
        'role': user['role'],
        'branch_id': user['branch_id']
    })
    
    return jsonify({
        'token': token,
        'user': {
            'id': user['id'],
            'username': user['username'],
            'role': user['role'],
            'branch_id': user['branch_id'],
            'branch_name': branch_name,
            'region': user['region']
        }
    })

@app.route('/api/auth/me', methods=['GET'])
@require_user_auth
def get_current_user():
    """Get current user info from JWT"""
    user = g.user
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (user['user_id'],))
    user_data = cursor.fetchone()
    conn.close()
    
    if not user_data:
        return jsonify({'error': 'User not found'}), 404
    
    return jsonify({
        'id': user_data['id'],
        'username': user_data['username'],
        'role': user_data['role'],
        'branch_id': user_data['branch_id'],
        'region': user_data['region']
    })

# ============== MOBILE TEAM AUTHENTICATION ==============

@app.route('/api/mobile/login', methods=['POST'])
def mobile_login():
    """Mobile team login - returns JWT token with 7-day expiry"""
    data = request.get_json()
    team_number = data.get('team_number')
    branch_id = data.get('branch_id')
    
    if not team_number or not branch_id:
        return jsonify({'error': 'team_number and branch_id required'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT * FROM teams WHERE team_number = ? AND branch_id = ?',
        (team_number, branch_id)
    )
    team = cursor.fetchone()
    conn.close()
    
    if not team:
        return jsonify({'error': 'Team not found in branch'}), 404
    
    # Generate team JWT token (7-day expiry)
    token = generate_team_token(team['id'], branch_id)
    
    return jsonify({
        'token': token,
        'team_id': team['id'],
        'team_number': team['team_number'],
        'branch_id': branch_id,
        'team_name': team['name'],
        'expires_in': 7 * 24 * 60 * 60  # seconds
    })

# ============== BRANCH MANAGEMENT (ADMIN ONLY) ==============

@app.route('/api/branches/public', methods=['GET'])
def get_branches_public():
    """Get active branches for mobile login (no auth required)"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, name, city, region FROM branches WHERE is_active = 1 ORDER BY name')
    branches = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify(branches)

@app.route('/api/branches', methods=['GET'])
@require_user_auth
def get_branches():
    """Get branches - admin sees all, regional_admin sees region, operator sees own branch"""
    user = g.user
    
    conn = get_db()
    cursor = conn.cursor()
    
    if user.get('role') == 'admin':
        cursor.execute('SELECT * FROM branches WHERE is_active = 1 ORDER BY name')
    elif user.get('role') == 'regional_admin':
        cursor.execute(
            'SELECT * FROM branches WHERE region = ? AND is_active = 1 ORDER BY name',
            (user.get('region'),)
        )
    else:
        # Operators and teams only see their own branch
        cursor.execute(
            'SELECT * FROM branches WHERE id = ? AND is_active = 1',
            (user.get('branch_id'),)
        )
    
    branches = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify(branches)

@app.route('/api/branches', methods=['POST'])
@require_user_auth
@require_role('admin')
def create_branch():
    """Create new branch (admin only)"""
    data = request.get_json()
    
    required = ['name', 'city', 'region', 'lat', 'lng']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO branches (name, city, region, lat, lng, geo_json, radius_km)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        data['name'], data['city'], data['region'],
        data['lat'], data['lng'], data.get('geo_json'),
        data.get('radius_km', 10)
    ))
    branch_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    try:
        log_action('created', 'branch', branch_id, None, {'name': data['name']})
    except Exception:
        pass
    
    return jsonify({'id': branch_id, 'message': 'Branch created', 'name': data['name']}), 201

@app.route('/api/events', methods=['GET'])
@require_auth
def get_events():
    """Get events relevant to user based on geographic area."""
    user = g.user
    
    # Admin sees all events
    if user.get('role') == 'admin':
        return jsonify(events)
    
    # Get branches for geo filtering
    conn = get_db()
    branches = get_branches_for_geo_filtering(conn, user)
    conn.close()
    
    if not branches:
        return jsonify([])
    
    # Filter events by geography
    filtered_events = []
    for event in events:
        for branch in branches:
            if is_in_branch_area(event['lat'], event['lng'], branch):
                filtered_events.append(event)
                break  # Match found, no need to check other branches
    
    return jsonify(filtered_events)

@app.route('/api/branches/<int:branch_id>', methods=['PATCH'])
@require_user_auth
@require_role('admin')
def update_branch(branch_id):
    """Update or soft delete branch (admin only)"""
    data = request.get_json()
    
    updates = []
    values = []
    
    for field in ['name', 'city', 'region', 'lat', 'lng', 'geo_json', 'is_active']:
        if field in data:
            updates.append(f'{field} = ?')
            values.append(data[field])
    
    if not updates:
        return jsonify({'error': 'No fields to update'}), 400
    
    values.append(datetime.now().isoformat())
    values.append(branch_id)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(f'''
        UPDATE branches SET {', '.join(updates)}, updated_at = ?
        WHERE id = ?
    ''', values)
    conn.commit()
    conn.close()
    
    log_action('updated', 'branch', branch_id, None, data)
    
    return jsonify({'message': 'Branch updated'})

@app.route('/api/branches/<int:branch_id>', methods=['DELETE'])
@require_user_auth
@require_role('admin')
def delete_branch(branch_id):
    """Delete branch (admin only)"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if branch exists
    cursor.execute('SELECT id FROM branches WHERE id = ?', (branch_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Branch not found'}), 404
    
    # Delete branch
    cursor.execute('DELETE FROM branches WHERE id = ?', (branch_id,))
    conn.commit()
    conn.close()
    
    log_action('deleted', 'branch', branch_id, None, None)
    
    return jsonify({'message': 'Branch deleted'})

# ============== USER MANAGEMENT (ADMIN ONLY) ==============

@app.route('/api/users', methods=['GET'])
@require_user_auth
@require_role('admin')
def get_users():
    """Get all users (admin only)"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, role, branch_id, region, is_active, created_at FROM users')
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(users)

@app.route('/api/users', methods=['POST'])
@require_user_auth
@require_role('admin')
def create_user():
    """Create new user (admin only)"""
    data = request.get_json()
    
    if not data.get('username') or not data.get('password'):
        return jsonify({'error': 'username and password required'}), 400
    
    if data.get('role') not in ['admin', 'regional_admin', 'operator']:
        return jsonify({'error': 'Invalid role'}), 400
    
    password_hash = hash_password(data['password'])
    
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO users (username, password_hash, role, branch_id, region)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            data['username'], password_hash, data['role'],
            data.get('branch_id'), data.get('region')
        ))
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        log_action('created', 'user', user_id, None, {'username': data['username'], 'role': data['role']})
        
        return jsonify({'id': user_id, 'message': 'User created'}), 201
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Username already exists'}), 409

@app.route('/api/users/<int:user_id>', methods=['PATCH'])
@require_user_auth
@require_role('admin')
def update_user(user_id):
    """Update or soft delete user (admin only)"""
    data = request.get_json()
    
    updates = []
    values = []
    
    for field in ['username', 'role', 'branch_id', 'region', 'is_active']:
        if field in data:
            updates.append(f'{field} = ?')
            values.append(data[field])
    
    if 'password' in data:
        updates.append('password_hash = ?')
        values.append(hash_password(data['password']))
    
    if not updates:
        return jsonify({'error': 'No fields to update'}), 400
    
    values.append(datetime.now().isoformat())
    values.append(user_id)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(f'''
        UPDATE users SET {', '.join(updates)}, updated_at = ?
        WHERE id = ?
    ''', values)
    conn.commit()
    conn.close()
    
    log_action('updated', 'user', user_id, None, data)
    
    return jsonify({'message': 'User updated'})

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@require_user_auth
@require_role('admin')
def delete_user(user_id):
    """Delete user (admin only)"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if user exists
    cursor.execute('SELECT id FROM users WHERE id = ?', (user_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': 'User not found'}), 404
    
    # Prevent deleting yourself
    if g.user.get('user_id') == user_id:
        conn.close()
        return jsonify({'error': 'Cannot delete your own account'}), 400
    
    # Delete user
    cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    
    log_action('deleted', 'user', user_id, None, None)
    
    return jsonify({'message': 'User deleted'})

# Initialize database on startup
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
