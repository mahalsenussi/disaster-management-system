"""
RBAC Authentication Module
JWT-based auth with role-based access control
"""

import jwt
import bcrypt
import time
import json
from functools import wraps
from flask import request, jsonify, g
from datetime import datetime
import sqlite3
import os

# Configuration
SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'your-secret-key-change-in-production')
DATABASE = os.path.join(os.path.dirname(__file__), 'database', 'disaster_ops.db')

# Token expiration
USER_TOKEN_EXPIRY = 8 * 60 * 60  # 8 hours for dashboard users
TEAM_TOKEN_EXPIRY = 7 * 24 * 60 * 60  # 7 days for mobile teams

def get_db():
    """Get database connection with WAL mode and timeout."""
    conn = sqlite3.connect(DATABASE, timeout=30.0)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrency
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=30000')
    return conn

# ============== Geo-Based Access Control ==============

def is_in_branch_area(item_lat, item_lng, branch):
    """
    Check if a point (item_lat, item_lng) is within a branch's geographic area.
    Uses simple distance calculation: radius in km converted to degrees.
    """
    if not branch or not branch.get('lat') or not branch.get('lng'):
        return False
    
    # Convert radius in km to degrees (approximate: 1 degree ≈ 111 km)
    radius_deg = (branch.get('radius_km', 10) or 10) / 111.0
    
    dx = item_lat - branch['lat']
    dy = item_lng - branch['lng']
    
    # Check if point is within radius (using squared distance to avoid sqrt)
    return (dx * dx + dy * dy) <= (radius_deg * radius_deg)

def get_branches_for_geo_filtering(conn, user):
    """
    Get branches relevant for geo-based filtering based on user role.
    Returns list of branch dicts with lat, lng, radius_km.
    """
    cursor = conn.cursor()
    
    if user.get('role') == 'admin':
        # Admin sees all branches
        cursor.execute('SELECT id, name, lat, lng, region FROM branches WHERE is_active = 1')
    elif user.get('role') == 'regional_admin':
        # Regional admin sees branches in their region
        cursor.execute(
            'SELECT id, name, lat, lng, region FROM branches WHERE region = ? AND is_active = 1',
            (user.get('region'),)
        )
    else:
        # Operators and teams only see their own branch
        cursor.execute(
            'SELECT id, name, lat, lng, region FROM branches WHERE id = ? AND is_active = 1',
            (user.get('branch_id'),)
        )
    
    branches = [dict(row) for row in cursor.fetchall()]
    # Add default radius for geo filtering
    for branch in branches:
        branch['radius_km'] = branch.get('radius_km', 10) or 10
    return branches

# ============== JWT Token Generation ==============

def generate_user_token(user_id, role, branch_id):
    """Generate JWT token for dashboard users (8 hour expiry)"""
    payload = {
        'type': 'user',
        'user_id': user_id,
        'role': role,
        'branch_id': branch_id,
        'exp': int(time.time()) + USER_TOKEN_EXPIRY
    }
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')

def generate_team_token(team_id, branch_id):
    """Generate JWT token for mobile teams (7 day expiry)"""
    payload = {
        'type': 'team',
        'team_id': team_id,
        'branch_id': branch_id,
        'exp': int(time.time()) + TEAM_TOKEN_EXPIRY
    }
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')

# ============== Auth Decorators ==============

def require_auth(f):
    """Verify JWT token and set g.user"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid Authorization header'}), 401
        
        token = auth_header.split(' ')[1]
        try:
            # leeway=30 allows 30s clock drift tolerance for mobile devices
            payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'], leeway=30)
            
            # Validate token type
            if payload.get('type') not in ['user', 'team']:
                return jsonify({'error': 'Invalid token type'}), 401
            
            g.user = payload
            return f(*args, **kwargs)
            
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError as e:
            return jsonify({'error': 'Invalid token'}), 401
    
    return wrapper

def require_user_auth(f):
    """Only for dashboard users (not mobile teams)"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing Authorization header'}), 401
        
        token = auth_header.split(' ')[1]
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'], leeway=30)
            
            if payload.get('type') != 'user':
                return jsonify({'error': 'User access only'}), 403
            
            g.user = payload
            return f(*args, **kwargs)
            
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
    
    return wrapper

def require_team_auth(f):
    """Only for mobile teams (not dashboard users)"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing Authorization header'}), 401
        
        token = auth_header.split(' ')[1]
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'], leeway=30)
            
            if payload.get('type') != 'team':
                return jsonify({'error': 'Team access only'}), 403
            
            g.user = payload
            return f(*args, **kwargs)
            
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
    
    return wrapper

def require_role(*roles):
    """Require specific role(s) for access"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if g.user.get('role') not in roles:
                return jsonify({'error': 'Forbidden - insufficient privileges'}), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator

# ============== Branch Filtering ==============

def apply_branch_filter(query_base, entity_branch_col='branch_id'):
    """
    Apply branch filter to SQL query based on user role.
    Returns modified SQL with WHERE clause.
    """
    user = g.user
    
    # Handle team tokens (mobile)
    if user.get('type') == 'team':
        return f"{query_base} WHERE {entity_branch_col} = {user.get('branch_id')}"
    
    # Handle user tokens (dashboard)
    role = user.get('role')
    branch_id = user.get('branch_id')
    
    if role == 'admin':
        # Admin sees all - no filter
        return query_base
    
    if role == 'regional_admin':
        # Regional admin sees branches in their region
        # Requires joining with branches table
        region = user.get('region')
        return f"{query_base} JOIN branches ON {entity_branch_col} = branches.id WHERE branches.region = '{region}'"
    
    if role == 'operator':
        # Operator sees ONLY their branch
        return f"{query_base} WHERE {entity_branch_col} = {branch_id}"
    
    # Unknown role - no access (use SQL FALSE)
    return f"{query_base} WHERE 1=0"

def enforce_branch_on_write(data):
    """
    Force branch_id from user context on all writes.
    NEVER trust frontend-sent branch_id.
    """
    user = g.user
    
    if user.get('type') == 'team':
        # Teams can only write to their own branch
        data['branch_id'] = user.get('branch_id')
        return data
    
    # Dashboard users
    role = user.get('role')
    
    if role == 'operator':
        # Operators CANNOT choose branch - forced from their assignment
        data['branch_id'] = user.get('branch_id')
    
    # Admin can choose any branch - validation happens in endpoint
    # Regional_admin can choose branches in their region
    
    return data

# ============== Audit Logging ==============

def log_action(action, entity_type, entity_id, old_values=None, new_values=None):
    """Log all sensitive operations for accountability"""
    conn = get_db()
    cursor = conn.cursor()
    
    user_id = None
    team_id = None
    
    if hasattr(g, 'user'):
        if g.user.get('type') == 'user':
            user_id = g.user.get('user_id')
        else:
            team_id = g.user.get('team_id')
    
    cursor.execute('''
        INSERT INTO audit_logs 
        (user_id, team_id, action, entity_type, entity_id, old_values, new_values, ip_address)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        user_id,
        team_id,
        action,
        entity_type,
        entity_id,
        json.dumps(old_values) if old_values else None,
        json.dumps(new_values) if new_values else None,
        request.remote_addr
    ))
    
    conn.commit()
    conn.close()

# ============== Password Utilities ==============

def hash_password(password):
    """Hash password with bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password, password_hash):
    """Verify password against hash"""
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
