"""
HDX Humanitarian API (HAPI) Client
Fetches standardized humanitarian indicators from hapi.humdata.org
"""
import time
import base64
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime
from evaluation_service.core.logger import get_logger

logger = get_logger()

HAPI_BASE_URL = "https://hapi.humdata.org/api/v2"

# HAPI themes relevant to Libya disaster management
HAPI_THEMES = {
    'idps': {
        'endpoint': '/affected-people/idps',
        'description': 'Internally Displaced Persons',
        'category': 'displacement',
        'priority': 'HIGH'
    },
    'refugees': {
        'endpoint': '/affected-people/refugees-persons-of-concern',
        'description': 'Refugees and Persons of Concern',
        'category': 'displacement',
        'priority': 'CRITICAL'
    },
    'humanitarian_needs': {
        'endpoint': '/affected-people/humanitarian-needs',
        'description': 'Humanitarian Needs Overview',
        'category': 'humanitarian_needs',
        'priority': 'CRITICAL'
    },
    'operational_presence': {
        'endpoint': '/coordination-context/operational-presence',
        'description': 'Humanitarian Operational Presence',
        'category': 'operational_presence',
        'priority': 'HIGH'
    },
    'funding': {
        'endpoint': '/coordination-context/funding',
        'description': 'Humanitarian Funding and Appeals',
        'category': 'funding',
        'priority': 'MEDIUM'
    },
    'conflict_events': {
        'endpoint': '/coordination-context/conflict-events',
        'description': 'Conflict Events',
        'category': 'conflict_security',
        'priority': 'CRITICAL'
    },
    'national_risk': {
        'endpoint': '/coordination-context/national-risk',
        'description': 'National Risk Assessment',
        'category': 'conflict_security',
        'priority': 'HIGH'
    },
    'food_security': {
        'endpoint': '/food-security-nutrition-poverty/food-security',
        'description': 'Food Security (IPC Phases)',
        'category': 'food_security',
        'priority': 'CRITICAL'
    },
    'food_prices': {
        'endpoint': '/food-security-nutrition-poverty/food-prices-market-monitor',
        'description': 'Food Prices and Market Monitor',
        'category': 'food_security',
        'priority': 'HIGH'
    },
    'population': {
        'endpoint': '/geography-infrastructure/baseline-population',
        'description': 'Baseline Population',
        'category': 'population',
        'priority': 'HIGH'
    },
    'rainfall': {
        'endpoint': '/climate/rainfall',
        'description': 'Rainfall and Anomalies',
        'category': 'climate_data',
        'priority': 'MEDIUM'
    }
}


class HAPIClient:
    """Client for HDX Humanitarian API (HAPI)"""

    def __init__(self, app_name: str = 'lrc-disaster-mgmt', email: str = 'info@lrc.org.ly'):
        self.base_url = HAPI_BASE_URL
        self.app_identifier = None
        self.session = requests.Session()
        self.session.headers.update({'Accept': 'application/json'})
        self._authenticate(app_name, email)

    def _authenticate(self, app_name: str, email: str):
        """Generate app identifier via HAPI"""
        try:
            resp = self.session.get(
                f"{self.base_url}/encode_app_identifier",
                params={'application': app_name, 'email': email},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                self.app_identifier = data.get('encoded_app_identifier')
                if self.app_identifier:
                    self.session.headers['X-HDX-HAPI-APP-IDENTIFIER'] = self.app_identifier
                    logger.info("HAPI authentication successful", module='HDX')
                else:
                    logger.warning("HAPI auth returned empty identifier, using unauthenticated", module='HDX')
            else:
                logger.warning(f"HAPI auth failed ({resp.status_code}), using unauthenticated", module='HDX')
        except Exception as e:
            logger.warning(f"HAPI auth error: {e}, using unauthenticated", module='HDX')

    def fetch_endpoint(self, theme_key: str, location_code: str = 'LBY',
                       admin_level: Optional[int] = None,
                       limit: int = 10000) -> List[Dict]:
        """Fetch data from a specific HAPI theme endpoint"""
        if theme_key not in HAPI_THEMES:
            logger.error(f"Unknown HAPI theme: {theme_key}", module='HDX')
            return []

        theme = HAPI_THEMES[theme_key]
        endpoint = theme['endpoint']

        params = {
            'location_code': location_code,
            'limit': limit
        }
        if admin_level is not None:
            params['admin_level'] = admin_level

        try:
            resp = self.session.get(f"{self.base_url}{endpoint}", params=params, timeout=30)

            if resp.status_code == 200:
                data = resp.json()
                records = data.get('data', [])
                logger.info(f"HAPI {theme_key}: fetched {len(records)} records", module='HDX')
                return records
            elif resp.status_code == 429:
                logger.warning(f"HAPI rate limited on {theme_key}, waiting 5s", module='HDX')
                time.sleep(5)
                return self.fetch_endpoint(theme_key, location_code, admin_level, limit)
            else:
                logger.error(f"HAPI {theme_key} error: {resp.status_code} - {resp.text[:200]}", module='HDX')
                return []
        except Exception as e:
            logger.error(f"HAPI {theme_key} exception: {e}", module='HDX')
            return []

    def fetch_all_themes(self, location_code: str = 'LBY') -> Dict[str, List[Dict]]:
        """Fetch data from all HAPI themes for Libya"""
        results = {}
        for theme_key in HAPI_THEMES:
            records = self.fetch_endpoint(theme_key, location_code)
            results[theme_key] = records
            time.sleep(0.5)  # polite delay between requests
        return results

    def fetch_metadata(self, endpoint_type: str = 'dataset',
                       location_code: Optional[str] = None,
                       limit: int = 1000) -> List[Dict]:
        """Fetch HAPI metadata (datasets, resources, locations, etc.)"""
        valid_types = ['dataset', 'resource', 'location', 'admin1', 'admin2',
                       'org', 'sector', 'data-availability']
        if endpoint_type not in valid_types:
            return []

        params = {'limit': limit}
        if location_code:
            params['location_code'] = location_code

        try:
            resp = self.session.get(
                f"{self.base_url}/metadata/{endpoint_type}",
                params=params, timeout=15
            )
            if resp.status_code == 200:
                return resp.json().get('data', [])
        except Exception as e:
            logger.error(f"HAPI metadata {endpoint_type} error: {e}", module='HDX')

        return []

    def fetch_with_pagination(self, theme_key: str, location_code: str = 'LBY',
                              page_size: int = 10000) -> List[Dict]:
        """Fetch all records with automatic pagination"""
        all_records = []
        offset = 0

        while True:
            if theme_key not in HAPI_THEMES:
                break

            endpoint = HAPI_THEMES[theme_key]['endpoint']
            params = {
                'location_code': location_code,
                'limit': page_size,
                'offset': offset
            }

            try:
                resp = self.session.get(f"{self.base_url}{endpoint}", params=params, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    records = data.get('data', [])
                    all_records.extend(records)
                    if len(records) < page_size:
                        break
                    offset += page_size
                    time.sleep(0.3)
                else:
                    break
            except Exception as e:
                logger.error(f"HAPI pagination error at offset {offset}: {e}", module='HDX')
                break

        return all_records
