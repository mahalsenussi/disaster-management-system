#!/usr/bin/env python3
"""
Script to populate the database with sample data for testing.
"""

import sqlite3
import os

DATABASE = os.path.join(os.path.dirname(__file__), 'database', 'disaster_ops.db')

def populate_sample_data():
    """Populate database with sample incidents, teams, and routes."""
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Sample incidents (Libya locations)
    incidents = [
        {
            'type': 'Fire',
            'severity': 'high',
            'lat': 32.8872,
            'lng': 13.1913,
            'status': 'open'
        },
        {
            'type': 'Medical Emergency',
            'severity': 'medium',
            'lat': 32.9000,
            'lng': 13.2000,
            'status': 'open'
        },
        {
            'type': 'Flood',
            'severity': 'high',
            'lat': 32.8500,
            'lng': 13.1500,
            'status': 'open'
        },
        {
            'type': 'Traffic Accident',
            'severity': 'low',
            'lat': 32.9200,
            'lng': 13.1800,
            'status': 'open'
        },
        {
            'type': 'Structural Collapse',
            'severity': 'high',
            'lat': 32.8700,
            'lng': 13.2200,
            'status': 'open'
        }
    ]
    
    # Sample teams
    teams = [
        {
            'name': 'Team Alpha - Tripoli',
            'lat': 32.8800,
            'lng': 13.1900,
            'status': 'available'
        },
        {
            'name': 'Team Beta - Benghazi',
            'lat': 32.1160,
            'lng': 20.0690,
            'status': 'available'
        },
        {
            'name': 'Team Gamma - Misrata',
            'lat': 32.3750,
            'lng': 15.0900,
            'status': 'available'
        },
        {
            'name': 'Team Delta - Sabha',
            'lat': 27.0300,
            'lng': 14.4300,
            'status': 'available'
        },
        {
            'name': 'Team Epsilon - Zuwara',
            'lat': 32.9300,
            'lng': 12.0800,
            'status': 'available'
        }
    ]
    
    # Clear existing data
    cursor.execute('DELETE FROM routes')
    cursor.execute('DELETE FROM incidents')
    cursor.execute('DELETE FROM teams')
    
    # Insert incidents
    for incident in incidents:
        cursor.execute('''
            INSERT INTO incidents (type, severity, lat, lng, status)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            incident['type'],
            incident['severity'],
            incident['lat'],
            incident['lng'],
            incident['status']
        ))
    
    # Insert teams
    for team in teams:
        cursor.execute('''
            INSERT INTO teams (name, lat, lng, status)
            VALUES (?, ?, ?, ?)
        ''', (
            team['name'],
            team['lat'],
            team['lng'],
            team['status']
        ))
    
    conn.commit()
    
    # Verify data
    cursor.execute('SELECT COUNT(*) FROM incidents')
    incident_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM teams')
    team_count = cursor.fetchone()[0]
    
    conn.close()
    
    print(f"Sample data populated successfully!")
    print(f"- {incident_count} incidents created")
    print(f"- {team_count} teams created")

if __name__ == '__main__':
    populate_sample_data()
