"""Part A — production-migration lanes (own copy, own DB, guarded + idempotent).

Called from init_db()'s commit lane right after the schema CREATEs.
Self-contained: no imports beyond stdlib. Guarded per-table / per-column so
every splice is idempotent and never touches the public lane's DB.
"""
import sqlite3, json

_WS_TABLES = {
    "workstreams": (
        "CREATE TABLE IF NOT EXISTS workstreams ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "name TEXT NOT NULL,"
        "type TEXT NOT NULL DEFAULT 'project' CHECK (type IN ('project','exercise')),"
        "code TEXT, description TEXT, region TEXT, objective TEXT,"
        "status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','closed','archived')),"
        "default_branch_id INTEGER, created_by INTEGER,"
        "started_at TEXT, ended_at TEXT, is_active INTEGER DEFAULT 1)"),
    "scenario_templates": (
        "CREATE TABLE IF NOT EXISTS scenario_templates ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "name TEXT NOT NULL, category TEXT, description TEXT, steps_json TEXT,"
        "icon TEXT, default_duration_min INTEGER, priority INTEGER DEFAULT 0,"
        "is_active INTEGER DEFAULT 1)"),
    "scenario_runs": (
        "CREATE TABLE IF NOT EXISTS scenario_runs ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "workstream_id INTEGER, template_id INTEGER, name TEXT, description TEXT,"
        "status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','active','completed','cancelled')),"
        "assigned_team_id INTEGER, lat REAL, lng REAL, scheduled_at TEXT,"
        "priority INTEGER DEFAULT 0, created_by INTEGER)"),
    "rally_points": (
        "CREATE TABLE IF NOT EXISTS rally_points ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "workstream_id INTEGER, name TEXT, category TEXT, lat REAL, lng REAL,"
        "radius_m INTEGER DEFAULT 50, active INTEGER DEFAULT 1,"
        "description TEXT, created_by INTEGER)"),
    "workstream_events": (
        "CREATE TABLE IF NOT EXISTS workstream_events ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "workstream_id INTEGER, type TEXT, lat REAL, lng REAL, incident_id INTEGER,"
        "team_id INTEGER, payload_json TEXT, created_at TEXT)"),
    "ws_links": (
        "CREATE TABLE IF NOT EXISTS ws_links ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "workstream_id INTEGER, title TEXT NOT NULL, url TEXT, kind TEXT DEFAULT 'form',"
        "description TEXT, is_active INTEGER DEFAULT 1, created_at TEXT)"),
    "user_workstreams": (
        "CREATE TABLE IF NOT EXISTS user_workstreams ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "user_id INTEGER, workstream_id INTEGER, role TEXT DEFAULT 'viewer')"),
}

_WS_ALTERS = {
    "teams": "workstream_id", "incidents": "workstream_id",
    "road_blocks": "workstream_id", "team_reports": "workstream_id",
    "manual_routes": "workstream_id", "routes": "workstream_id",
    "team_destinations": "workstream_id", "users": "workstream_id",
}

def _cols(conn, table):
    return [r[1] for r in conn.execute("PRAGMA table_info(%s)" % table)]

def migrate_ws(conn):
    """Idempotent Part A lane: ws tables + guarded ALTERs. Own DB only."""
    for name, ddl in _WS_TABLES.items():
        conn.execute(ddl)
    for table, col in _WS_ALTERS.items():
        try:
            if col not in _cols(conn, table):
                conn.execute("ALTER TABLE %s ADD COLUMN %s INTEGER" % (table, col))
        except Exception:
            pass
    conn.commit()
