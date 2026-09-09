#!/usr/bin/env python3
"""Extract target POI categories from the local Geofabrik OSM shapefile
extract and emit a CSV for loading into the LRC points_of_interest table.

Input dir: /mnt/ssd/hdd/Downloads/libya-260907-free.shp (or POI_SHP_DIR env)
Output: /tmp/libya_pois.csv (or POI_CSV_OUT env)
"""
import csv
import os
import sys

import shapefile

SHP_DIR = os.environ.get('POI_SHP_DIR', '/mnt/ssd/hdd/Downloads/libya-260907-free.shp')
CSV_OUT = os.environ.get('POI_CSV_OUT', '/tmp/libya_pois.csv')

CATEGORY_MAP = {
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

LAYERS = [
    ('gis_osm_pois_free_1', 'node'),
    ('gis_osm_pois_a_free_1', 'way'),
    ('gis_osm_traffic_free_1', 'node'),
]

TRAFFIC_ONLY_FC = {'fuel'}


def ring_centroid(ring):
    ring = list(ring)
    if len(ring) < 3:
        return sum(p[1] for p in ring) / len(ring), sum(p[0] for p in ring) / len(ring)
    a = cx = cy = 0.0
    n = len(ring)
    for i in range(n):
        j = (i + 1) % n
        x0, y0 = ring[i]
        x1, y1 = ring[j]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(a) < 1e-9:
        return ring[0][1], ring[0][0]
    a *= 0.5
    return cy / (6 * a), cx / (6 * a)


def polygon_centroid(shp):
    if not shp.points:
        return None, None
    parts = list(shp.parts) + [len(shp.points)]
    best = []
    for i in range(len(shp.parts)):
        ring = shp.points[parts[i]:parts[i + 1]]
        if len(ring) > len(best):
            best = ring
    if len(best) < 3:
        best = shp.points[parts[0]:parts[1]]
    return ring_centroid(best)


def main():
    found = {}
    for theme, osm_type in LAYERS:
        path = os.path.join(SHP_DIR, theme)
        if not os.path.exists(path + '.shp'):
            print(f'skip: {path} not found')
            continue
        reader = shapefile.Reader(path)
        fields = [f[0] for f in reader.fields[1:]]
        for rec, shp in zip(reader.records(), reader.shapes()):
            d = dict(zip(fields, rec))
            fclass = d.get('fclass', '')
            if fclass not in CATEGORY_MAP:
                continue
            if theme == 'gis_osm_traffic_free_1' and fclass not in TRAFFIC_ONLY_FC:
                continue
            category = CATEGORY_MAP[fclass]
            name = (d.get('name') or '').strip()
            osm_id = str(d['osm_id'])
            if osm_type == 'way':
                lat, lng = polygon_centroid(shp)
            else:
                lat, lng = shp.points[0][1], shp.points[0][0]
            if lat is None or lng is None:
                continue
            key = (osm_type, osm_id)
            if key in found and found[key][0]:
                continue
            found[key] = (name, category, f"{lat:.7f}", f"{lng:.7f}", osm_id)

    with open(CSV_OUT, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['name', 'category', 'lat', 'lng', 'osm_type', 'osm_id'])
        for (osm_type, osm_id), (name, category, lat, lng, oid) in sorted(found.items()):
            writer.writerow([name, category, lat, lng, osm_type, oid])

    from collections import Counter
    cats = Counter(v[1] for v in found.values())
    print(f'{len(found)} unique POIs -> {CSV_OUT}')
    for c, n in sorted(cats.items()):
        print(f'  {c:14s} {n}')


if __name__ == '__main__':
    main()