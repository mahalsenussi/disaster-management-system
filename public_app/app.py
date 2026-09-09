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
import uuid
from datetime import datetime
import os
import time
import threading
import logging
from logging.handlers import RotatingFileHandler

# Import RBAC auth module
from auth import (
    require_auth, require_user_auth, require_team_auth, require_role,
    generate_user_token, generate_team_token, hash_password, verify_password,
    apply_branch_filter, enforce_branch_on_write, log_action,
    is_in_branch_area, get_branches_for_geo_filtering,
    resolve_branch_by_location
)

app = Flask(__name__)

# GPS ping contract: the mobile "Emergency Field Ops" app sends a location
# ping every GPS_PING_INTERVAL seconds. A team is considered GPS-ACTIVE while
# pings arrive within that window (plus tolerance for one missed ping), LOST
# after that but still recently active, and OFFLINE once no ping has arrived
# for a longer period. Keep these consistent with the Flutter app's timers.
GPS_PING_INTERVAL = 30       # seconds the app waits between location pings
GPS_ACTIVE_SECONDS = 45      # gps_active while last ping < 45s (30s + 15s margin)
GPS_LOST_SECONDS = 180       # gps_lost between 45s and 180s; offline after
CORS(app)  # Enable CORS for all routes

# Configuration
DATABASE = os.path.join(os.path.dirname(__file__), 'database', 'disaster_ops.db')
ENGINE_API_URL = os.environ.get('ENGINE_API_URL', 'http://localhost:5002/route')
EVALUATION_API_URL = os.environ.get('EVALUATION_API_URL', 'http://localhost:5006')
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

    # Team destinations table (management-sent navigation points)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS team_destinations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            label TEXT,
            created_by INTEGER,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (team_id) REFERENCES teams(id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_team_dest_team ON team_destinations(team_id, status)')
    
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
    
    # Points of interest table (imported from public geo sources: OSM/HDX/ArcGIS)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS points_of_interest (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            category TEXT NOT NULL,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            osm_type TEXT,
            osm_id TEXT,
            address TEXT,
            phone TEXT,
            website TEXT,
            source TEXT DEFAULT 'osm',
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_poi_category ON points_of_interest(category)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_poi_location ON points_of_interest(lat, lng)')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_poi_osm ON points_of_interest(osm_type, osm_id)')

    # ---- Reports & Intelligence add-on migrations ----

    # POI extra columns (guarded for existing DBs)
    for column, ddl in [
        ('category_data', 'category_data TEXT'),
        ('verified', 'verified INTEGER DEFAULT 0'),
        ('modified_by', 'modified_by INTEGER'),
        ('notes', 'notes TEXT'),
    ]:
        existing = [r[1] for r in cursor.execute(f'PRAGMA table_info(points_of_interest)').fetchall()]
        if column not in existing:
            cursor.execute(f'ALTER TABLE points_of_interest ADD COLUMN {ddl}')

    # Per-category POI field definitions (dynamic forms per category)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS poi_category_schemas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            field_key TEXT NOT NULL,
            field_label TEXT NOT NULL,
            field_type TEXT NOT NULL,
            unit TEXT,
            options_json TEXT,
            required INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            UNIQUE(category, field_key)
        )
    ''')

    # Audit trail for POI edits
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS poi_change_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            poi_id INTEGER NOT NULL,
            user_id INTEGER,
            field TEXT,
            old_value TEXT,
            new_value TEXT,
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Daily SITREP reports from branches (disaster-management cells)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_id INTEGER NOT NULL,
            report_date TEXT NOT NULL,
            submitted_by INTEGER,
            summary TEXT,
            branch_status TEXT CHECK(branch_status IN ('normal','alert','critical')) DEFAULT 'normal',
            needs TEXT,
            attachments_json TEXT,
            status TEXT DEFAULT 'submitted',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(branch_id, report_date)
        )
    ''')

    # Individual intel/source sections within a daily report
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_report_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL,
            section TEXT NOT NULL,
            source_category TEXT,
            content TEXT,
            incident_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Attachments (photos/docs) for daily reports
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS report_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL,
            attachment_type TEXT DEFAULT 'image',
            file_path TEXT,
            url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # HQ follow-up decisions on reported items
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS followups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_id INTEGER NOT NULL,
            report_id INTEGER,
            item TEXT NOT NULL,
            assigned_to INTEGER,
            due_date TEXT,
            status TEXT CHECK(status IN ('open','in_progress','resolved','closed')) DEFAULT 'open',
            decision TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # AI analysis summaries storage
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS analysis_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            category TEXT,
            branch_id INTEGER,
            period_start TEXT,
            period_end TEXT,
            model TEXT,
            summary_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_daily_reports_branch_date ON daily_reports(branch_id, report_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_daily_items_report ON daily_report_items(report_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_followups_status_due ON followups(status, due_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_summaries_kind ON analysis_summaries(kind, category)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_poi_schemas_category ON poi_category_schemas(category)')

    # Seed default per-category schemas so editor forms work out of the box
    seed_poi_schemas(cursor)

    # Rebuild users table CHECK if it doesn't allow new roles yet (SQLite can't ALTER CHECKs)
    old_users_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
    if old_users_sql and "'analyst'" not in (old_users_sql[0] or ''):
        conn.executescript('''
            CREATE TABLE users_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin','regional_admin','operator','data_entry','analyst')),
                branch_id INTEGER,
                region TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO users_new (id, username, password_hash, role, branch_id, region, is_active, created_at, updated_at)
                SELECT id, username, password_hash, role, branch_id, region, is_active, created_at, updated_at FROM users;
            DROP TABLE users;
            ALTER TABLE users_new RENAME TO users;
        ''')

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

# ============== POI per-category schemas ==============

DEFAULT_POI_SCHEMAS = {
    'hospital': [
        ('beds_total', 'Total Beds', 'number', 'beds', 1, 1),
        ('beds_available', 'Available Beds', 'number', 'beds', 1, 2),
        ('capacity_pct', 'Capacity %', 'percent', '%', 1, 3),
        ('ambulance_units', 'Ambulance Units', 'number', 'units', 1, 4),
        ('status', 'Status', 'select', None, 1, 5, '["operational","reduced","non_operational","unknown"]'),
        ('notes', 'Operational Notes', 'textarea', None, 0, 6),
    ],
    'clinic': [
        ('has_emergency', 'Emergency Services', 'boolean', None, 0, 1),
        ('capacity_pct', 'Capacity %', 'percent', '%', 0, 2),
        ('staff_status', 'Staff Status', 'select', None, 0, 3, '["full","partial","low","unknown"]'),
    ],
    'pharmacy': [
        ('open_now', 'Open Now', 'boolean', None, 0, 1),
        ('stock_status', 'Stock Status', 'select', None, 0, 2, '["well_stocked","limited","critical","unknown"]'),
    ],
    'detention': [
        ('capacity', 'Capacity', 'number', 'persons', 1, 1),
        ('vacancy_pct', 'Vacancy %', 'percent', '%', 1, 2),
        ('occupancy_pct', 'Occupancy %', 'percent', '%', 1, 3),
        ('status', 'Status', 'select', None, 1, 4, '["operational","over_capacity","at_capacity","unknown"]'),
    ],
    'shelter': [
        ('capacity', 'Capacity', 'number', 'persons', 1, 1),
        ('occupancy_pct', 'Occupancy %', 'percent', '%', 1, 2),
        ('has_water', 'Water Supply', 'boolean', None, 0, 3),
        ('has_power', 'Power Supply', 'boolean', None, 0, 4),
    ],
    'school': [
        ('students', 'Students', 'number', 'students', 0, 1),
        ('shelter_capacity', 'Shelter Capacity', 'number', 'persons', 0, 2),
        ('usable_as_shelter', 'Usable as Shelter', 'boolean', None, 0, 3),
    ],
    'fuel': [
        ('availability', 'Fuel Availability', 'select', None, 1, 1, '["available","limited","out_of_stock","unknown"]'),
        ('fuel_type', 'Fuel Types', 'text', None, 0, 2),
    ],
    'bank': [
        ('open_now', 'Open Now', 'boolean', None, 0, 1),
        ('cash_status', 'Cash Status', 'select', None, 0, 2, '["normal","limited","no_cash","unknown"]'),
    ],
    'government': [
        ('contact_office', 'Contact Office', 'text', None, 0, 1),
        ('working_hours', 'Working Hours', 'text', None, 0, 2),
    ],
}

FIELD_TYPES = ('text', 'textarea', 'number', 'percent', 'select', 'boolean')

def seed_poi_schemas(cursor):
    """Insert default field definitions for categories that have none yet."""
    defined = {row[0] for row in cursor.execute(
        'SELECT DISTINCT category FROM poi_category_schemas').fetchall()}
    for category, fields in DEFAULT_POI_SCHEMAS.items():
        if category in defined:
            continue
        for field_key, label, ftype, unit, required, sort_order, *rest in fields:
            options_json = rest[0] if rest else None
            cursor.execute('''
                INSERT OR IGNORE INTO poi_category_schemas
                    (category, field_key, field_label, field_type, unit, options_json, required, sort_order)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (category, field_key, label, ftype, unit, options_json, required, sort_order))

def get_poi_schema(conn, category):
    """Return ordered list of field definitions for a category."""
    rows = conn.execute(
        'SELECT * FROM poi_category_schemas WHERE category = ? AND is_active = 1 '
        'ORDER BY sort_order, id', (category,)
    ).fetchall()
    return [dict(r) for r in rows]

def validate_poi_data(conn, category, data):
    """Validate/normalize category_data against the category schema.
    Returns (normalized_dict_or_None, error_message_or_None)."""
    if data is None:
        return None, None
    if not isinstance(data, dict):
        return None, 'category_data must be a JSON object'
    schema = get_poi_schema(conn, category)
    if not schema:
        return data, None  # no schema defined yet - accept as-is
    normalized = {}
    for field in schema:
        key = field['field_key']
        value = data.get(key)
        if value in (None, ''):
            if field.get('required'):
                return None, f"'{key}' is required for {category}"
            continue
        ftype = field['field_type']
        try:
            if ftype in ('number', 'percent'):
                value = float(value)
                if ftype == 'percent' and not (0 <= value <= 100):
                    return None, f"'{key}' must be between 0 and 100"
            elif ftype == 'boolean':
                if isinstance(value, str):
                    value = value.lower() in ('1', 'true', 'yes', 'on')
                value = bool(value)
            elif ftype == 'select':
                options = json.loads(field.get('options_json') or '[]')
                if options and str(value) not in options:
                    return None, f"'{key}' must be one of: {', '.join(options)}"
                value = str(value)
        except (ValueError, TypeError):
            return None, f"'{key}' has an invalid value"
        normalized[key] = value
    # Unknown keys are dropped silently to keep data clean
    return normalized, None

# ============== Analytics / AI helpers ==============

def row_to_dict(row):
    if row is None:
        return None
    return dict(row)

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

@app.route('/reports')
def reports_page():
    """Serve the Reports & Intelligence page (auth handled by frontend)."""
    return render_template('reports.html')

@app.route('/api/incidents', methods=['GET'])
@require_auth
def get_incidents():
    """Get incidents - filtered by GEOGRAPHIC area for operators, regional_admin, teams."""
    conn = get_db()
    cursor = conn.cursor()
    
    user = g.user
    
    # Admin/analyst sees all incidents (non-archived)
    if user.get('role') in ('admin', 'analyst'):
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
        
        # Operators are geofenced to their branch operational area (radius_km, default 10)
        if g.user.get('role') == 'operator':
            conn = get_db()
            branch = conn.execute(
                'SELECT id, name, lat, lng, radius_km FROM branches WHERE id = ?',
                (data.get('branch_id'),)
            ).fetchone()
            conn.close()
            if branch and not is_in_branch_area(data.get('lat'), data.get('lng'), dict(branch)):
                radius_km = branch['radius_km'] or 10
                return jsonify({
                    'error': f'Incident is outside your branch operational area ({int(radius_km)} km radius)'
                }), 403
        
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
    
    if user.get('role') in ('admin', 'analyst'):
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
                
                if diff_seconds < GPS_ACTIVE_SECONDS:
                    team['gps_state'] = 'gps_active'
                elif diff_seconds < GPS_LOST_SECONDS:
                    team['gps_state'] = 'gps_lost'
                else:
                    team['gps_state'] = 'offline'
            
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
                    
                    if diff_seconds < GPS_ACTIVE_SECONDS:
                        team['gps_state'] = 'gps_active'
                    elif diff_seconds < GPS_LOST_SECONDS:
                        team['gps_state'] = 'gps_lost'
                    else:
                        team['gps_state'] = 'offline'
                
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

@app.route('/api/routes/to-point', methods=['POST'])
@require_team_auth
def route_to_point():
    """Ad-hoc route from the team's current position (or given origin) to an
    arbitrary destination point (e.g. a hospital, shelter or any map point sent
    by management). Uses the OSRM engine with a straight-line fallback.
    """
    try:
        data = request.get_json() or {}
        destination = data.get('destination')
        origin = data.get('origin')

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT lat, lng FROM teams WHERE id = ?', (g.user['team_id'],))
        team = cursor.fetchone()

        if not origin or origin.get('lat') is None or origin.get('lng') is None:
            if not team:
                conn.close()
                return jsonify({'error': 'Team not found'}), 404
            origin = {'lat': team['lat'], 'lng': team['lng']}
        conn.close()

        if not destination or destination.get('lat') is None or destination.get('lng') is None:
            return jsonify({'error': 'destination.lat and destination.lng are required'}), 400

        valid, coords_error = validate_coordinates(origin['lat'], origin['lng'])
        if not valid:
            return jsonify({'error': coords_error}), 400
        valid, coords_error = validate_coordinates(destination['lat'], destination['lng'])
        if not valid:
            return jsonify({'error': coords_error}), 400

        engine_payload = {
            'team': {'lat': origin['lat'], 'lng': origin['lng']},
            'incident': {'lat': destination['lat'], 'lng': destination['lng']},
            'road_blocks': []
        }
        response = requests.post(ENGINE_API_URL, json=engine_payload, timeout=10)
        response.raise_for_status()
        route_data = response.json()

        return jsonify({
            'path': route_data.get('path', []),
            'distance': route_data.get('distance', 0),
            'distance_m': route_data.get('distance_m', 0),
            'duration': route_data.get('duration', 0),
            'source': route_data.get('source', 'osrm')
        })
    except requests.exceptions.RequestException as e:
        system_logger.error(f"Failed to call engine API (to-point): {e}")
        return jsonify({'error': f'Failed to call engine API: {str(e)}'}), 500
    except Exception as e:
        system_logger.error(f"Internal server error in route_to_point: {e}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@app.route('/api/teams/<int:team_id>/destination', methods=['POST'])
@require_auth
def send_team_destination(team_id):
    """Management sends an arbitrary map point to a team (e.g. hospital, shelter,
    staging point). Replaces any previously active destination for that team."""
    data = request.get_json() or {}
    lat = data.get('lat')
    lng = data.get('lng')
    label = (data.get('label') or '').strip()

    if lat is None or lng is None:
        return jsonify({'error': 'lat and lng are required'}), 400

    valid, coords_error = validate_coordinates(lat, lng)
    if not valid:
        return jsonify({'error': coords_error}), 400

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('SELECT id, name FROM teams WHERE id = ?', (team_id,))
    team = cursor.fetchone()
    if not team:
        conn.close()
        return jsonify({'error': 'Team not found'}), 404

    cursor.execute(
        "UPDATE team_destinations SET status = 'superseded' WHERE team_id = ? AND status = 'active'",
        (team_id,)
    )
    cursor.execute(
        'INSERT INTO team_destinations (team_id, lat, lng, label, created_by) VALUES (?, ?, ?, ?, ?)',
        (team_id, float(lat), float(lng), label or None, g.user.get('user_id'))
    )
    dest_id = cursor.lastrowid
    system_log('team_destination_sent', 'user', g.user.get('user_id'), {
        'destination_id': dest_id,
        'team_id': team_id,
        'lat': lat, 'lng': lng, 'label': label
    })
    conn.commit()
    conn.close()

    return jsonify({
        'message': 'Destination sent to team',
        'destination': {
            'id': dest_id,
            'team_id': team_id,
            'team_name': team['name'],
            'lat': lat, 'lng': lng, 'label': label
        }
    }), 201

@app.route('/api/teams/<int:team_id>/destination', methods=['GET'])
@require_team_auth
def get_team_destination(team_id):
    """Polled by a team's Field Ops app to receive management-sent destinations."""
    if int(team_id) != int(g.user['team_id']):
        return jsonify({'error': 'Unauthorized'}), 403

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM team_destinations WHERE team_id = ? AND status = 'active' "
        'ORDER BY created_at DESC LIMIT 1',
        (team_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({'active': False})
    return jsonify({
        'active': True,
        'id': row['id'],
        'lat': row['lat'],
        'lng': row['lng'],
        'label': row['label'],
        'created_at': row['created_at']
    })

@app.route('/api/routes', methods=['GET'])
@require_auth
def get_routes():
    """Get routes - filtered by GEOGRAPHIC area for operators, regional_admin, teams."""
    conn = get_db()
    cursor = conn.cursor()
    
    user = g.user
    
    # Admin/analyst see all routes
    if user.get('role') in ('admin', 'analyst'):
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
    """Mobile team login - returns JWT token with 7-day expiry.
    Branch is auto-detected from GPS location (lat/lng) when provided,
    so teams can share areas across branches. Falls back to branch_id.
    """
    data = request.get_json()
    team_number = data.get('team_number')
    lat = data.get('lat')
    lng = data.get('lng')
    branch_id = data.get('branch_id')

    if not team_number:
        return jsonify({'error': 'team_number required'}), 400

    conn = get_db()
    geo_assigned = None
    branch = None

    if lat is not None and lng is not None:
        valid, coords_error = validate_coordinates(lat, lng)
        if not valid:
            conn.close()
            return jsonify({'error': coords_error}), 400
        resolved = resolve_branch_by_location(conn, float(lat), float(lng))
        if not resolved:
            conn.close()
            return jsonify({'error': 'No active branches configured'}), 500
        branch = resolved['branch']
        branch_id = branch['id']
        geo_assigned = resolved['match_type']

    if branch_id is None:
        conn.close()
        return jsonify({'error': 'branch_id required (or lat/lng for geo detection)'}), 400

    cursor = conn.cursor()
    # Prefer team whose home branch matches the active area, else any team
    # with this team_number (supports teams shared between areas).
    cursor.execute(
        'SELECT * FROM teams WHERE team_number = ? '
        'ORDER BY (branch_id = ?) DESC, id ASC LIMIT 1',
        (str(team_number).strip(), branch_id)
    )
    team = cursor.fetchone()
    if not team:
        cursor.execute(
            'SELECT * FROM teams WHERE team_number = ? AND branch_id = ?',
            (str(team_number).strip(), branch_id)
        )
        team = cursor.fetchone()
    if team:
        # A logged-in team starts live GPS tracking, even if it was in manual
        # movement mode (gps_enabled=0, e.g. position set from the dashboard).
        cursor.execute(
            'UPDATE teams SET gps_enabled = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            (team['id'],)
        )
    conn.commit()
    conn.close()

    if not team:
        return jsonify({'error': 'Team not found'}), 404

    # Generate team JWT token (7-day expiry) for the active area
    token = generate_team_token(team['id'], branch_id)

    response = {
        'token': token,
        'team_id': team['id'],
        'team_number': team['team_number'],
        'branch_id': branch_id,
        'team_name': team['name'],
        'expires_in': 7 * 24 * 60 * 60  # seconds
    }
    if branch:
        response['branch_name'] = branch['name']
        response['branch_city'] = branch['city']
        response['branch_region'] = branch['region']
    if geo_assigned:
        response['geo_assigned'] = geo_assigned

    return jsonify(response)

@app.route('/api/branches/geo-locate', methods=['GET'])
def geo_locate_branch():
    """Detect the branch covering a GPS point (no auth required).
    Used by the mobile app to auto-assign the team's area on login."""
    lat = request.args.get('lat')
    lng = request.args.get('lng')

    if lat is None or lng is None:
        return jsonify({'error': 'lat and lng query params required'}), 400

    valid, coords_error = validate_coordinates(lat, lng)
    if not valid:
        return jsonify({'error': coords_error}), 400

    conn = get_db()
    resolved = resolve_branch_by_location(conn, float(lat), float(lng))
    conn.close()

    if not resolved:
        return jsonify({'error': 'No active branches configured'}), 500

    branch = resolved['branch']
    return jsonify({
        'id': branch['id'],
        'name': branch['name'],
        'city': branch['city'],
        'region': branch['region'],
        'radius_km': branch.get('radius_km') or 10,
        'distance_km': branch.get('distance_km'),
        'match_type': resolved['match_type']
    })

@app.route('/api/pois', methods=['GET'])
@require_auth
def get_points_of_interest():
    """Get points of interest (POIs).
    Teams/operators see POIs within their branch area (geo-filtered).
    Admin sees all of Libya unless bbox is provided.
    Optional params: category (comma-separated), bbox (minLat,minLng,maxLat,maxLng),
    q (name search), limit (default 1000).
    """
    user = g.user

    category_param = request.args.get('category', '')
    categories = [c.strip() for c in category_param.split(',') if c.strip()]
    q = request.args.get('q', '').strip()
    limit = min(int(request.args.get('limit', 1000)), 5000)

    bbox = None
    bbox_param = request.args.get('bbox', '')
    if bbox_param:
        parts = [float(p) for p in bbox_param.split(',')]
        if len(parts) == 4:
            bbox = parts  # minLat, minLng, maxLat, maxLng

    conn = get_db()
    cursor = conn.cursor()

    where = ['is_active = 1']
    values = []

    if categories:
        where.append(f"category IN ({','.join('?' * len(categories))})")
        values.extend(categories)

    if q:
        where.append('(name LIKE ? OR address LIKE ?)')
        values.extend([f'%{q}%', f'%{q}%'])

    if bbox:
        where.append('lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?')
        values.extend([bbox[0], bbox[2], bbox[1], bbox[3]])

    sql = f'SELECT * FROM points_of_interest WHERE {" AND ".join(where)}'

    # Non-admin/analyst users are geo-filtered to their branches
    if user.get('role') not in ('admin', 'analyst'):
        branches = get_branches_for_geo_filtering(conn, user)
        rows = []
        if branches:
            # Fetch without LIMIT so geo filtering happens before truncation
            cursor.execute(sql + ' ORDER BY category, name', values)
            for row in cursor.fetchall():
                for branch in branches:
                    if is_in_branch_area(row['lat'], row['lng'], branch):
                        item = dict(row)
                        item['category_data'] = json.loads(item['category_data']) if item.get('category_data') else None
                        rows.append(item)
                        break
                if len(rows) >= limit:
                    break
        conn.close()
        return jsonify(rows)

    sql += ' ORDER BY category, name LIMIT ?'
    values.append(limit)
    cursor.execute(sql, values)
    rows = [dict(row) for row in cursor.fetchall()]
    for item in rows:
        item['category_data'] = json.loads(item['category_data']) if item.get('category_data') else None
    conn.close()

    return jsonify(rows)

# ============== POI MANAGEMENT (Reports & Intelligence add-on) ==============

@app.route('/api/pois/<int:poi_id>', methods=['GET'])
@require_auth
def get_poi_detail(poi_id):
    """Get a single POI with parsed category_data."""
    conn = get_db()
    row = conn.execute('SELECT * FROM points_of_interest WHERE id = ?', (poi_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'POI not found'}), 404
    item = dict(row)
    item['category_data'] = json.loads(item['category_data']) if item.get('category_data') else None
    return jsonify(item)

def _require_poi_editor():
    """POI edits are allowed for dashboard users with editor roles."""
    if g.user.get('type') != 'user' or g.user.get('role') not in ('admin', 'analyst', 'data_entry'):
        return False
    return True

def _log_poi_change(conn, poi_id, field, old_value, new_value):
    try:
        conn.execute('''
            INSERT INTO poi_change_log (poi_id, user_id, field, old_value, new_value)
            VALUES (?, ?, ?, ?, ?)
        ''', (poi_id, g.user.get('user_id'), field,
              json.dumps(old_value, ensure_ascii=False) if old_value not in (None, '') else None,
              json.dumps(new_value, ensure_ascii=False) if new_value not in (None, '') else None))
    except Exception:
        pass

@app.route('/api/pois', methods=['POST'])
@require_auth
def create_poi():
    """Create a custom point of interest (source='custom'). Editors only."""
    if not _require_poi_editor():
        return jsonify({'error': 'You do not have permission to add POIs'}), 403
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    category = (data.get('category') or '').strip()
    if not category:
        return jsonify({'error': 'category is required'}), 400
    valid, err = validate_coordinates(data.get('lat'), data.get('lng'))
    if not valid:
        return jsonify({'error': err}), 400

    conn = get_db()
    normalized, verr = validate_poi_data(conn, category, data.get('category_data'))
    if verr:
        conn.close()
        return jsonify({'error': verr}), 400

    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO points_of_interest
                (name, category, lat, lng, address, phone, website, category_data,
                 source, verified, notes, modified_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'custom', ?, ?, ?)
        ''', (
            name or None, category, float(data['lat']), float(data['lng']),
            data.get('address'), data.get('phone'), data.get('website'),
            json.dumps(normalized, ensure_ascii=False) if normalized else None,
            1 if data.get('verified', True) else 0,
            data.get('notes'), g.user.get('user_id'),
        ))
        poi_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return jsonify({'id': poi_id, 'message': 'POI created'}), 201
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'A POI with this OSM reference already exists'}), 409

@app.route('/api/pois/<int:poi_id>', methods=['PATCH'])
@require_auth
def update_poi(poi_id):
    """Update a POI (rename, move, re-categorize, status data, verify, hide)."""
    if not _require_poi_editor():
        return jsonify({'error': 'You do not have permission to edit POIs'}), 403
    data = request.get_json() or {}
    conn = get_db()
    cursor = conn.cursor()
    row = cursor.execute('SELECT * FROM points_of_interest WHERE id = ?', (poi_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'POI not found'}), 404
    existing = dict(row)

    # Category change requires re-validating against the new schema
    new_category = data.get('category', existing['category'])
    if data.get('category_data') is not None:
        normalized, verr = validate_poi_data(conn, new_category, data.get('category_data'))
        if verr:
            conn.close()
            return jsonify({'error': verr}), 400
    else:
        normalized = json.loads(existing['category_data']) if existing.get('category_data') else None

    if data.get('lat') is not None or data.get('lng') is not None:
        lat = data.get('lat', existing['lat'])
        lng = data.get('lng', existing['lng'])
        valid, err = validate_coordinates(lat, lng)
        if not valid:
            conn.close()
            return jsonify({'error': err}), 400
    else:
        lat, lng = existing['lat'], existing['lng']

    new_name = data.get('name', existing['name'])
    new_address = data.get('address', existing['address'])
    new_notes = data.get('notes', existing['notes'])

    updated_at = datetime.now().isoformat()
    cursor.execute('''
        UPDATE points_of_interest SET
            name = ?, category = ?, lat = ?, lng = ?, address = ?,
            phone = COALESCE(?, phone), website = COALESCE(?, website),
            notes = ?, category_data = ?,
            modified_by = ?, updated_at = ?
        WHERE id = ?
    ''', (
        new_name, new_category, lat, lng, new_address,
        data.get('phone'), data.get('website'),
        new_notes, json.dumps(normalized, ensure_ascii=False) if normalized else None,
        g.user.get('user_id'), updated_at, poi_id,
    ))

    for field, old_v, new_v in [
        ('name', existing['name'], new_name),
        ('category', existing['category'], new_category),
        ('address', existing['address'], new_address),
        ('coordinates', f"{existing['lat']},{existing['lng']}", f"{lat},{lng}"),
        ('category_data', existing.get('category_data'),
         json.dumps(normalized, ensure_ascii=False) if normalized else None),
        ('notes', existing.get('notes'), new_notes),
    ]:
        if old_v != new_v:
            _log_poi_change(conn, poi_id, field, old_v, new_v)
    conn.commit()

    if data.get('is_active') is not None:
        cursor.execute('UPDATE points_of_interest SET is_active = ?, modified_by = ? WHERE id = ?',
                       (1 if data.get('is_active') else 0, g.user.get('user_id'), poi_id))
        _log_poi_change(conn, poi_id, 'is_active', existing.get('is_active'), data.get('is_active'))
        conn.commit()

    conn.close()
    return jsonify({'id': poi_id, 'message': 'POI updated'})

@app.route('/api/pois/<int:poi_id>', methods=['DELETE'])
@require_auth
def delete_poi(poi_id):
    """Soft-delete a POI (hidden from listings, OSM row kept for uniqueness)."""
    if not _require_poi_editor():
        return jsonify({'error': 'You do not have permission to delete POIs'}), 403
    conn = get_db()
    cur = conn.execute('SELECT is_active FROM points_of_interest WHERE id = ?', (poi_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'POI not found'}), 404
    conn.execute('UPDATE points_of_interest SET is_active = 0, modified_by = ? WHERE id = ?',
                 (g.user.get('user_id'), poi_id))
    _log_poi_change(conn, poi_id, 'is_active', row[0], 0)
    conn.commit()
    conn.close()
    return jsonify({'id': poi_id, 'message': 'POI hidden'})

@app.route('/api/pois/<int:poi_id>/verify', methods=['POST'])
@require_auth
def verify_poi(poi_id):
    """Mark a POI as verified (checked against real-world status)."""
    if not _require_poi_editor():
        return jsonify({'error': 'No permission to verify POIs'}), 403
    conn = get_db()
    cur = conn.execute('SELECT verified FROM points_of_interest WHERE id = ?', (poi_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'POI not found'}), 404
    conn.execute('UPDATE points_of_interest SET verified = 1, modified_by = ? WHERE id = ?',
                 (g.user.get('user_id'), poi_id))
    _log_poi_change(conn, poi_id, 'verified', row[0], 1)
    conn.commit()
    conn.close()
    return jsonify({'id': poi_id, 'message': 'POI verified'})

# ============== POI CATEGORY SCHEMAS ==============

@app.route('/api/poi-schemas', methods=['GET'])
@require_auth
def get_poi_schemas():
    """List per-category field schemas grouped by category."""
    conn = get_db()
    if request.args.get('category'):
        rows = conn.execute(
            'SELECT * FROM poi_category_schemas WHERE category = ? AND is_active = 1 ORDER BY sort_order, id',
            (request.args['category'],)
        ).fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
    rows = conn.execute('SELECT * FROM poi_category_schemas WHERE is_active = 1 ORDER BY category, sort_order, id').fetchall()
    conn.close()
    grouped = {}
    for r in rows:
        grouped.setdefault(r['category'], []).append(dict(r))
    return jsonify(grouped)

@app.route('/api/poi-schemas', methods=['POST'])
@require_user_auth
@require_role('admin', 'analyst')
def create_poi_schema():
    """Add a field definition to a category form."""
    data = request.get_json() or {}
    category = (data.get('category') or '').strip()
    field_key = (data.get('field_key') or '').strip()
    label = (data.get('field_label') or '').strip()
    ftype = (data.get('field_type') or '').strip()
    if not category or not field_key or not label or ftype not in FIELD_TYPES:
        return jsonify({'error': 'category, field_key, field_label and a valid field_type are required'}), 400
    conn = get_db()
    try:
        conn.execute('''
            INSERT INTO poi_category_schemas
                (category, field_key, field_label, field_type, unit, options_json, required, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (category, field_key, label, ftype, data.get('unit'),
              json.dumps(data.get('options')) if data.get('options') else None,
              1 if data.get('required') else 0, int(data.get('sort_order') or 0)))
        conn.commit()
        field_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        conn.close()
        return jsonify({'id': field_id, 'message': 'Schema field added'}), 201
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': f"field_key '{field_key}' already exists for {category}"}), 409

@app.route('/api/poi-schemas/<int:field_id>', methods=['PATCH'])
@require_user_auth
@require_role('admin', 'analyst')
def update_poi_schema(field_id):
    data = request.get_json() or {}
    conn = get_db()
    if not conn.execute('SELECT 1 FROM poi_category_schemas WHERE id = ?', (field_id,)).fetchone():
        conn.close()
        return jsonify({'error': 'Schema field not found'}), 404
    allowed = {}
    for field in ('field_label', 'field_type', 'unit', 'required', 'sort_order', 'is_active'):
        if field in data:
            allowed[field] = data[field]
    if data.get('options') is not None:
        allowed['options_json'] = json.dumps(data['options'])
    if not allowed:
        conn.close()
        return jsonify({'error': 'No fields to update'}), 400
    sets = ', '.join(f'{k} = ?' for k in allowed)
    conn.execute(f'UPDATE poi_category_schemas SET {sets} WHERE id = ?',
                 [*allowed.values(), field_id])
    conn.commit()
    conn.close()
    return jsonify({'id': field_id, 'message': 'Schema field updated'})

@app.route('/api/poi-schemas/<int:field_id>', methods=['DELETE'])
@require_user_auth
@require_role('admin', 'analyst')
def delete_poi_schema(field_id):
    conn = get_db()
    conn.execute('UPDATE poi_category_schemas SET is_active = 0 WHERE id = ?', (field_id,))
    conn.commit()
    conn.close()
    return jsonify({'id': field_id, 'message': 'Schema field removed'})

# ============== DAILY BRANCH REPORTS (SITREP) ==============

REPORT_SECTIONS = ('weather', 'government', 'health', 'roads', 'security', 'other')

def _allowed_branch_ids(conn, user):
    """Branch ids visible to the current user (all for admin/analyst)."""
    if user.get('type') == 'team':
        return [user.get('branch_id')]
    if user.get('role') in ('admin', 'analyst'):
        return None  # all
    if user.get('role') == 'regional_admin':
        rows = conn.execute('SELECT id FROM branches WHERE region = ? AND is_active = 1',
                            (user.get('region'),)).fetchall()
        return [r[0] for r in rows]
    return [user.get('branch_id')]  # operator / data_entry

@app.route('/api/daily-reports', methods=['GET'])
@require_auth
def get_daily_reports():
    """List daily SITREP reports (role-geo-filtered). Filters: branch_id, from, to, status."""
    conn = get_db()
    allowed = _allowed_branch_ids(conn, g.user)
    where = []
    values = []
    branch_id = request.args.get('branch_id', type=int)
    if allowed is not None:
        where.append('branch_id IN (%s)' % ','.join('?' * len(allowed)))
        values.extend(allowed)
    elif branch_id:
        where.append('branch_id = ?')
        values.append(branch_id)
    if request.args.get('from'):
        where.append('report_date >= ?')
        values.append(request.args['from'])
    if request.args.get('to'):
        where.append('report_date <= ?')
        values.append(request.args['to'])
    if request.args.get('status'):
        where.append('status = ?')
        values.append(request.args['status'])
    sql = 'SELECT * FROM daily_reports'
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY report_date DESC, id DESC'
    rows = [dict(r) for r in conn.execute(sql, values).fetchall()]
    conn.close()
    return jsonify(rows)

def _get_daily_report_data(conn, report_id, allowed=None):
    """Fetch one report with items + follow-ups as a plain dict (or None)."""
    row = conn.execute('SELECT * FROM daily_reports WHERE id = ?', (report_id,)).fetchone()
    if not row:
        return None
    if allowed is not None and row['branch_id'] not in allowed:
        return False
    report = dict(row)
    if report.get('attachments_json'):
        report['attachments'] = json.loads(report['attachments_json'])
    report['items'] = [dict(r) for r in conn.execute(
        'SELECT * FROM daily_report_items WHERE report_id = ? ORDER BY id', (report_id,))]
    report['followups'] = [dict(r) for r in conn.execute(
        'SELECT * FROM followups WHERE report_id = ? ORDER BY id', (report_id,))]
    return report

@app.route('/api/daily-reports/<int:report_id>', methods=['GET'])
@require_auth
def get_daily_report(report_id):
    """Get one report with its items and follow-ups."""
    conn = get_db()
    allowed = _allowed_branch_ids(conn, g.user)
    report = _get_daily_report_data(conn, report_id, allowed=allowed)
    conn.close()
    if report is None:
        return jsonify({'error': 'Report not found'}), 404
    if report is False:
        return jsonify({'error': 'Not allowed to view this report'}), 403
    return jsonify(report)

@app.route('/api/daily-reports', methods=['POST'])
@require_auth
def create_daily_report():
    """Create (or upsert-for-date) a daily SITREP with its item sections."""
    data = request.get_json() or {}
    data = enforce_branch_on_write(data)
    branch_id = data.get('branch_id')
    if not branch_id:
        return jsonify({'error': 'branch_id is required'}), 400
    report_date = data.get('report_date') or datetime.now().strftime('%Y-%m-%d')
    branch_status = data.get('branch_status') or 'normal'
    if branch_status not in ('normal', 'alert', 'critical'):
        return jsonify({'error': 'branch_status must be normal, alert or critical'}), 400
    if data.get('branch_status') and g.user.get('type') == 'team':
        return jsonify({'error': 'Teams cannot submit branch reports'}), 403

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO daily_reports
            (branch_id, report_date, submitted_by, summary, branch_status, needs, status, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 'submitted', CURRENT_TIMESTAMP)
        ON CONFLICT(branch_id, report_date) DO UPDATE SET
            summary = excluded.summary,
            branch_status = excluded.branch_status,
            needs = excluded.needs,
            submitted_by = excluded.submitted_by,
            status = 'submitted',
            updated_at = CURRENT_TIMESTAMP
    ''', (branch_id, report_date,
          g.user.get('user_id') if g.user.get('type') == 'user' else None,
          data.get('summary'), branch_status, data.get('needs')))
    report_id = cursor.lastrowid
    if report_id == 0:
        report_id = conn.execute(
            'SELECT id FROM daily_reports WHERE branch_id = ? AND report_date = ?',
            (branch_id, report_date)).fetchone()[0]

    # Replace the item sections for this report
    conn.execute('DELETE FROM daily_report_items WHERE report_id = ?', (report_id,))
    items = data.get('items') or []
    for item in items:
        section = (item.get('section') or item.get('category') or 'other').strip()
        if section in REPORT_SECTIONS or section == 'key_incidents' or section == 'actions':
            conn.execute('''
                INSERT INTO daily_report_items (report_id, section, source_category, content, incident_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (report_id, section, item.get('source_category'), item.get('content'),
                  item.get('incident_id')))
    conn.commit()
    report = _get_daily_report_data(conn, report_id)
    conn.close()
    return jsonify({'id': report_id, 'message': 'Daily report saved', 'report': report}), 201

@app.route('/api/daily-reports/<int:report_id>', methods=['PATCH'])
@require_auth
def update_daily_report(report_id):
    """Update report status/summary (analyst can mark discussed/reviewed)."""
    data = request.get_json() or {}
    conn = get_db()
    row = conn.execute('SELECT * FROM daily_reports WHERE id = ?', (report_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Report not found'}), 404
    updates, values = [], []
    for field in ('summary', 'needs', 'branch_status', 'status', 'attachments_json'):
        if field in data:
            updates.append(f'{field} = ?')
            values.append(data[field])
    if not updates:
        conn.close()
        return jsonify({'error': 'No fields to update'}), 400
    values.append(report_id)
    conn.execute(f'UPDATE daily_reports SET {", ".join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?', values)
    conn.commit()
    conn.close()
    return jsonify({'id': report_id, 'message': 'Daily report updated'})

@app.route('/api/daily-reports/<int:report_id>/items', methods=['POST'])
@require_auth
def add_daily_report_item(report_id):
    """Append a single item section to a report."""
    data = request.get_json() or {}
    section = (data.get('section') or 'other').strip()
    if section not in REPORT_SECTIONS and section != 'key_incidents' and section != 'actions':
        return jsonify({'error': 'invalid section'}), 400
    conn = get_db()
    if not conn.execute('SELECT 1 FROM daily_reports WHERE id = ?', (report_id,)).fetchone():
        conn.close()
        return jsonify({'error': 'Report not found'}), 404
    conn.execute('''
        INSERT INTO daily_report_items (report_id, section, source_category, content, incident_id)
        VALUES (?, ?, ?, ?, ?)
    ''', (report_id, section, data.get('source_category'), data.get('content'), data.get('incident_id')))
    item_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.commit()
    conn.close()
    return jsonify({'id': item_id, 'message': 'Item added'}), 201

@app.route('/api/daily-reports/<int:report_id>', methods=['DELETE'])
@require_auth
def delete_daily_report(report_id):
    """Delete a report and its items (admin/analyst)."""
    if g.user.get('role') not in ('admin', 'analyst'):
        return jsonify({'error': 'Only admins and analysts can delete reports'}), 403
    conn = get_db()
    if not conn.execute('SELECT 1 FROM daily_reports WHERE id = ?', (report_id,)).fetchone():
        conn.close()
        return jsonify({'error': 'Report not found'}), 404
    conn.execute('DELETE FROM daily_report_items WHERE report_id = ?', (report_id,))
    conn.execute('DELETE FROM followups WHERE report_id = ?', (report_id,))
    conn.execute('DELETE FROM daily_reports WHERE id = ?', (report_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Report deleted'})

# ============== FOLLOW-UP MANAGEMENT (HQ) ==============

@app.route('/api/followups', methods=['GET'])
@require_auth
def get_followups():
    """List follow-ups (role-filtered). Filters: status, branch_id."""
    conn = get_db()
    allowed = _allowed_branch_ids(conn, g.user)
    where, values = [], []
    if allowed is not None:
        where.append('branch_id IN (%s)' % ','.join('?' * len(allowed)))
        values.extend(allowed)
    if request.args.get('status'):
        where.append('status = ?')
        values.append(request.args['status'])
    if request.args.get('branch_id'):
        where.append('branch_id = ?')
        values.append(request.args['branch_id'])
    sql = 'SELECT * FROM followups'
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY status = "closed", status = "resolved", due_date IS NULL, due_date ASC, id DESC'
    rows = [dict(r) for r in conn.execute(sql, values).fetchall()]
    conn.close()
    return jsonify(rows)

@app.route('/api/followups', methods=['POST'])
@require_auth
def create_followup():
    """Create a follow-up from a report item / discussion decision."""
    data = request.get_json() or {}
    data = enforce_branch_on_write(data)
    if not data.get('item'):
        return jsonify({'error': 'item text is required'}), 400
    conn = get_db()
    conn.execute('''
        INSERT INTO followups (branch_id, report_id, item, assigned_to, due_date, status, decision, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (data.get('branch_id'), data.get('report_id'), data.get('item'),
          data.get('assigned_to'), data.get('due_date'), data.get('status') or 'open',
          data.get('decision'), g.user.get('user_id')))
    f_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.commit()
    conn.close()
    return jsonify({'id': f_id, 'message': 'Follow-up created'}), 201

@app.route('/api/followups/<int:followup_id>', methods=['PATCH'])
@require_auth
def update_followup(followup_id):
    """Update a follow-up (status, decision, assignment, due date)."""
    data = request.get_json() or {}
    conn = get_db()
    if not conn.execute('SELECT 1 FROM followups WHERE id = ?', (followup_id,)).fetchone():
        conn.close()
        return jsonify({'error': 'Follow-up not found'}), 404
    updates, values = [], []
    for field in ('status', 'decision', 'assigned_to', 'due_date', 'item'):
        if field in data:
            updates.append(f'{field} = ?')
            values.append(data[field])
    if not updates:
        conn.close()
        return jsonify({'error': 'No fields to update'}), 400
    values.append(followup_id)
    conn.execute(f'UPDATE followups SET {", ".join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?', values)
    conn.commit()
    conn.close()
    return jsonify({'id': followup_id, 'message': 'Follow-up updated'})

# ============== AI ANALYSIS & SUMMARIES ==============

def _call_ai_summarize(contexts, kind='poi_category', timeout_seconds=600):
    """Call evaluation_service AI summarizer (cloud-backed, sync)."""
    try:
        resp = requests.post(
            f'{EVALUATION_API_URL}/api/analysis/summarize',
            json={'kind': kind, 'contexts': contexts},
            timeout=timeout_seconds,
        )
        if resp.status_code != 200:
            return None, f'AI service error {resp.status_code}'
        result = resp.json()
        if not isinstance(result, dict) or 'summaries' not in result:
            return None, f'unexpected AI response: {str(result)[:200]}'
        return result, None
    except Exception as e:
        return None, f'AI service unreachable: {e}'

def _build_poi_category_context(conn, category):
    rows = conn.execute(
        'SELECT name, lat, lng, category_data, address, verified, source '
        'FROM points_of_interest WHERE category = ? AND is_active = 1',
        (category,)).fetchall()
    names = [dict(r) for r in rows]
    stats = {'total': len(names), 'verified': sum(1 for r in names if r['verified']),
             'custom': sum(1 for r in names if r['source'] != 'osm')}
    # Aggregate numeric/percent schema fields
    for field in get_poi_schema(conn, category):
        fkey, ftype = field['field_key'], field['field_type']
        vals = []
        for r in names:
            cd = json.loads(r['category_data']) if r.get('category_data') else {}
            v = cd.get(fkey)
            if isinstance(v, (int, float)):
                vals.append(v)
            elif ftype == 'boolean':
                vals.append(1 if v else 0)
        if vals:
            stats[field['field_label']] = f"{sum(vals)/len(vals):.1f} avg ({len(vals)} reported)"
    return {'category': category, 'stats': stats, 'names': [r['name'] for r in names if r['name']][:40]}

def _build_branch_context(conn, branch_id, days=7):
    branch = conn.execute('SELECT id, name, city, region FROM branches WHERE id = ?', (branch_id,)).fetchone()
    if not branch:
        return None
    since = (datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
             - __import__('datetime').timedelta(days=days - 1)).strftime('%Y-%m-%d')
    reports = [dict(r) for r in conn.execute(
        'SELECT report_date, branch_status, summary, needs FROM daily_reports '
        'WHERE branch_id = ? AND report_date >= ? ORDER BY report_date', (branch_id, since))]
    items = [dict(r) for r in conn.execute(
        'SELECT section, source_category, content FROM daily_report_items '
        'WHERE report_id IN (SELECT id FROM daily_reports WHERE branch_id = ? AND report_date >= ?) '
        'ORDER BY section', (branch_id, since))]
    followups = [dict(r) for r in conn.execute(
        'SELECT item, status, decision FROM followups WHERE branch_id = ?', (branch_id,))]
    incidents = conn.execute(
        'SELECT COUNT(*) FROM incidents WHERE branch_id = ? AND is_archived = 0', (branch_id,)).fetchone()[0]
    return {
        'branch': dict(branch),
        'days': since,
        'reports': reports,
        'items': items,
        'followups': followups,
        'open_incidents': incidents,
    }

# In-memory store for in-flight analyst summary jobs (job_id -> status)
_analyst_jobs = {}
_analyst_jobs_lock = threading.Lock()

def _persist_analysis_result(result, kind, period_days):
    conn = get_db()
    cursor = conn.cursor()
    created = []
    period_end = datetime.now().strftime('%Y-%m-%d')
    import datetime as _dt
    period_start = (_dt.datetime.now() - _dt.timedelta(days=period_days)).strftime('%Y-%m-%d')
    for item in result.get('summaries', []):
        cursor.execute('''
            INSERT INTO analysis_summaries (kind, category, branch_id, period_start, period_end, model, summary_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (item.get('kind', kind), item.get('category'), item.get('branch_id'),
              period_start, period_end, result.get('model'), json.dumps(item, ensure_ascii=False)))
        created.append(cursor.lastrowid)
    conn.commit()
    conn.close()
    return created

def _build_analysis_contexts(data):
    """Build the context list for a summarize request (sheet-local)."""
    kind = data.get('kind') or 'all'
    period_days = max(1, min(int(data.get('period_days') or 7), 30))
    conn = get_db()
    contexts = []
    if kind in ('poi_category', 'all'):
        category = data.get('category')
        cats = [category] if category else [r[0] for r in conn.execute(
            "SELECT DISTINCT category FROM points_of_interest WHERE is_active = 1 AND category IS NOT NULL ORDER BY category")]
        for cat in cats:
            ctx = _build_poi_category_context(conn, cat)
            if ctx:
                contexts.append(ctx)
    if kind in ('branch', 'all'):
        branch_id = data.get('branch_id')
        branches = [branch_id] if branch_id else [r[0] for r in conn.execute(
            'SELECT id FROM branches WHERE is_active = 1')]
        for bid in branches:
            ctx = _build_branch_context(conn, bid, period_days)
            if ctx:
                contexts.append(ctx)
    conn.close()
    return contexts, kind, period_days

def _run_analyst_job(job_id, contexts, kind, period_days):
    start = time.time()
    result, err = _call_ai_summarize(contexts, kind=kind, timeout_seconds=1800)
    with _analyst_jobs_lock:
        entry = _analyst_jobs.get(job_id)
        if entry is None:
            return
        if err or not result:
            entry['status'] = 'error'
            entry['error'] = err or 'No summary produced'
            entry['finished_at'] = datetime.now().isoformat()
            return
        try:
            entry['ids'] = _persist_analysis_result(result, kind, period_days)
            entry['result'] = {'summaries': result.get('summaries', []),
                               'model': result.get('model'),
                               'generated_at': result.get('generated_at')}
            entry['status'] = 'success'
        except Exception as e:
            entry['status'] = 'error'
            entry['error'] = f'persist failed: {e}'
        entry['finished_at'] = datetime.now().isoformat()
        entry['elapsed'] = round(time.time() - start)

def _new_analyst_job(job_id):
    entry = {'id': job_id, 'status': 'running', 'result': None, 'error': None,
             'created_at': datetime.now().isoformat(), 'finished_at': None}
    with _analyst_jobs_lock:
        _analyst_jobs[job_id] = entry
    return entry

@app.route('/api/analysis/summarize', methods=['POST'])
@require_auth
def run_analysis_summary():
    """Trigger an async AI summary for POI categories and/or branches.
    Returns {job_id} immediately; poll GET /api/analysis/jobs/<job_id>.
    Body: {kind: 'poi_category'|'branch'|'all', category?, branch_id?, period_days?}
    """
    if g.user.get('role') not in ('admin', 'analyst'):
        return jsonify({'error': 'Analyst or admin access required'}), 403
    data = request.get_json() or {}
    contexts, kind, period_days = _build_analysis_contexts(data)
    if not contexts:
        return jsonify({'error': 'Nothing to summarize'}), 400

    job_id = uuid.uuid4().hex[:12]
    _new_analyst_job(job_id)
    threading.Thread(target=_run_analyst_job,
                     args=(job_id, contexts, kind, period_days), daemon=True).start()
    return jsonify({'job_id': job_id, 'status': 'running', 'kind': kind}), 202

@app.route('/api/analysis/jobs/<job_id>', methods=['GET'])
@require_auth
def get_analysis_job(job_id):
    """Poll the status/result of an async analysis job."""
    if g.user.get('role') not in ('admin', 'analyst'):
        return jsonify({'error': 'Analyst or admin access required'}), 403
    with _analyst_jobs_lock:
        entry = _analyst_jobs.get(job_id)
    if not entry:
        return jsonify({'error': 'Job not found (may have expired)'}), 404
    return jsonify(entry)

@app.route('/api/analysis/summaries', methods=['GET'])
@require_auth
def get_analysis_summaries():
    """List stored summaries. Filters: kind, category, branch_id, limit."""
    conn = get_db()
    where, values = [], []
    if request.args.get('kind'):
        where.append('kind = ?')
        values.append(request.args['kind'])
    if request.args.get('category'):
        where.append('category = ?')
        values.append(request.args['category'])
    if request.args.get('branch_id'):
        where.append('branch_id = ?')
        values.append(request.args['branch_id'])
    sql = 'SELECT * FROM analysis_summaries'
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    limit = min(int(request.args.get('limit', 50)), 200)
    sql += ' ORDER BY id DESC LIMIT ?'
    values.append(limit)
    rows = [dict(r) for r in conn.execute(sql, values).fetchall()]
    for r in rows:
        r['summary'] = json.loads(r.pop('summary_json')) if r.get('summary_json') else None
    conn.close()
    return jsonify(rows)

@app.route('/api/analysis/digest', methods=['GET'])
@require_auth
def get_analysis_digest():
    """Return the latest digest entries (nightly + on-demand summaries)."""
    import datetime as _dt
    try:
        days = max(1, min(int(request.args.get('days', '7')), 30))
    except ValueError:
        days = 7
    since = (_dt.datetime.now() - _dt.timedelta(days=days)).strftime('%Y-%m-%d')
    conn = get_db()
    rows = conn.execute('''
        SELECT * FROM analysis_summaries WHERE period_start >= ?
        ORDER BY created_at DESC LIMIT 50
    ''', (since,)).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        item['summary'] = json.loads(item.pop('summary_json')) if item.get('summary_json') else None
        out.append(item)
    conn.close()
    return jsonify(out)

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
    
    if user.get('role') in ('admin', 'analyst'):
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
    
    # Admin/analyst see all events
    if user.get('role') in ('admin', 'analyst'):
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
    
    if data.get('role') not in ['admin', 'regional_admin', 'operator', 'data_entry', 'analyst']:
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

# ============== NIGHTLY AI DIGEST ==============

_digest_lock = threading.Lock()
_last_digest_date = None

def run_nightly_digest():
    """Generate a nightly AI digest: all POI categories + all branches."""
    conn = get_db()
    categories = [r[0] for r in conn.execute(
        "SELECT DISTINCT category FROM points_of_interest WHERE is_active = 1 AND category IS NOT NULL ORDER BY category")]
    branches = [r[0] for r in conn.execute('SELECT id FROM branches WHERE is_active = 1')]
    conn.close()
    contexts = []
    for cat in categories:
        conn = get_db()
        ctx = _build_poi_category_context(conn, cat)
        conn.close()
        if ctx:
            contexts.append(ctx)
    for bid in branches:
        conn = get_db()
        ctx = _build_branch_context(conn, bid, 7)
        conn.close()
        if ctx:
            contexts.append(ctx)
    if not contexts:
        return
    result, err = _call_ai_summarize(contexts, kind='daily', timeout_seconds=1800)
    if err or not result:
        system_logger.warning(f'Nightly digest failed: {err}')
        return
    conn = get_db()
    period_end = datetime.now().strftime('%Y-%m-%d')
    import datetime as _dt
    period_start = (_dt.datetime.now() - _dt.timedelta(days=7)).strftime('%Y-%m-%d')
    for item in result.get('summaries', []):
        conn.execute('''
            INSERT INTO analysis_summaries (kind, category, branch_id, period_start, period_end, model, summary_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (item.get('kind', 'daily'), item.get('category'), item.get('branch_id'),
              period_start, period_end, result.get('model'), json.dumps(item, ensure_ascii=False)))
    conn.commit()
    conn.close()
    system_logger.info(f'Nightly digest completed for {len(categories)} categories and {len(branches)} branches')

def digest_worker():
    """Background loop: run the digest once per day."""
    global _last_digest_date
    while True:
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            if _last_digest_date != today and datetime.now().hour >= 2:
                with _digest_lock:
                    if _last_digest_date != today:
                        run_nightly_digest()
                        _last_digest_date = today
        except Exception as e:
            system_logger.warning(f'Digest worker error: {e}')
        time.sleep(600)

def start_digest_worker():
    """Start background digest thread once (skip reloader parent)."""
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not os.environ.get('WERKZEUG_RUN_MAIN'):
        if not any(t.name == 'nightly-digest' for t in threading.enumerate()):
            t = threading.Thread(target=digest_worker, name='nightly-digest', daemon=True)
            t.start()
            system_logger.info('Nightly digest worker started')

# Initialize database on startup
if __name__ == '__main__':
    init_db()
    start_digest_worker()
    app.run(host='0.0.0.0', port=5000, debug=True)
