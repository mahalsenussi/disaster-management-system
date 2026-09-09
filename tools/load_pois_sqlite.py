#!/usr/bin/env python3
"""Load the extracted POI CSV into the LRC points_of_interest table.
Usage: POI_DB=/path/to/disaster_ops.db python3 load_pois_sqlite.py /tmp/libya_pois.csv
"""
import csv
import os
import sqlite3
import sys

DB = os.environ['POI_DB']

CATEGORY_MAP = {
    'hospital', 'clinic', 'doctors', 'pharmacy', 'police', 'fire_station',
    'school', 'university', 'kindergarten', 'bank', 'fuel',
}


def main():
    if len(sys.argv) < 2:
        print('usage: load_pois_sqlite.py <csv>')
        sys.exit(1)
    conn = sqlite3.connect(DB, timeout=60.0)
    conn.execute('PRAGMA journal_mode=WAL')
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS points_of_interest (
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
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    cur.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_poi_osm ON points_of_interest(osm_type, osm_id)')

    inserted = updated = skipped = 0
    with open(sys.argv[1], encoding='utf-8') as f:
        for row in csv.DictReader(f):
            cat = row['category']
            if cat not in CATEGORY_MAP:
                skipped += 1
                continue
            name = (row['name'] or '').strip()
            ot, oid = row['osm_type'], row['osm_id']
            try:
                lat = float(row['lat'])
                lng = float(row['lng'])
            except ValueError:
                skipped += 1
                continue
            cur.execute('SELECT 1 FROM points_of_interest WHERE osm_type = ? AND osm_id = ?', (ot, oid))
            if cur.fetchone():
                cur.execute(
                    '''
                    UPDATE points_of_interest
                    SET name = CASE WHEN ? <> '' THEN ? ELSE name END,
                        category = ?, lat = ?, lng = ?,
                        is_active = 1, updated_at = CURRENT_TIMESTAMP
                    WHERE osm_type = ? AND osm_id = ?
                    ''',
                    (name, name, cat, lat, lng, ot, oid),
                )
                updated += 1
            else:
                cur.execute(
                    '''
                    INSERT INTO points_of_interest (name, category, lat, lng, osm_type, osm_id, source)
                    VALUES (?, ?, ?, ?, ?, ?, 'osm')
                    ''',
                    (name or None, cat, lat, lng, ot, oid),
                )
                inserted += 1
    conn.commit()
    conn.close()
    print(f'inserted={inserted} updated={updated} skipped={skipped}')


if __name__ == '__main__':
    main()