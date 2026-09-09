#!/usr/bin/env python3
"""Clean demo incidents/teams and seed the 38 real LRC branch teams.

Team numbers 101..138 match the official LRC branch code order.
Creates a timestamped backup of the DB before touching anything.
Run:  python3 tools/clean_and_seed_teams.py [database/disaster_ops.db]
"""
import sqlite3
import shutil
import sys
import time

DB = sys.argv[1] if len(sys.argv) > 1 else "database/disaster_ops.db"

backup = f"{DB}.backup-{time.strftime('%Y%m%d-%H%M%S')}"
shutil.copy2(DB, backup)

# (code, arabic_name, english_branch_name)
TEAMS = [
    (101, "بنغازي",   "Benghazi"),
    (102, "سبها",      "Sabha"),
    (103, "مصراتة",    "Misrata"),
    (104, "البيضاء",   "Bayda"),
    (105, "اجدابيا",   "Ajdabiya"),
    (106, "درنة",      "Derna"),
    (107, "الزاوية",   "Zawiya"),
    (108, "طرابلس",    "Tripoli"),
    (109, "المرج",     "Al Marj"),
    (110, "زوارة",     "Zuwara"),
    (111, "سرت",       "Sirte"),
    (112, "أوباري",    "Ubari"),
    (113, "هون",       "Hun"),
    (114, "طبرق",      "Tobruk"),
    (115, "الخمس",     "Al Khums"),
    (116, "غريان",     "Gharyan"),
    (117, "الكفرة",    "Kufra"),
    (118, "ترهونة",    "Tarhuna"),
    (119, "جالو",      "Jalu"),
    (120, "مرزق",      "Murzuq"),
    (121, "صبراتة",    "Sabratha"),
    (122, "نالوت",     "Nalut"),
    (123, "غدامس",     "Ghadames"),
    (124, "بني وليد",  "Bani Walid"),
    (125, "الجفارة",   "Al Jafara"),
    (126, "غات",       "Ghat"),
    (127, "وادي الشاطئ", "Ash Shati"),
    (128, "القبة",     "Al Qubah"),
    (129, "يفرن",      "Yafran"),
    (130, "شحات",      "Shahhat"),
    (131, "زليتن",     "Zliten"),
    (132, "الجميل",    "Al Jamil"),
    (133, "العجيلات",  "Al Ajaylat"),
    (134, "الأبيار",   "Al Abyar"),
    (135, "توكرة",     "Tocra"),
    (136, "الساحل",    "Al Sahel"),
    (137, "الزنتان",   "Zintan"),
    (138, "سلوق",      "Suluq"),
]

conn = sqlite3.connect(DB, timeout=30)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

def clean_refs(table, col, ids):
    """Unlink child rows referencing removed ids: NULL when allowed, else delete the row."""
    if not ids:
        return (0, 0)
    ph = ",".join("?" * len(ids))
    try:
        cur.execute(f"UPDATE {table} SET {col} = NULL WHERE {col} IN ({ph})", ids)
        return (cur.rowcount, 0)
    except sqlite3.IntegrityError:
        cur.execute(f"DELETE FROM {table} WHERE {col} IN ({ph})", ids)
        return (0, cur.rowcount)

# ---------- 1. Clean incidents ----------
inc_ids = [r["id"] for r in cur.execute("SELECT id FROM incidents").fetchall()]
if inc_ids:
    ph = ",".join("?" * len(inc_ids))
    cur.execute(f"DELETE FROM incident_logs WHERE incident_id IN ({ph})", inc_ids)
    cur.execute(f"DELETE FROM incident_reports WHERE incident_id IN ({ph})", inc_ids)
    cur.execute(f"DELETE FROM team_reports WHERE incident_id IN ({ph})", inc_ids)
    clean_refs("routes", "incident_id", inc_ids)
    clean_refs("manual_routes", "incident_id", inc_ids)
    clean_refs("daily_report_items", "incident_id", inc_ids)
    cur.execute(f"DELETE FROM incidents WHERE id IN ({ph})", inc_ids)
print(f"incidents cleaned: {len(inc_ids)} removed")

# ---------- 2. Clean demo teams ----------
team_ids = [r["id"] for r in cur.execute("SELECT id FROM teams").fetchall()]
if team_ids:
    ph = ",".join("?" * len(team_ids))
    cur.execute(f"DELETE FROM team_reports WHERE team_id IN ({ph})", team_ids)
    clean_refs("routes", "team_id", team_ids)
    clean_refs("manual_routes", "team_id", team_ids)
    cur.execute(f"DELETE FROM teams WHERE id IN ({ph})", team_ids)
print(f"teams cleaned: {len(team_ids)} removed")

# ---------- 3. Seed LRC teams ----------
branch_ids = {}
for r in cur.execute("SELECT id, name, lat, lng FROM branches WHERE is_active = 1").fetchall():
    branch_ids[r["name"]] = r

created = 0
for code, ar, en in TEAMS:
    branch = branch_ids.get(en)
    if not branch:
        print(f"  !! branch not found for {en} ({ar}) - skipped")
        continue
    cur.execute("SELECT 1 FROM teams WHERE team_number = ?", (str(code),))
    if cur.fetchone():
        continue
    name = f"فريق {ar} ({en})"
    cur.execute("""
        INSERT INTO teams
            (team_number, name, lat, lng, status, current_status, color, icon,
             battery_level, speed, heading, gps_enabled, branch_id, created_at, updated_at)
        VALUES (?,?,?,?, 'available', 'available', '#3498db', '🚑', 100, 0.0, 0.0, 1, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (str(code), name, branch["lat"], branch["lng"], branch["id"]))
    created += 1

conn.commit()

total_teams = cur.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
total_inc = cur.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
conn.close()

print(f"teams seeded: {created} (total now {total_teams})")
print(f"incidents now: {total_inc}")
print(f"backup saved: {backup}")