"""
HDX Collector Orchestrator
Coordinates HAPI, CKAN, and CSV data collection into the knowledge base
"""
import os
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from evaluation_service.core.logger import get_logger
from evaluation_service.modules.hdx.hapi_client import HAPIClient, HAPI_THEMES
from evaluation_service.modules.hdx.ckan_client import CKANClient
from evaluation_service.modules.hdx.data_processor import DataProcessor

logger = get_logger()

# High-priority datasets to download CSVs for
KEY_DOWNLOAD_DATASETS = [
    'wfp-food-prices-for-libya',
    'lby-iom-dtm-from-api',
    'cod-ab-lby',
    'world-bank-education-indicators-for-libya',
    'libya-main-towns-neighborhoods',
    'acmad-standardized-precipitation-index',
]

# Temp directory for downloaded files
DOWNLOAD_DIR = '/tmp/hdx_downloads'


class HDXCollector:
    """Orchestrates HDX data collection for the knowledge base"""

    def __init__(self, download_dir: str = DOWNLOAD_DIR):
        self.hapi = HAPIClient()
        self.ckan = CKANClient()
        self.processor = DataProcessor()
        self.download_dir = download_dir
        self.stats = {
            'hapi_entries': 0,
            'ckan_entries': 0,
            'csv_entries': 0,
            'datasets_discovered': 0,
            'errors': 0,
            'started_at': None,
            'completed_at': None
        }

    def collect_all(self) -> Dict:
        """Main entry point: run full HDX collection"""
        self.stats['started_at'] = datetime.now().isoformat()
        logger.info("Starting HDX data collection", module='HDX')

        try:
            # Phase 1: HAPI standardized data
            hapi_entries = self.collect_hapi_data()
            self.stats['hapi_entries'] = len(hapi_entries)

            # Phase 2: CKAN dataset discovery
            ckan_entries = self.discover_and_summarize_datasets()
            self.stats['ckan_entries'] = len(ckan_entries)

            # Phase 3: Key CSV downloads
            csv_entries = self.download_key_datasets()
            self.stats['csv_entries'] = len(csv_entries)

            all_entries = hapi_entries + ckan_entries + csv_entries
            self.stats['completed_at'] = datetime.now().isoformat()

            logger.info(
                f"HDX collection complete: {len(all_entries)} entries "
                f"(HAPI: {self.stats['hapi_entries']}, "
                f"CKAN: {self.stats['ckan_entries']}, "
                f"CSV: {self.stats['csv_entries']})",
                module='HDX'
            )

            return all_entries

        except Exception as e:
            logger.error(f"HDX collection failed: {e}", module='HDX')
            self.stats['errors'] += 1
            self.stats['completed_at'] = datetime.now().isoformat()
            return []

    def collect_and_save(self, kb_repository) -> Dict:
        """Collect HDX data and save to knowledge base"""
        entries = self.collect_all()

        saved = 0
        updated = 0
        errors = 0

        for entry in entries:
            try:
                entry_id = kb_repository.upsert_entry(
                    category=entry['category'],
                    title=entry['title'],
                    content=entry['content'],
                    source=entry['source'],
                    source_url=entry.get('source_url'),
                    tags=entry.get('tags'),
                    priority=entry.get('priority', 5)
                )
                if entry_id:
                    # Check if it was new or updated
                    existing = kb_repository.get_entry(entry_id)
                    if existing and existing.get('updated_at') != existing.get('created_at'):
                        updated += 1
                    else:
                        saved += 1
            except Exception as e:
                logger.error(f"Failed to save entry '{entry.get('title', '?')}': {e}", module='HDX')
                errors += 1

        result = {
            'entries_total': len(entries),
            'entries_saved': saved,
            'entries_updated': updated,
            'errors': errors,
            'hapi_entries': self.stats['hapi_entries'],
            'ckan_entries': self.stats['ckan_entries'],
            'csv_entries': self.stats['csv_entries'],
            'datasets_discovered': self.stats['datasets_discovered'],
            'completed_at': self.stats['completed_at']
        }

        logger.info(f"HDX collection saved: {result}", module='HDX')
        return result

    def collect_hapi_data(self) -> List[Dict]:
        """Phase 1: Fetch standardized data from HAPI"""
        logger.info("Phase 1: Collecting HAPI data", module='HDX')
        all_entries = []

        for theme_key, theme_info in HAPI_THEMES.items():
            try:
                records = self.hapi.fetch_endpoint(theme_key)
                if records:
                    entries = self.processor.process_hapi_theme(theme_key, records)
                    all_entries.extend(entries)
                    logger.info(f"  {theme_key}: {len(entries)} entries from {len(records)} records", module='HDX')
                else:
                    logger.info(f"  {theme_key}: no data available", module='HDX')

                time.sleep(0.5)  # polite delay

            except Exception as e:
                logger.error(f"  {theme_key} failed: {e}", module='HDX')
                self.stats['errors'] += 1

        return all_entries

    def discover_and_summarize_datasets(self) -> List[Dict]:
        """Phase 2: Discover all Libya datasets via CKAN"""
        logger.info("Phase 2: Discovering HDX datasets via CKAN", module='HDX')
        all_entries = []

        try:
            datasets = self.ckan.search_all_datasets(groups='lby')
            self.stats['datasets_discovered'] = len(datasets)

            for dataset in datasets:
                try:
                    summary = self.ckan.extract_dataset_summary(dataset)

                    # Map tags to KB categories
                    categories = self.ckan.get_dataset_categories_from_tags(summary.get('tags', []))
                    summary['_kb_categories'] = categories

                    entry = self.processor.build_dataset_metadata_entry(summary)
                    all_entries.append(entry)

                except Exception as e:
                    logger.error(f"  Failed to process dataset {dataset.get('name', '?')}: {e}", module='HDX')
                    self.stats['errors'] += 1

            logger.info(f"  Discovered {len(datasets)} datasets, created {len(all_entries)} entries", module='HDX')

        except Exception as e:
            logger.error(f"  CKAN discovery failed: {e}", module='HDX')
            self.stats['errors'] += 1

        return all_entries

    def download_key_datasets(self) -> List[Dict]:
        """Phase 3: Download and process key CSV datasets"""
        logger.info("Phase 3: Downloading key datasets", module='HDX')
        all_entries = []

        os.makedirs(self.download_dir, exist_ok=True)

        for dataset_name in KEY_DOWNLOAD_DATASETS:
            try:
                resources = self.ckan.find_downloadable_resources(dataset_name)
                if not resources:
                    logger.info(f"  {dataset_name}: no downloadable resources", module='HDX')
                    continue

                # Get dataset metadata for summary
                dataset_meta = self.ckan.get_dataset(dataset_name)
                if not dataset_meta:
                    continue

                summary = self.ckan.extract_dataset_summary(dataset_meta)
                categories = self.ckan.get_dataset_categories_from_tags(summary.get('tags', []))
                summary['_kb_categories'] = categories

                # Download first CSV resource
                for resource in resources:
                    if resource['format'] == 'CSV':
                        dest_path = os.path.join(self.download_dir, f"{dataset_name}.csv")
                        success, result = self.ckan.download_resource(resource['url'], dest_path)

                        if success:
                            entries = self.processor.process_csv_dataset(summary, dest_path)
                            all_entries.extend(entries)
                            logger.info(f"  {dataset_name}: {len(entries)} entries from CSV", module='HDX')
                        else:
                            logger.warning(f"  {dataset_name}: download failed - {result}", module='HDX')

                        break

                time.sleep(1)  # polite delay between downloads

            except Exception as e:
                logger.error(f"  {dataset_name} failed: {e}", module='HDX')
                self.stats['errors'] += 1

        return all_entries

    def get_status(self, kb_repository) -> Dict:
        """Get collection status and KB statistics"""
        stats = kb_repository.get_entries_count_by_category()

        return {
            'categories': stats,
            'total_entries': sum(s.get('count', 0) for s in stats.values()),
            'hdx_categories': {
                cat: stats.get(cat, {}).get('count', 0)
                for cat in [
                    'displacement', 'humanitarian_needs', 'conflict_security',
                    'operational_presence', 'funding', 'food_security',
                    'population', 'climate_data', 'health', 'education',
                    'infrastructure', 'geodata', 'hdx_datasets'
                ]
            },
            'last_collection': self._get_last_collection_time(kb_repository)
        }

    def _get_last_collection_time(self, kb_repository) -> Optional[str]:
        """Get the last HDX collection timestamp"""
        try:
            result = kb_repository.execute_query(
                """SELECT updated_at FROM knowledge_entries
                   WHERE source LIKE '%HDX%' OR source LIKE '%HAPI%'
                   ORDER BY updated_at DESC LIMIT 1"""
            )
            if result:
                return result[0].get('updated_at')
        except Exception:
            pass
        return None
