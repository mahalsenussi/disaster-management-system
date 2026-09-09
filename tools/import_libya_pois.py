#!/usr/bin/env python3
"""Import Points of Interest for all of Libya from the OpenStreetMap Overpass API.

Writes into the points_of_interest table of the project DB (disaster_ops.db).
Idempotent: rows are upserted keyed on (osm_type, osm_id).

Usage:
  POI_DB=/path/to/disaster_ops.db python3 import_libya_pois.py
"""

import json
import os
import sqlite3
import sys
import time
import urllib.request
import urllib.parse

DEFAULT_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'public_app', 'database', 'disaster_ops.db')
DB = os.environ.get('POI_DB', DEFAULT_DB)
# Public Overpass mirrors (main endpoint is often unreachable/rate-limited)
MIRRORS = [
    os.environ.get('OVERPASS_URL'),
    'https://overpass.kumi.systems/api/interpreter',
    'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
    'https://overpass-api.de/api/interpreter',
]
MIRRORS = [m for m in MIRRORS if m]

# Libya bounding box: (min lat, min lng, max lat, max lng)
BBOX = (19.4, 9.3, 33.4, 25.3)

# OSM amenity value -> our category
CATEGORIES = {
    'hospital': 'hospital',
    'clinic': 'clinic',
    'doctors': 'doctors',
    'pharmacy': 'pharmacy',
    'police': 'police',
    'fire_station': 'fire_station',
    'school': 'school',
    'university': 'university',
    'kindergarten': 'kindergarten',
    'bank': 'bank',
    'fuel': 'fuel',
}


def overpass_query(query):
    """POST an Overpass query across mirrors and return parsed JSON.
    Retries each mirror a few times with backoff."""
    data = urllib.parse.urlencode({'data': query}).encode('utf-8')
    last_err = None
    for mirror in MIRRORS:
        for attempt in range(3):
            try:
                req = urllib.request.Request(mirror, data=data)
                with urllib.request.urlopen(req, timeout=180) as resp:
                    body = resp.read().decode('utf-8')
                if not body.strip():
                    raise RuntimeError('empty response')
                return json.loads(body)
            except Exception as e:
                last_err = e
                time.sleep(4 * (attempt + 1))
    raise SystemExit(f'Overpass query failed after retries: {last_err}')


def pull_category(amenity):
    s, w, n, e = BBOX
    query = (
        f'[out:json][timeout:180];'
        f'(node["amenity"="{amenity}"]({s},{w},{n},{e});'
        f' way["amenity"="{amenity}"]({s},{w},{n},{e}););'
        f'out center tags;'
    )
    return overpass_query(query)


def extract_location(el):
    """Return (lat, lng) for a node or a way (center)."""
    if el.get('center'):
        return el['center']['lat'], el['center']['lon']
    if el.get('lat') is not None:
        return el['lat'], el['lon']
    return None, None


def address_from_tags(tags):
    parts = []
    for key in ('addr:street', 'addr:housenumber', 'addr:city', 'addr:postcode'):
        if tags.get(key):
            parts.append(tags[key])
    return ', '.join(parts) if parts else None


def best_tags(tags, *keys):
    """First key that exists (supports contact: namespace)."""
    for key in keys:
        if tags.get(key):
            return tags[key]
    return None


def upsert(conn, row):
    conn.execute(
        '''
        INSERT INTO points_of_interest
            (name, category, lat, lng, osm_type, osm_id, address, phone, website, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'osm')
        ON CONFLICT(osm_type, osm_id) DO UPDATE SET
            name = excluded.name,
            category = excluded.category,
            lat = excluded.lat,
            lng = excluded.lng,
            address = excluded.address,
            phone = excluded.phone,
            website = excluded.website,
            is_active = 1,
            updated_at = CURRENT_TIMESTAMP
        ''',
        row,
    )


def main():
    conn = sqlite3.connect(DB, timeout=30.0)
    conn.execute('PRAGMA journal_mode=WAL')
    total_new = total_upd = 0

    for amenity, category in CATEGORIES.items():
        try:
            data = pull_category(amenity)
        except SystemExit as e:
            print(f'[{amenity}] SKIPPED: {e}')
            continue

        inserted = updated = 0
        for el in data.get('elements', []):
            tags = el.get('tags', {})
            if not tags:
                continue
            lat, lng = extract_location(el)
            if lat is None or lng is None:
                continue
            osm_id = str(el['id'])
            osm_type = el['type']
            phone = best_tags(tags, 'phone', 'contact:phone')
            website = best_tags(tags, 'website', 'contact:website')
            row = (
                tags.get('name') or tags.get('name:en'),
                category,
                lat,
                lng,
                osm_type,
                osm_id,
                address_from_tags(tags),
                phone,
                website,
            )
            cur = conn.execute(
                '''
                SELECT 1 FROM points_of_interest WHERE osm_type = ? AND osm_id = ?
                ''',
                (osm_type, osm_id),
            )
            if cur.fetchone():
                conn.execute(
                    '''
                    UPDATE points_of_interest
                    SET name = ?, category = ?, lat = ?, lng = ?, address = ?,
                        phone = ?, website = ?, is_active = 1, updated_at = CURRENT_TIMESTAMP
                    WHERE osm_type = ? AND osm_id = ?
                    ''',
                    row + (osm_type, osm_id),
                )
                updated += 1
            else:
                upsert(conn, row)
                inserted += 1

        conn.commit()
        total_new += inserted
        total_upd += updated
        print(f'[{category:13s}] {amenity:13s} new={inserted:5d} updated={updated:5d}')
        time.sleep(2)  # be polite to the public Overpass instance

    conn.close()
    print(f'\nDONE: {total_new} inserted, {total_upd} updated into {DB}')


if __name__ == '__main__':
    main()