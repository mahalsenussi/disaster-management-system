"""
Marine data collector from Copernicus Marine (MEDSEA) with mock fallback.

Uses the `copernicusmarine` Python package (installed on the server, v2.4.1) to pull:
  - Sea surface horizontal velocity (uo/vo): cmems_mod_med_phy-cur_anfc_4.2km-2D_PT1H-m
  - Sea surface height (zos):              cmems_mod_med_phy-ssh_anfc_4.2km_P1D-m

If CMEMS credentials are not configured (COPERNICUS_USERNAME/COPERNICUS_PASSWORD env,
or ~/.copernicusmarine/.copernicusmarine-credentials), a deterministic mock grid is
generated so the frontend works end-to-end until real login is enabled.
"""
import os
import math
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

from evaluation_service.core.logger import get_logger
from evaluation_service.modules.marine.validator import MarineValidator

logger = get_logger()

# Libya box + transit corridor (lon9..26, lat29..35.2) at ~0.25deg grid for frontend perf
DEFAULT_BBOX = {'min_lon': 9.0, 'max_lon': 26.0, 'min_lat': 29.0, 'max_lat': 35.2}
GRID_STEP = 0.25

# Known departure points / coastal zones used to emit vessel-risk clusters
ZONES = [
    {'zone': 'Zuwara', 'lat': 32.93, 'lon': 12.09},
    {'zone': 'Sabratha', 'lat': 32.80, 'lon': 12.48},
    {'zone': 'Tripoli', 'lat': 32.89, 'lon': 13.19},
    {'zone': 'Al Khums', 'lat': 32.65, 'lon': 14.27},
    {'zone': 'Misrata', 'lat': 32.38, 'lon': 15.09},
    {'zone': 'Sirte', 'lat': 31.20, 'lon': 16.59},
    {'zone': 'Benghazi', 'lat': 32.12, 'lon': 20.07},
    {'zone': 'Derna', 'lat': 32.76, 'lon': 22.64},
    {'zone': 'Tobruk', 'lat': 32.08, 'lon': 23.98},
]

CURRENT_DATASET = 'cmems_mod_med_phy-cur_anfc_4.2km-2D_PT1H-m'
SSH_DATASET = 'cmems_mod_med_phy-ssh_anfc_4.2km_P1D-m'


class MarineCollector:
    """Collects sea currents, sea surface height and derived vessel risk."""

    def __init__(self):
        self.validator = MarineValidator()
        self.copernicus_username = os.environ.get('COPERNICUS_USERNAME')
        self.copernicus_password = os.environ.get('COPERNICUS_PASSWORD')

    def has_credentials(self) -> bool:
        return bool(self.copernicus_username and self.copernicus_password)

    @staticmethod
    def login_hint() -> str:
        return ("Run `copernicusmarine login` on the server or set COPERNICUS_USERNAME/"
                "COPERNICUS_PASSWORD env for the evaluation service to enable real CMEMS data.")

    # ------------------------------------------------------------------ currents
    def collect_currents(self, bbox: Dict = None) -> tuple[bool, str, List[Dict]]:
        """Collect sea surface velocity grid for the box.

        Returns: (success, source_message, rows)
        """
        bbox = bbox or DEFAULT_BBOX
        if self.has_credentials():
            rows = self._collect_currents_cmems(bbox)
            if rows:
                message = f"Sea currents collected from CMEMS {CURRENT_DATASET}"
                logger.info(message, module='MARINE_COLLECTOR')
                return True, message, rows
            logger.warning("CMEMS current pull failed, using mock", module='MARINE_COLLECTOR')
        rows = self._mock_currents(bbox)
        message = "Sea currents mock data (no CMEMS credentials)"
        logger.info(message, module='MARINE_COLLECTOR')
        return True, message, rows

    def _collect_currents_cmems(self, bbox: Dict) -> List[Dict]:
        try:
            import copernicusmarine
            now = datetime.now(timezone.utc)
            start = now - timedelta(hours=1)
            result = copernicusmarine.subset(
                dataset_id=CURRENT_DATASET,
                variables=['uo', 'vo'],
                minimum_longitude=bbox['min_lon'],
                maximum_longitude=bbox['max_lon'],
                minimum_latitude=bbox['min_lat'],
                maximum_latitude=bbox['max_lat'],
                start_datetime=start,
                end_datetime=now,
            )
            import xarray as xr
            ds = xr.open_dataset(result.file_path)
            uo = ds['uo'].isel(time=-1).values
            vo = ds['vo'].isel(time=-1).values
            lats = ds['latitude'].values
            lons = ds['longitude'].values
            rows = []
            for i, lat in enumerate(lats):
                for j, lon in enumerate(lons):
                    u = float(uo[i, j])
                    v = float(vo[i, j])
                    rows.append(self._grid_row(now, float(lat), float(lon), u, v))
            return rows
        except Exception as e:
            logger.error(f"CMEMS current collection failed: {e}",
                         module='MARINE_COLLECTOR', exc_info=True)
            return []

    def _mock_currents(self, bbox: Dict) -> List[Dict]:
        """Deterministic spatially-smooth mock current field (m/s)."""
        now = datetime.now(timezone.utc)
        rng = random.Random(42)
        rows = []
        lat = bbox['min_lat']
        while lat <= bbox['max_lat']:
            lon = bbox['min_lon']
            while lon <= bbox['max_lon']:
                # coherent patterns: longshore jet off the coast + meanders
                u = 0.18 * math.sin((lon - 9) / 5.0) + 0.05 * math.sin(lat / 0.8)
                v = 0.12 * math.cos((lon - 15) / 4.0) + 0.04 * math.sin(lat / 1.3)
                if abs(lat - 32.0) < 1.0:
                    u += 0.15  # stronger alongshore flow near shelf break
                u = round(u, 3)
                v = round(v, 3)
                rows.append({**self._grid_row(now, lat, lon, u, v), 'src': 'mock'})
                lon = round(lon + GRID_STEP, 4)
            lat = round(lat + GRID_STEP, 4)
        return rows

    @staticmethod
    def _grid_row(now, lat, lon, u, v) -> Dict:
        speed = math.hypot(u, v)
        direction = math.degrees(math.atan2(v, u)) % 360
        return {
            'time': now.isoformat(),
            'lat': round(lat, 4),
            'lon': round(lon, 4),
            'uo': round(u, 4),
            'vo': round(v, 4),
            'speed': round(speed, 4),
            'direction_deg': round(direction, 1),
            'src': CURRENT_DATASET,
        }

    # ------------------------------------------------------------------ ssh
    def collect_ssh(self, bbox: Dict = None) -> tuple[bool, str, List[Dict]]:
        """Collect sea surface height grid for the box."""
        bbox = bbox or DEFAULT_BBOX
        if self.has_credentials():
            rows = self._collect_ssh_cmems(bbox)
            if rows:
                message = f"Sea surface height collected from CMEMS {SSH_DATASET}"
                logger.info(message, module='MARINE_COLLECTOR')
                return True, message, rows
            logger.warning("CMEMS SSH pull failed, using mock", module='MARINE_COLLECTOR')
        rows = self._mock_ssh(bbox)
        return True, "Sea surface height mock data (no CMEMS credentials)", rows

    def _collect_ssh_cmems(self, bbox: Dict) -> List[Dict]:
        try:
            import copernicusmarine
            now = datetime.now(timezone.utc)
            start = now - timedelta(days=1)
            result = copernicusmarine.subset(
                dataset_id=SSH_DATASET,
                variables=['zos'],
                minimum_longitude=bbox['min_lon'],
                maximum_longitude=bbox['max_lon'],
                minimum_latitude=bbox['min_lat'],
                maximum_latitude=bbox['max_lat'],
                start_datetime=start,
                end_datetime=now,
            )
            import xarray as xr
            ds = xr.open_dataset(result.file_path)
            zos = ds['zos'].isel(time=-1).values
            lats = ds['latitude'].values
            lons = ds['longitude'].values
            rows = []
            for i, lat in enumerate(lats):
                for j, lon in enumerate(lons):
                    rows.append({
                        'time': now.isoformat(),
                        'lat': round(float(lat), 4),
                        'lon': round(float(lon), 4),
                        'zos': round(float(zos[i, j]), 4),
                        'src': SSH_DATASET,
                    })
            return rows
        except Exception as e:
            logger.error(f"CMEMS SSH collection failed: {e}", module='MARINE_COLLECTOR', exc_info=True)
            return []

    def _mock_ssh(self, bbox: Dict) -> List[Dict]:
        now = datetime.now(timezone.utc).isoformat()
        rng = random.Random(7)
        rows = []
        lat = bbox['min_lat']
        while lat <= bbox['max_lat']:
            lon = bbox['min_lon']
            while lon <= bbox['max_lon']:
                zos = 0.05 * math.sin((lon - 9) / 6.0) + 0.03 * math.cos((lat - 29) / 4.0)
                if abs(lat - 32.0) < 0.8:
                    zos += 0.03  # slight elevation along the shelf
                rows.append({
                    'time': now,
                    'lat': round(lat, 4),
                    'lon': round(lon, 4),
                    'zos': round(zos, 4),
                    'src': 'mock',
                })
                lon = round(lon + GRID_STEP, 4)
            lat = round(lat + GRID_STEP, 4)
        return rows

    # ------------------------------------------------------------------ vessel risk
    def compute_vessel_risk(self, currents: List[Dict], ssh: List[Dict],
                            coastal_data: Dict[str, Dict]) -> List[Dict]:
        """Composite small-vessel capsize risk per known zone.

        risk = f(wave_height, wave_period, wind_speed, current_speed, sea_level_anomaly)
        Danger thresholds designed for small craft / migrant boats. Returns rows.
        """
        clat = {c['lat']: c for c in currents}
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for zone in ZONES:
            lat = zone['lat']
            lon = zone['lon']
            ind = self._nearest_index(zone, currents)
            cur = currents[ind] if currents else {}
            cur_speed = cur.get('speed', 0.0) or 0.0

            coastal = coastal_data.get(zone['zone'], {}) or {}
            wave_h = coastal.get('wave_height') or 0.8
            wave_p = coastal.get('wave_period') or 8.0
            wind = coastal.get('wind_speed') or 5.0
            sla = coastal.get('sea_level_anomaly') or 0.0

            score = self._risk_score(wave_h, wave_p, wind, cur_speed, sla)
            level = 'LOW'
            if score >= 0.7:
                level = 'EXTREME'
            elif score >= 0.5:
                level = 'HIGH'
            elif score >= 0.3:
                level = 'MEDIUM'

            rows.append({
                'time': now,
                'lat': round(lat, 4),
                'lon': round(lon, 4),
                'zone': zone['zone'],
                'risk_score': round(score, 3),
                'danger_level': level,
                'wave_height': round(wave_h, 2),
                'wave_period': round(wave_p, 1),
                'wind_speed': round(wind, 2),
                'current_speed': round(cur_speed, 3),
                'sea_level_anomaly': round(sla, 3),
                'evaluation': None,
                'evaluated_at': None,
            })
        return rows

    @staticmethod
    def _nearest_index(zone: Dict, rows: List[Dict]) -> int:
        best, best_d = None, 1e9
        for i, r in enumerate(rows):
            d = (r['lat'] - zone['lat']) ** 2 + (r['lon'] - zone['lon']) ** 2
            if d < best_d:
                best_d, best = d, i
        return best or 0

    # ------------------------------------------------------------- orchestration
    def collect_currents_and_save(self) -> tuple[bool, str]:
        from evaluation_service.modules.marine.service import MarineService
        success, message, rows = self.collect_currents()
        if not success or not rows:
            return False, message
        svc = MarineService()
        ok, save_msg, _ = svc.save_currents(rows)
        return ok, f"{message}. {save_msg}"

    def collect_ssh_and_save(self) -> tuple[bool, str]:
        from evaluation_service.modules.marine.service import MarineService
        success, message, rows = self.collect_ssh()
        if not success or not rows:
            return False, message
        svc = MarineService()
        ok, save_msg, _ = svc.save_ssh(rows)
        return ok, f"{message}. {save_msg}"

    def collect_risk_and_save(self, coastal_data: Dict[str, Dict] = None) -> tuple[bool, str]:
        """Pull currents+ssh, derive vessel risk, persist it. Returns (ok, message)."""
        from evaluation_service.modules.marine.service import MarineService
        coastal_data = coastal_data or {}
        ok_c, msg_c, currents = self.collect_currents()
        ok_s, msg_s, ssh = self.collect_ssh()
        if not ok_c:
            return False, msg_c
        svc = MarineService()
        save_ok, save_msg, _ = svc.save_currents(currents)
        if ok_s:
            svc.save_ssh(ssh)
        rows = self.compute_vessel_risk(currents, ssh, coastal_data)
        ok, risk_msg, _ = svc.save_vessel_risk(rows)
        return ok, f"{msg_c} | {msg_s} | {risk_msg}"

    @staticmethod
    def _risk_score(wave_h, wave_p, wind, cur, sla) -> float:
        """Weighted composite risk 0..1 for small boats."""
        w_h = max(0.0, min(1.0, (wave_h - 0.5) / 2.5))
        w_p = max(0.0, min(1.0, (9.0 - wave_p) / 3.0)) if wave_p else 0.3
        w_w = max(0.0, min(1.0, (wind - 5.0) / 15.0))
        w_c = max(0.0, min(1.0, (cur - 0.2) / 0.8))
        w_sla = max(0.0, min(1.0, abs(sla) / 0.6))
        return 0.35 * w_h + 0.25 * w_p + 0.2 * w_w + 0.12 * w_c + 0.08 * w_sla