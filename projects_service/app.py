#!/usr/bin/env python3
"""Projects Service — health convoys, portable hospitals, detention-centre &
field-visit operations. Microservice on port 5004, served at
https://projects.onlineacademy.com.ly via the cloudflared tunnel.

SHARES AUTH with the dashboard: same JWT_SECRET_KEY env + same users table
(admin/CHANGEME), but every request is additionally scoped by project_users
(role: admin | staff | viewer). Own DB projects_ops.db, auto-schema init_db().
"""
import os
import sys
import json
import sqlite3
import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request, g, render_template, send_from_directory
from flask import jsonify as jj

BASE = Path(__file__).resolve().parent
DATABASE = os.environ.get(
    'PROJECTS_DB', str(BASE / 'database' / 'projects_ops.db'))
SECRET_KEY = os.environ.get(
    'JWT_SECRET_KEY', 'your-secret-key-change-in-production')
TOKEN_ALGO = 'HS256'
TOKEN_TTL = timedelta(hours=8)

PASSWORD_HASH_BCRYPT_PREFIX = 'bcrypt:'  # same convention as dashboard auth.py

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024


# --------------------------------------------------------------------------
# DB schema (idempotent — sync safe)
# --------------------------------------------------------------------------
SCHEMA = r'''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,          -- bcrypt hash (no prefix like dashboard? verify)
    full_name TEXT,
    role TEXT DEFAULT 'admin',            -- used by dashboard auth; here top-level
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    project_type TEXT NOT NULL DEFAULT 'health_convoy',
    region TEXT,
    description TEXT,
    status TEXT DEFAULT 'active',
    is_active INTEGER DEFAULT 1,
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS project_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    role TEXT NOT NULL DEFAULT 'staff',   -- admin | staff | viewer
    UNIQUE(project_id, user_id)
);

CREATE TABLE IF NOT EXISTS gps_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    user_id INTEGER,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    note TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'planned',        -- planned|in_progress|done|blocked
    priority INTEGER DEFAULT 1,
    assignee_id INTEGER REFERENCES users(id),
    lat REAL,
    lng REAL,
    due_date TEXT,
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS visit_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    title TEXT NOT NULL,
    start_time TEXT,
    end_time TEXT,
    waypoints TEXT,                        -- JSON list of {lat,lng,label}
    status TEXT DEFAULT 'planned',
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    title TEXT NOT NULL,
    report_date TEXT,
    summary TEXT,
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS report_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL REFERENCES reports(id),
    metric_key TEXT NOT NULL,
    metric_value REAL,
    metric_label TEXT
);
'''


def get_db():
    conn = sqlite3.connect(DATABASE, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    Path(DATABASE).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE)
    conn.executescript(SCHEMA)
    # seed shared admin account (bcrypt hash same as dashboard)
    cur = conn.cursor()
    row = cur.execute("SELECT id FROM users WHERE username='admin'").fetchone()
    if not row:
        h = bcrypt.hashpw(b'CHANGEME', bcrypt.gensalt()).decode()
        cur.execute(
            "INSERT INTO users (username, password_hash, full_name, role) "
            "VALUES ('admin', ?, 'Project Admin', 'admin')", (h,))
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------
# Auth (mirrors dashboard auth.py on purpose — same secret, same users table)
# --------------------------------------------------------------------------
def create_token(user_id, username, role):
    now = datetime.now(timezone.utc)
    payload = {
        'sub': str(user_id),
        'username': username,
        'role': role,
        'typ': 'dashboard',   # same claim the dashboard uses so tokens interoperate
        'iat': now,
        'exp': now + TOKEN_TTL,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=TOKEN_ALGO)


def require_auth(f):
    @wraps(f)
    def wrapper(*a, **kw):
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid Authorization header'}), 401
        token = auth.replace('Bearer ', '')
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[TOKEN_ALGO], leeway=30)
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        g.user = payload
        return f(*a, **kw)
    return wrapper


def project_admin_required(f):
    @wraps(f)
    @require_auth
    def wrapper(project_id, *a, **kw):
        uid = int(g.user['sub'])
        conn = get_db()
        row = conn.execute(
            "SELECT role FROM project_users WHERE project_id=? AND user_id=?",
            (project_id, uid)).fetchone()
        conn.close()
        if not row or row['role'] not in ('admin',):
            return jsonify({'error': 'Project admin required'}), 403
        return f(project_id, *a, **kw)
    return wrapper


def project_scoped(f):
    """Allow only users who are members of this project (any role)."""
    @wraps(f)
    @require_auth
    def wrapper(project_id, *a, **kw):
        uid = int(g.user['sub'])
        conn = get_db()
        row = conn.execute(
            "SELECT 1 FROM project_users WHERE project_id=? AND user_id=?",
            (project_id, uid)).fetchone()
        is_admin = conn.execute(
            "SELECT role FROM project_users WHERE project_id=? AND user_id=?",
            (project_id, uid)).fetchone()
        conn.close()
        if not row:
            return jsonify({'error': 'Not a member of this project'}), 403
        g.project_role = is_admin['role'] if is_admin else 'viewer'
        return f(project_id, *a, **kw)
    return wrapper


# --------------------------------------------------------------------------
# Frontend
# --------------------------------------------------------------------------
@app.route('/')
def index():
    return render_template('dashboard.html', service='projects')


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(str(BASE / 'static'), 'favicon.ico')


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
@app.route('/api/auth/login', methods=['POST'])
def login():
    d = request.get_json(force=True) if request.data else {}
    u = (d.get('username') or '').strip()
    p = d.get('password') or ''
    if not u or not p:
        return jsonify({'error': 'username and password required'}), 400
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE username=? AND is_active=1",
                       (u,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Invalid credentials'}), 401
    stored = row['password_hash']
    if stored.startswith('bcrypt:'):
        stored = stored[len('bcrypt:'):]
    if not bcrypt.checkpw(p.encode(), stored.encode()):
        return jsonify({'error': 'Invalid credentials'}), 401
    token = create_token(row['id'], row['username'], row['role'])
    return jsonify({'token': token, 'user': {
        'id': row['id'], 'username': row['username'],
        'role': row['role'], 'full_name': row['full_name']}})


@app.route('/api/projects', methods=['GET'])
@require_auth
def list_projects():
    uid = int(g.user['sub'])
    conn = get_db()
    if g.user.get('role') == 'admin':
        rows = conn.execute(
            "SELECT p.*, IFNULL((SELECT COUNT(*) FROM project_users pu "
            "WHERE pu.project_id=p.id),0) AS member_count "
            "FROM projects p WHERE p.is_active=1 ORDER BY p.name").fetchall()
        result = [dict(r) for r in rows]
        # admins see all — mark them admin on every project
        for r in result:
            r['my_role'] = 'admin'
    else:
        rows = conn.execute(
            "SELECT p.*, pu.role AS my_role, "
            "(SELECT COUNT(*) FROM project_users pu2 WHERE pu2.project_id=p.id) AS member_count "
            "FROM projects p JOIN project_users pu ON pu.project_id=p.id "
            "WHERE p.is_active=1 AND pu.user_id=?",
            (uid,)).fetchall()
        result = [dict(r) for r in rows]
    conn.close()
    return jsonify(result)


@app.route('/api/projects', methods=['POST'])
@require_auth
def create_project():
    if g.user.get('role') != 'admin':
        return jsonify({'error': 'Only global admins can create projects'}), 403
    d = request.get_json(force=True) if request.data else {}
    name = (d.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Project name required'}), 400
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO projects (name, project_type, region, description, created_by) "
        "VALUES (?,?,?,?,?)",
        (name, d.get('project_type', 'health_convoy'), d.get('region'),
         d.get('description'), int(g.user['sub'])))
    pid = cur.lastrowid
    # creator becomes project admin automatically
    conn.execute("INSERT OR IGNORE INTO project_users (project_id,user_id,role) "
                 "VALUES (?,?,'admin')", (pid, int(g.user['sub'])))
    conn.commit()
    conn.close()
    return jsonify({'id': pid, 'name': name}), 201


@app.route('/api/projects/<int:pid>/users', methods=['GET', 'POST'])
def project_users(pid):
    conn = get_db()
    if request.method == 'GET':
        @project_scoped
        def _g(pid):
            rows = conn.execute(
                "SELECT u.id, u.username, u.full_name, pu.role "
                "FROM project_users pu JOIN users u ON u.id=pu.user_id "
                "WHERE pu.project_id=?", (pid,)).fetchall()
            return jsonify([dict(r) for r in rows])
        return _g(pid)
    else:
        @project_admin_required
        def _p(pid):
            d = request.get_json(force=True) or {}
            uname = (d.get('username') or '').strip()
            role = d.get('role', 'staff')
            conn.execute(
                "INSERT OR REPLACE INTO project_users (project_id,user_id,role) "
                "SELECT ?, id, ? FROM users WHERE username=?",
                (pid, role, uname))
            conn.commit()
            return jsonify({'ok': True}), 201
        return _p(pid)


@app.route('/api/projects/<int:pid>/members/<int:uid>', methods=['DELETE'])
@project_admin_required
def remove_member(pid, uid):
    conn = get_db()
    conn.execute("DELETE FROM project_users WHERE project_id=? AND user_id=?",
                 (pid, uid))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


def _scope_get(pid):
    return (int(g.user['sub']), get_db())


@app.route('/api/projects/<int:pid>/points', methods=['GET', 'POST'])
def gps_points(pid):
    conn = get_db()
    if request.method == 'GET':
        @project_scoped
        def _g(pid):
            rows = conn.execute(
                "SELECT gp.*, u.username FROM gps_points gp "
                "LEFT JOIN users u ON u.id=gp.user_id "
                "WHERE gp.project_id=? ORDER BY gp.recorded_at DESC LIMIT 5000",
                (pid,)).fetchall()
            return jsonify([dict(r) for r in rows])
        return _g(pid)
    else:
        @project_scoped
        def _p(pid):
            d = request.get_json(force=True) or {}
            lat = d.get('lat'); lng = d.get('lng')
            if lat is None or lng is None:
                return jsonify({'error': 'lat and lng required'}), 400
            cur = conn.execute(
                "INSERT INTO gps_points (project_id,user_id,lat,lng,note) "
                "VALUES (?,?,?,?,?)",
                (pid, int(g.user['sub']), float(lat), float(lng), d.get('note')))
            conn.commit()
            return jsonify({'id': cur.lastrowid}), 201
        return _p(pid)


@app.route('/api/projects/<int:pid>/tasks', methods=['GET', 'POST'])
def tasks(pid):
    conn = get_db()
    if request.method == 'GET':
        @project_scoped
        def _g(pid):
            rows = conn.execute(
                "SELECT t.*, u.username AS assignee FROM tasks t "
                "LEFT JOIN users u ON u.id=t.assignee_id "
                "WHERE t.project_id=? ORDER BY t.status, t.priority",
                (pid,)).fetchall()
            return jsonify([dict(r) for r in rows])
        return _g(pid)
    else:
        @project_scoped
        def _p(pid):
            d = request.get_json(force=True) or {}
            title = (d.get('title') or '').strip()
            if not title:
                return jsonify({'error': 'task title required'}), 400
            cur = conn.execute(
                "INSERT INTO tasks (project_id,title,description,status,priority,"
                "assignee_id,lat,lng,due_date,created_by) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (pid, title, d.get('description'), d.get('status', 'planned'),
                 d.get('priority', 1), d.get('assignee_id'), d.get('lat'),
                 d.get('lng'), d.get('due_date'), int(g.user['sub'])))
            conn.commit()
            return jsonify({'id': cur.lastrowid}), 201
        return _p(pid)


@app.route('/api/projects/<int:pid>/tasks/<int:tid>', methods=['PATCH'])
@project_scoped
def update_task(pid, tid):
    d = request.get_json(force=True) or {}
    ok = ['status', 'priority', 'assignee_id', 'title', 'due_date']
    sets = {k: d[k] for k in ok if k in d}
    if not sets:
        return jsonify({'error': 'nothing to update'}), 400
    conn = get_db()
    conn.execute(
        "UPDATE tasks SET " + ", ".join(f"{k}=?" for k in sets) +
        " WHERE id=? AND project_id=?", (*sets.values(), tid, pid))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/projects/<int:pid>/reports', methods=['GET', 'POST'])
def reports(pid):
    conn = get_db()
    if request.method == 'GET':
        @project_scoped
        def _g(pid):
            rows = conn.execute(
                "SELECT r.*, u.username AS created_by_name "
                "FROM reports r LEFT JOIN users u ON u.id=r.created_by "
                "WHERE r.project_id=? ORDER BY r.report_date DESC, r.created_at DESC",
                (pid,)).fetchall()
            return jsonify([dict(r) for r in rows])
        return _g(pid)
    else:
        @project_scoped
        def _p(pid):
            d = request.get_json(force=True) or {}
            title = (d.get('title') or '').strip()
            if not title:
                return jsonify({'error': 'report title required'}), 400
            cur = conn.execute(
                "INSERT INTO reports (project_id,title,report_date,summary,created_by) "
                "VALUES (?,?,?,?,?)",
                (pid, title, d.get('report_date'), d.get('summary'),
                 int(g.user['sub'])))
            rid = cur.lastrowid
            for m in (d.get('metrics') or []):
                if isinstance(m, dict) and m.get('key'):
                    conn.execute(
                        "INSERT INTO report_metrics (report_id,metric_key,"
                        "metric_value,metric_label) VALUES (?,?,?,?)",
                        (rid, m['key'], m.get('value'), m.get('label')))
            conn.commit()
            return jsonify({'id': rid}), 201
        return _p(pid)


@app.route('/api/projects/<int:pid>/analytics', methods=['GET'])
@project_scoped
def analytics(pid):
    conn = get_db()
    tasks_row = conn.execute(
        "SELECT COUNT(*) AS total, "
        "SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) AS done, "
        "SUM(CASE WHEN status='in_progress' THEN 1 ELSE 0 END) AS in_progress, "
        "SUM(CASE WHEN status='planned' THEN 1 ELSE 0 END) AS planned, "
        "SUM(CASE WHEN status='blocked' THEN 1 ELSE 0 END) AS blocked "
        "FROM tasks WHERE project_id=?", (pid,)).fetchone()
    points = conn.execute(
        "SELECT COUNT(*) AS n FROM gps_points WHERE project_id=?", (pid,)).fetchone()[0]
    reports = conn.execute(
        "SELECT COUNT(*) FROM reports WHERE project_id=?", (pid,)).fetchone()[0]
    # metric rollups across the project's reports
    rollups = conn.execute(
        "SELECT metric_key, SUM(metric_value) AS total, COUNT(*) AS n "
        "FROM report_metrics rm JOIN reports r ON r.id=rm.report_id "
        "WHERE r.project_id=? GROUP BY metric_key ORDER BY total DESC",
        (pid,)).fetchall()
    # time trend of tasks by day
    trend = conn.execute(
        "SELECT date(created_at) AS day, COUNT(*) AS n "
        "FROM tasks WHERE project_id=? GROUP BY date(created_at) "
        "ORDER BY day", (pid,)).fetchall()
    conn.close()
    return jsonify({
        'tasks': dict(tasks_row),
        'gps_points': points,
        'reports': reports,
        'metric_rollups': [dict(r) for r in rollups],
        'task_trend': [dict(r) for r in trend],
    })


if __name__ == '__main__':
    if '--init-db' in sys.argv:
        init_db()
        print(f"projects_service init: {DATABASE} ready")
    else:
        init_db()
        app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '5004')),
                threaded=True, debug=False)
