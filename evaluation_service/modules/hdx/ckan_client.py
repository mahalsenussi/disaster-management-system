"""
HDXX CKAN Metadata API Client
Searches datasets, discovers resources, and downloads files from HDX
"""
import os
import time
import requests
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from evaluation_service.core.logger import get_logger

logger = get_logger()

HDX_CKAN_BASE = "https://data.humdata.org/api/3/action"
HDX_DOWNLOAD_BASE = "https://data.humdata.org"


class CKANClient:
    """Client for HDX CKAN metadata API"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'LRC-DisasterMgmt/2.0'})

    def search_datasets(self, groups: str = 'lby', rows: int = 200,
                        start: int = 0, sort: str = 'metadata_modified desc',
                        extras: Optional[Dict] = None) -> List[Dict]:
        """Search HDX datasets by country (ISO3 group code)"""
        params = {
            'fq': f'groups:{groups}',
            'rows': rows,
            'start': start,
            'sort': sort
        }

        try:
            resp = self.session.get(
                f"{HDX_CKAN_BASE}/package_search",
                params=params,
                timeout=30
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    results = data.get('result', {})
                    datasets = results.get('results', [])
                    total = results.get('count', 0)
                    logger.info(f"CKAN: found {total} datasets for groups={groups}, returned {len(datasets)}", module='HDX')
                    return datasets
            logger.error(f"CKAN search error: {resp.status_code}", module='HDX')
        except Exception as e:
            logger.error(f"CKAN search exception: {e}", module='HDX')

        return []

    def search_all_datasets(self, groups: str = 'lby') -> List[Dict]:
        """Fetch all datasets for Libya (single large request with fallback pagination)"""
        # Try a single large request first to avoid unstable ordering across pages
        datasets = self.search_datasets(groups=groups, rows=500, start=0)
        if datasets:
            return datasets

        # Fallback: paginated fetch (CKAN max rows may be limited on some configs)
        all_datasets = []
        page_size = 100
        start = 0

        while True:
            datasets = self.search_datasets(groups=groups, rows=page_size, start=start)
            if not datasets:
                break
            all_datasets.extend(datasets)
            if len(datasets) < page_size:
                break
            start += page_size
            time.sleep(0.5)

        return all_datasets

    def get_dataset(self, dataset_id: str) -> Optional[Dict]:
        """Get full dataset metadata by ID or name"""
        try:
            resp = self.session.get(
                f"{HDX_CKAN_BASE}/package_show",
                params={'id': dataset_id},
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    return data.get('result')
        except Exception as e:
            logger.error(f"CKAN get_dataset error for {dataset_id}: {e}", module='HDX')

        return None

    def get_dataset_resources(self, dataset_id: str) -> List[Dict]:
        """Get all resources (files) for a dataset"""
        dataset = self.get_dataset(dataset_id)
        if dataset:
            return dataset.get('resources', [])
        return []

    def find_downloadable_resources(self, dataset_id: str) -> List[Dict]:
        """Find CSV/JSON/XLSX resources that can be downloaded"""
        resources = self.get_dataset_resources(dataset_id)
        downloadable = []
        for r in resources:
            fmt = (r.get('format') or '').upper()
            if fmt in ('CSV', 'JSON', 'XLSX', 'XLS'):
                downloadable.append({
                    'id': r.get('id'),
                    'name': r.get('name'),
                    'format': fmt,
                    'url': r.get('url'),
                    'size': r.get('size'),
                    'last_modified': r.get('last_modified'),
                    'datastore_active': r.get('datastore_active', False)
                })
        return downloadable

    def search_tabular_resources(self, groups: str = 'lby') -> List[Dict]:
        """Find all resources with datastore_active=true (available via Tabular Data API)"""
        params = {
            'fq': f'groups:{groups}+res_extras_datastore_active:true',
            'rows': 100,
            'sort': 'metadata_modified desc'
        }

        try:
            resp = self.session.get(
                f"{HDX_CKAN_BASE}/package_search",
                params=params,
                timeout=30
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    results = data.get('result', {})
                    return results.get('results', [])
        except Exception as e:
            logger.error(f"CKAN tabular search error: {e}", module='HDX')

        return []

    def download_resource(self, url: str, dest_path: str) -> Tuple[bool, str]:
        """Download a resource file from HDX"""
        try:
            resp = self.session.get(url, timeout=120, stream=True)
            if resp.status_code == 200:
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                with open(dest_path, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                size_mb = os.path.getsize(dest_path) / (1024 * 1024)
                logger.info(f"Downloaded {size_mb:.1f}MB to {dest_path}", module='HDX')
                return True, dest_path
            else:
                logger.error(f"Download failed ({resp.status_code}): {url}", module='HDX')
                return False, f"HTTP {resp.status_code}"
        except Exception as e:
            logger.error(f"Download error: {e}", module='HDX')
            return False, str(e)

    def extract_dataset_summary(self, dataset: Dict) -> Dict:
        """Extract key metadata from a CKAN dataset"""
        return {
            'id': dataset.get('id'),
            'name': dataset.get('name'),
            'title': dataset.get('title'),
            'notes': dataset.get('notes', ''),
            'organization': (dataset.get('organization') or {}).get('title', 'Unknown'),
            'org_name': (dataset.get('organization') or {}).get('name', ''),
            'metadata_created': dataset.get('metadata_created'),
            'metadata_modified': dataset.get('metadata_modified'),
            'num_resources': dataset.get('num_resources', 0),
            'tags': [t.get('display_name') or t.get('name') for t in dataset.get('tags', [])],
            'groups': [g.get('display_name') or g.get('name') for g in dataset.get('groups', [])],
            'resources': [
                {
                    'id': r.get('id'),
                    'name': r.get('name'),
                    'format': r.get('format'),
                    'url': r.get('url'),
                    'datastore_active': r.get('datastore_active', False)
                }
                for r in dataset.get('resources', [])
            ],
            'hdx_link': f"https://data.humdata.org/dataset/{dataset.get('name', '')}"
        }

    def get_dataset_categories_from_tags(self, tags: List[str]) -> List[str]:
        """Map HDX tags to knowledge base categories"""
        tag_to_category = {
            'displacement': 'displacement',
            'idp': 'displacement',
            'refugees': 'displacement',
            'migration': 'displacement',
            'health': 'health',
            'health facilities': 'health',
            'disease': 'health',
            'nutrition': 'health',
            'food security': 'food_security',
            'food prices': 'food_security',
            'markets': 'food_security',
            'education': 'education',
            'education facilities': 'education',
            'conflict': 'conflict_security',
            'violence': 'conflict_security',
            'hazards and risk': 'conflict_security',
            'natural disasters': 'conflict_security',
            'population': 'population',
            'demographics': 'population',
            'baseline population': 'population',
            'climate': 'climate_data',
            'climate-weather': 'climate_data',
            'drought': 'climate_data',
            'flooding': 'climate_data',
            'transportation': 'infrastructure',
            'roads': 'infrastructure',
            'facilities-infrastructure': 'infrastructure',
            'water sanitation and hygiene-wash': 'infrastructure',
            'geodata': 'geodata',
            'administrative boundaries-divisions': 'geodata',
            'indicators': 'hdx_datasets',
            'development': 'hdx_datasets',
            'socioeconomics': 'hdx_datasets',
        }

        categories = set()
        for tag in tags:
            tag_lower = tag.lower()
            if tag_lower in tag_to_category:
                categories.add(tag_to_category[tag_lower])

        return list(categories) if categories else ['hdx_datasets']
