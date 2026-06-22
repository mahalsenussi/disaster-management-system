#!/usr/bin/env python3
"""
Phase 0 RBAC Database Migration Script
Creates branches, users, audit_logs tables
Recreates teams and incidents with foreign keys
"""

import sqlite3
import os
from datetime import datetime

DATABASE = os.path.join(os.path.dirname(__file__), 'database', 'disaster_ops.db')

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def migrate():
    conn = get_db()
    cursor = conn.cursor()
    
    print("Starting Phase 0 RBAC migration...")
    
    # 1. Create branches table
    print("1. Creating branches table...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS branches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            city TEXT NOT NULL,
            region TEXT NOT NULL,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            geo_json TEXT,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 2. Create default branch
    print("2. Creating default branch...")
    cursor.execute('''
        INSERT OR IGNORE INTO branches (id, name, city, region, lat, lng)
        VALUES (1, 'Benghazi (Default)', 'Benghazi', 'East', 32.1165, 20.0666)
    ''')
    
    # 3. Create users table (RBAC)
    print("3. Creating users table...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'regional_admin', 'operator')),
            branch_id INTEGER,
            region TEXT,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (branch_id) REFERENCES branches(id)
        )
    ''')
    
    # 4. Create audit_logs table
    print("4. Creating audit_logs table...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            team_id INTEGER,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id INTEGER,
            old_values TEXT,
            new_values TEXT,
            ip_address TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (team_id) REFERENCES teams(id)
        )
    ''')
    
    # 5. Add branch_id columns to existing tables
    print("5. Adding branch_id columns...")
    
    try:
        cursor.execute('ALTER TABLE teams ADD COLUMN branch_id INTEGER DEFAULT 1')
        print("   Added branch_id to teams")
    except sqlite3.OperationalError:
        print("   teams.branch_id already exists")
    
    try:
        cursor.execute('ALTER TABLE incidents ADD COLUMN branch_id INTEGER DEFAULT 1')
        print("   Added branch_id to incidents")
    except sqlite3.OperationalError:
        print("   incidents.branch_id already exists")
    
    try:
        cursor.execute('ALTER TABLE incidents ADD COLUMN is_active BOOLEAN DEFAULT 1')
        print("   Added is_active to incidents")
    except sqlite3.OperationalError:
        print("   incidents.is_active already exists")
    
    # 6. Create indexes
    print("6. Creating indexes...")
    indexes = [
        'CREATE INDEX IF NOT EXISTS idx_teams_branch_id ON teams(branch_id)',
        'CREATE INDEX IF NOT EXISTS idx_teams_last_updated ON teams(last_updated)',
        'CREATE INDEX IF NOT EXISTS idx_incidents_branch_id ON incidents(branch_id)',
        'CREATE INDEX IF NOT EXISTS idx_users_branch_id ON users(branch_id)',
        'CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)',
        'CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id)',
        'CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON audit_logs(entity_type, entity_id)',
    ]
    for idx_sql in indexes:
        try:
            cursor.execute(idx_sql)
        except sqlite3.OperationalError as e:
            print(f"   Index skipped: {e}")
    
    # 7. Add incident_id to routes if not exists
    print("7. Adding incident_id to routes...")
    try:
        cursor.execute('ALTER TABLE routes ADD COLUMN incident_id INTEGER')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_routes_incident_id ON routes(incident_id)')
        print("   Added incident_id to routes")
    except sqlite3.OperationalError:
        print("   incident_id already exists")
    
    # 8. Migrate existing teams to default branch
    print("8. Migrating teams to default branch...")
    cursor.execute('UPDATE teams SET branch_id = 1 WHERE branch_id IS NULL')
    
    # 9. Migrate existing incidents to default branch
    print("9. Migrating incidents to default branch...")
    cursor.execute('UPDATE incidents SET branch_id = 1 WHERE branch_id IS NULL')
    
    # 10. Create default admin user (password: admin123)
    print("10. Creating default admin user...")
    import bcrypt
    password_hash = bcrypt.hashpw('admin123'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    cursor.execute('''
        INSERT OR IGNORE INTO users (id, username, password_hash, role, branch_id, region)
        VALUES (1, 'admin', ?, 'admin', NULL, NULL)
    ''', (password_hash,))
    
    conn.commit()
    conn.close()
    
    print("\n✅ Migration complete!")
    print("Default admin: username='admin', password='admin123'")
    print("⚠️  CHANGE DEFAULT PASSWORD IN PRODUCTION!")

if __name__ == '__main__':
    migrate()
