"""
HDX Data Processor
Transforms raw HAPI and CKAN data into knowledge base entries
"""
import csv
import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from collections import Counter, defaultdict
from evaluation_service.core.logger import get_logger
from evaluation_service.modules.hdx.hapi_client import HAPI_THEMES

logger = get_logger()


class DataProcessor:
    """Processes HDX data into knowledge base entries"""

    def __init__(self):
        self.entries_created = 0
        self.entries_updated = 0

    def process_hapi_theme(self, theme_key: str, records: List[Dict]) -> List[Dict]:
        """Process HAPI records for a theme into knowledge entries"""
        if not records:
            return []

        theme_info = HAPI_THEMES.get(theme_key, {})
        category = theme_info.get('category', 'hdx_datasets')
        description = theme_info.get('description', theme_key)

        processors = {
            'idps': self._process_idps,
            'refugees': self._process_refugees,
            'humanitarian_needs': self._process_humanitarian_needs,
            'operational_presence': self._process_operational_presence,
            'funding': self._process_funding,
            'conflict_events': self._process_conflict_events,
            'national_risk': self._process_national_risk,
            'food_security': self._process_food_security,
            'food_prices': self._process_food_prices,
            'population': self._process_population,
            'rainfall': self._process_rainfall,
        }

        processor = processors.get(theme_key)
        if processor:
            return processor(records, category)

        return [self._build_generic_entry(theme_key, records, category, description)]

    def _process_refugees(self, records: List[Dict], category: str) -> List[Dict]:
        """Process refugees and persons of concern data"""
        entries = []

        # Group by origin country for refugees in Libya
        origin_data = defaultdict(lambda: {'total': 0, 'latest_ref': ''})

        for r in records:
            asylum = r.get('asylum_location_name') or ''
            origin = r.get('origin_location_name') or 'Unknown'
            pop = r.get('population', 0) or 0
            ref = r.get('reference_period_start') or ''

            # Only count refugees who are in Libya
            if 'Libya' in asylum or 'LBY' in asylum:
                origin_data[origin]['total'] += pop
                if ref and (not origin_data[origin]['latest_ref'] or ref > origin_data[origin]['latest_ref']):
                    origin_data[origin]['latest_ref'] = ref

        total_refugees = sum(d['total'] for d in origin_data.values())

        # Main summary entry
        breakdown = []
        for origin, data in sorted(origin_data.items(), key=lambda x: x[1]['total'], reverse=True):
            if data['total'] > 0:
                breakdown.append(f"  - {origin}: {data['total']:,}")

        content = f"Refugees and Persons of Concern in Libya: {total_refugees:,} total.\n\n"
        if breakdown:
            content += "By country of origin:\n" + "\n".join(breakdown[:10]) + "\n\n"
        content += "Source: UNHCR via HDX HAPI."

        entries.append({
            'category': category,
            'title': 'Libya - Refugees and Persons of Concern',
            'content': content,
            'source': 'UNHCR/HDX HAPI',
            'source_url': 'https://data.humdata.org/dataset/refugees-persons-of-concern',
            'tags': ['refugees', 'unhcr', 'displacement', 'population'],
            'priority': 9
        })

        # Specific entries for major origin countries
        for origin, data in list(origin_data.items())[:5]:
            if data['total'] > 0:
                entries.append({
                    'category': category,
                    'title': f'{origin} Refugees in Libya',
                    'content': f"Approximately {data['total']:,} refugees from {origin} in Libya.\nLatest reference period: {data['latest_ref']}\nSource: UNHCR via HDX HAPI.",
                    'source': 'UNHCR/HDX HAPI',
                    'tags': ['refugees', origin.lower(), 'libya', 'unhcr'],
                    'priority': 8
                })

        return entries

    def _process_idps(self, records: List[Dict], category: str) -> List[Dict]:
        """Process IDP data into knowledge entries"""
        entries = []

        # Find the most recent assessment round to avoid double-counting
        round_numbers = []
        for r in records:
            rnd = r.get('reporting_round')
            try:
                round_numbers.append(int(rnd))
            except (ValueError, TypeError):
                continue
        latest_round = max(round_numbers) if round_numbers else None

        # Filter to latest round only
        if latest_round is not None:
            latest_records = [r for r in records if str(r.get('reporting_round')) == str(latest_round)]
        else:
            latest_records = records

        # Aggregate by admin1
        admin1_data = defaultdict(lambda: {'total': 0, 'rounds': set()})
        for r in latest_records:
            admin1 = r.get('admin1_name') or 'Unknown'
            pop = r.get('population', 0) or 0
            admin1_data[admin1]['total'] += pop
            rnd = r.get('reporting_round', '')
            if rnd:
                admin1_data[admin1]['rounds'].add(str(rnd))

        total_idps = sum(d['total'] for d in admin1_data.values())

        breakdown = []
        for admin1, data in sorted(admin1_data.items(), key=lambda x: x[1]['total'], reverse=True):
            if data['total'] > 0:
                breakdown.append(f"  - {admin1}: {data['total']:,}")

        top_rounds = set()
        for d in admin1_data.values():
            top_rounds.update(d['rounds'])

        content = f"Internally Displaced Persons (IDPs) in Libya: {total_idps:,} total.\n\n"
        if breakdown:
            content += "Distribution by governorate:\n" + "\n".join(breakdown[:10]) + "\n\n"
        if latest_round:
            content += f"Latest assessment round: #{latest_round}\n"
        if top_rounds:
            content += f"Assessment rounds: {', '.join(sorted(top_rounds))}\n"

        content += "\nSource: IOM Displacement Tracking Matrix via HDX HAPI."

        entries.append({
            'category': category,
            'title': 'Libya - Internally Displaced Persons (IDPs)',
            'content': content,
            'source': 'IOM/HDX HAPI',
            'source_url': 'https://data.humdata.org/dataset/?q=libya+displacement',
            'tags': ['idps', 'displacement', 'iom', 'population'],
            'priority': 9
        })

        # Per-governorate entries for top 5
        for admin1, data in list(admin1_data.items())[:5]:
            if data['total'] > 0:
                entries.append({
                    'category': category,
                    'title': f'IDPs in {admin1}, Libya',
                    'content': f"Approximately {data['total']:,} internally displaced persons in {admin1}, Libya.\nLatest round: {latest_round}\nSource: IOM DTM via HDX HAPI.",
                    'source': 'IOM/HDX HAPI',
                    'tags': ['idps', (admin1 or 'unknown').lower(), 'displacement'],
                    'priority': 7
                })

        return entries

    def _process_humanitarian_needs(self, records: List[Dict], category: str) -> List[Dict]:
        """Process humanitarian needs data"""
        entries = []

        # Group by sector
        sector_data = defaultdict(lambda: {'total': 0, 'categories': defaultdict(int)})
        for r in records:
            sector = r.get('sector_name', 'Unknown')
            pop = r.get('population', 0) or 0
            cat = r.get('category', 'general')
            sector_data[sector]['total'] += pop
            sector_data[sector]['categories'][cat] += pop

        total_needs = sum(d['total'] for d in sector_data.values())

        breakdown = []
        for sector, data in sorted(sector_data.items(), key=lambda x: x[1]['total'], reverse=True):
            if data['total'] > 0:
                breakdown.append(f"  - {sector}: {data['total']:,} people")

        content = f"Humanitarian Needs in Libya: {total_needs:,} people in need across all sectors.\n\n"
        content += "Needs by sector:\n" + "\n".join(breakdown[:10]) + "\n\n"
        content += "Source: Humanitarian Needs Overview via HDX HAPI."

        entries.append({
            'category': category,
            'title': 'Libya - Humanitarian Needs Overview',
            'content': content,
            'source': 'OCHA/HDX HAPI',
            'source_url': 'https://data.humdata.org/dataset/?q=libya+humanitarian+needs',
            'tags': ['humanitarian', 'needs', 'assessment', 'population'],
            'priority': 9
        })

        return entries

    def _process_operational_presence(self, records: List[Dict], category: str) -> List[Dict]:
        """Process operational presence data"""
        entries = []

        orgs = set()
        sectors_by_org = defaultdict(set)
        sector_orgs = defaultdict(set)

        for r in records:
            org_name = r.get('org_name', '')
            sector = r.get('sector_name', '')
            if org_name:
                orgs.add(org_name)
                if sector:
                    sectors_by_org[org_name].add(sector)
                    sector_orgs[sector].add(org_name)

        content = f"Humanitarian Organizations Active in Libya: {len(orgs)} organizations.\n\n"

        content += "Key organizations:\n"
        for org in sorted(orgs)[:20]:
            sectors = sectors_by_org.get(org, set())
            sector_str = f" ({', '.join(sorted(sectors)[:3])})" if sectors else ""
            content += f"  - {org}{sector_str}\n"

        content += f"\nActive sectors: {', '.join(sorted(sector_orgs.keys())[:10])}\n"
        content += "\nSource: Humanitarian Operational Presence via HDX HAPI."

        entries.append({
            'category': category,
            'title': 'Humanitarian Organizations Active in Libya',
            'content': content,
            'source': 'OCHA/HDX HAPI',
            'source_url': 'https://data.humdata.org/dataset/?q=libya+operational+presence',
            'tags': ['organizations', 'humanitarian', 'coordination', '3w'],
            'priority': 8
        })

        # Sector-specific entries
        for sector, org_list in list(sector_orgs.items())[:5]:
            if len(org_list) >= 2:
                entries.append({
                    'category': category,
                    'title': f'Organizations in {sector} sector - Libya',
                    'content': f"{len(org_list)} organizations active in the {sector} sector in Libya:\n" +
                               "\n".join(f"  - {o}" for o in sorted(org_list)[:15]) +
                               f"\n\nSource: HDX HAPI.",
                    'source': 'OCHA/HDX HAPI',
                    'tags': [sector.lower(), 'organizations', 'libya'],
                    'priority': 6
                })

        return entries

    def _process_funding(self, records: List[Dict], category: str) -> List[Dict]:
        """Process funding data"""
        entries = []

        for r in records:
            appeal_name = r.get('appeal_name', '')
            appeal_type = r.get('appeal_type', '')
            requirements = r.get('requirements_usd', 0) or 0
            funding = r.get('funding_usd', 0) or 0
            pct = r.get('funding_pct', 0) or 0

            if requirements > 0:
                content = f"Humanitarian Funding for Libya ({appeal_type}):\n"
                content += f"  - Appeal: {appeal_name}\n"
                content += f"  - Requirements: ${requirements:,.0f}\n"
                content += f"  - Funded: ${funding:,.0f} ({pct:.1f}%)\n"
                content += f"  - Gap: ${requirements - funding:,.0f}\n\n"
                content += "Source: Financial Tracking Service via HDX HAPI."

                entries.append({
                    'category': category,
                    'title': f'Libya Funding - {appeal_name}',
                    'content': content,
                    'source': 'OCHA FTS/HDX HAPI',
                    'source_url': 'https://data.humdata.org/dataset/?q=libya+funding',
                    'tags': ['funding', 'appeals', 'fts', 'financial'],
                    'priority': 7
                })

        if not entries:
            entries.append({
                'category': category,
                'title': 'Libya - Humanitarian Funding Status',
                'content': 'Current humanitarian funding data for Libya is available via HDX HAPI. Check the latest appeals and funding status at https://data.humdata.org.',
                'source': 'OCHA FTS/HDX HAPI',
                'tags': ['funding', 'appeals'],
                'priority': 5
            })

        return entries

    def _process_conflict_events(self, records: List[Dict], category: str) -> List[Dict]:
        """Process conflict events data"""
        entries = []

        total_events = 0
        total_fatalities = 0
        type_counts = Counter()

        for r in records:
            events = r.get('events', 0) or 0
            fatalities = r.get('fatalities', 0) or 0
            event_type = r.get('event_type', 'Unknown')
            total_events += events
            total_fatalities += fatalities
            type_counts[event_type] += events

        content = f"Conflict Events in Libya:\n"
        content += f"  - Total events: {total_events:,}\n"
        content += f"  - Total fatalities: {total_fatalities:,}\n\n"

        if type_counts:
            content += "Events by type:\n"
            for etype, count in type_counts.most_common(10):
                content += f"  - {etype}: {count:,}\n"

        content += "\nSource: ACLED via HDX HAPI."

        entries.append({
            'category': category,
            'title': 'Libya - Conflict Events Summary',
            'content': content,
            'source': 'ACLED/HDX HAPI',
            'source_url': 'https://data.humdata.org/dataset/?q=libya+conflict',
            'tags': ['conflict', 'events', 'security', 'fatalities'],
            'priority': 9
        })

        return entries

    def _process_national_risk(self, records: List[Dict], category: str) -> List[Dict]:
        """Process national risk assessment data"""
        entries = []

        for r in records:
            risk_class = r.get('risk_class', '')
            global_rank = r.get('global_rank', '')
            overall = r.get('overall_risk', '')
            hazard = r.get('hazard_exposure_risk', '')
            vulnerability = r.get('vulnerability_risk', '')
            coping = r.get('coping_capacity_risk', '')

            content = f"National Risk Assessment for Libya:\n"
            content += f"  - Risk Class: {risk_class}\n"
            content += f"  - Global Rank: {global_rank}\n"
            content += f"  - Overall Risk Score: {overall}\n"
            content += f"  - Hazard Exposure Risk: {hazard}\n"
            content += f"  - Vulnerability Risk: {vulnerability}\n"
            content += f"  - Coping Capacity Risk: {coping}\n\n"
            content += "Source: INFORM via HDX HAPI."

            entries.append({
                'category': category,
                'title': 'Libya - National Risk Assessment (INFORM)',
                'content': content,
                'source': 'INFORM/HDX HAPI',
                'source_url': 'https://data.humdata.org/dataset/?q=libya+risk',
                'tags': ['risk', 'assessment', 'inform', 'hazards'],
                'priority': 8
            })
            break  # one entry per assessment

        return entries

    def _process_food_security(self, records: List[Dict], category: str) -> List[Dict]:
        """Process food security (IPC) data"""
        entries = []

        phase_data = defaultdict(int)
        for r in records:
            phase = r.get('ipc_phase', '')
            pop = r.get('population_in_phase', 0) or 0
            phase_data[f"Phase {phase}"] += pop

        total = sum(phase_data.values())
        content = f"Food Security Situation in Libya (IPC Classification):\n"
        content += f"  - Total assessed population: {total:,}\n\n"
        content += "Population by IPC phase:\n"
        for phase in sorted(phase_data.keys()):
            pop = phase_data[phase]
            pct = (pop / total * 100) if total > 0 else 0
            label = {
                'Phase 1': 'Minimal',
                'Phase 2': 'Stressed',
                'Phase 3': 'Crisis',
                'Phase 4': 'Emergency',
                'Phase 5': 'Famine'
            }.get(phase, '')
            content += f"  - {phase} ({label}): {pop:,} ({pct:.1f}%)\n"

        in_crisis = sum(v for k, v in phase_data.items() if k in ('Phase 3', 'Phase 4', 'Phase 5'))
        if in_crisis > 0:
            content += f"\n  ** {in_crisis:,} people in Crisis or worse (Phase 3+) **\n"

        content += "\nSource: IPC via HDX HAPI."

        entries.append({
            'category': category,
            'title': 'Libya - Food Security (IPC)',
            'content': content,
            'source': 'IPC/HDX HAPI',
            'source_url': 'https://data.humdata.org/dataset/?q=libya+food+security',
            'tags': ['food', 'security', 'ipc', 'nutrition', 'hunger'],
            'priority': 9
        })

        return entries

    def _process_food_prices(self, records: List[Dict], category: str) -> List[Dict]:
        """Process food prices data"""
        entries = []

        commodity_prices = defaultdict(list)
        markets = set()

        for r in records:
            commodity = r.get('commodity_name', '')
            price = r.get('price', 0) or 0
            market = r.get('market_name', '')
            currency = r.get('currency_code', 'LYD')

            if commodity and price > 0:
                commodity_prices[commodity].append(price)
            if market:
                markets.add(market)

        content = f"Food Prices in Libya Markets:\n"
        content += f"  - Markets monitored: {len(markets)}\n"
        content += f"  - Commodities tracked: {len(commodity_prices)}\n\n"
        content += "Average prices by commodity:\n"

        for commodity, prices in sorted(commodity_prices.items(), key=lambda x: len(x[1]), reverse=True)[:15]:
            avg = sum(prices) / len(prices)
            content += f"  - {commodity}: avg {avg:.2f} LYD (from {len(prices)} reports)\n"

        content += f"\nMarkets: {', '.join(sorted(markets)[:10])}\n"
        content += "\nSource: WFP Food Prices Database via HDX HAPI."

        entries.append({
            'category': category,
            'title': 'Libya - Food Prices and Market Data',
            'content': content,
            'source': 'WFP/HDX HAPI',
            'source_url': 'https://data.humdata.org/dataset/wfp-food-prices-for-libya',
            'tags': ['food', 'prices', 'markets', 'wfp', 'monitoring'],
            'priority': 8
        })

        return entries

    def _process_population(self, records: List[Dict], category: str) -> List[Dict]:
        """Process population data"""
        entries = []

        total_pop = 0
        gender_data = defaultdict(int)
        age_data = defaultdict(int)

        for r in records:
            pop = r.get('population', 0) or 0
            gender = r.get('gender', 'Unknown')
            age_range = r.get('age_range', 'Unknown')
            total_pop += pop
            gender_data[gender] += pop
            if age_range != 'Unknown':
                age_data[age_range] += pop

        content = f"Baseline Population of Libya: {total_pop:,}\n\n"
        content += "By gender:\n"
        for g, p in sorted(gender_data.items()):
            pct = (p / total_pop * 100) if total_pop > 0 else 0
            content += f"  - {g}: {p:,} ({pct:.1f}%)\n"

        if age_data:
            content += "\nBy age group:\n"
            for age in sorted(age_data.keys()):
                content += f"  - {age}: {age_data[age]:,}\n"

        content += "\nSource: WorldPop via HDX HAPI."

        entries.append({
            'category': category,
            'title': 'Libya - Population Demographics',
            'content': content,
            'source': 'WorldPop/HDX HAPI',
            'source_url': 'https://data.humdata.org/dataset/?q=libya+population',
            'tags': ['population', 'demographics', 'census'],
            'priority': 8
        })

        return entries

    def _process_rainfall(self, records: List[Dict], category: str) -> List[Dict]:
        """Process rainfall/climate data"""
        entries = []

        anomalies = []
        for r in records:
            anomaly = r.get('rainfall_anomaly_pct')
            rainfall = r.get('rainfall')
            lta = r.get('rainfall_long_term_average')
            period = r.get('aggregation_period', '')

            if anomaly is not None:
                anomalies.append({'anomaly': anomaly, 'rainfall': rainfall, 'lta': lta, 'period': period})

        if anomalies:
            avg_anomaly = sum(a['anomaly'] for a in anomalies) / len(anomalies)
            content = f"Rainfall Conditions in Libya:\n"
            content += f"  - Average anomaly: {avg_anomaly:.1f}% from long-term average\n"
            content += f"  - Data points: {len(anomalies)}\n\n"

            if avg_anomaly < -20:
                content += "  ** Below-normal rainfall indicates drought conditions **\n"
            elif avg_anomaly > 20:
                content += "  ** Above-normal rainfall may indicate flood risk **\n"
            else:
                content += "  Rainfall is near normal levels.\n"

            content += "\nSource: CHIRPS via HDX HAPI."

            entries.append({
                'category': category,
                'title': 'Libya - Rainfall and Climate Conditions',
                'content': content,
                'source': 'CHIRPS/HDX HAPI',
                'source_url': 'https://data.humdata.org/dataset/?q=libya+climate',
                'tags': ['rainfall', 'climate', 'drought', 'weather'],
                'priority': 7
            })

        return entries

    def _build_generic_entry(self, theme_key: str, records: List[Dict],
                             category: str, description: str) -> Dict:
        """Build a generic knowledge entry from any HAPI theme"""
        return {
            'category': category,
            'title': f'Libya - {description}',
            'content': f"{description} data available for Libya via HDX HAPI.\n{len(records)} records retrieved.\n\nSource: HDX HAPI.",
            'source': 'HDX HAPI',
            'tags': [theme_key, 'libya', 'hapi'],
            'priority': 5
        }

    def process_csv_dataset(self, dataset_summary: Dict, csv_path: str,
                            max_rows: int = 5000) -> List[Dict]:
        """Process a downloaded CSV dataset into knowledge entries"""
        entries = []
        title = dataset_summary.get('title', 'Unknown Dataset')
        org = dataset_summary.get('organization', 'Unknown')
        hdx_link = dataset_summary.get('hdx_link', '')

        try:
            with open(csv_path, 'r', encoding='utf-8', errors='replace') as f:
                reader = csv.DictReader(f)
                rows = []
                for i, row in enumerate(reader):
                    if i >= max_rows:
                        break
                    rows.append(row)

            if not rows:
                return []

            # Compute basic statistics
            content = f"Dataset: {title}\nOrganization: {org}\nRecords analyzed: {len(rows)}\n\n"

            # Analyze numeric columns
            columns = list(rows[0].keys())
            numeric_cols = []
            for col in columns:
                try:
                    vals = [float(r.get(col, 0) or 0) for r in rows[:100]]
                    if any(v != 0 for v in vals):
                        numeric_cols.append(col)
                except (ValueError, TypeError):
                    pass

            if numeric_cols:
                content += "Key statistics:\n"
                for col in numeric_cols[:8]:
                    try:
                        vals = [float(r.get(col, 0) or 0) for r in rows]
                        total = sum(vals)
                        avg = total / len(vals) if vals else 0
                        max_val = max(vals)
                        min_val = min(vals)
                        content += f"  - {col}: total={total:,.1f}, avg={avg:,.1f}, min={min_val:,.1f}, max={max_val:,.1f}\n"
                    except (ValueError, TypeError):
                        pass

            # Analyze categorical columns
            cat_cols = [c for c in columns if c not in numeric_cols]
            if cat_cols:
                content += "\nCategories:\n"
                for col in cat_cols[:5]:
                    values = Counter(str(r.get(col, '')) for r in rows if r.get(col))
                    if 0 < len(values) <= 20:
                        top = values.most_common(5)
                        content += f"  - {col}: {', '.join(f'{v}({c})' for v, c in top)}\n"

            content += f"\nSource: {org} via HDX."

            categories = dataset_summary.get('_kb_categories', ['hdx_datasets'])

            entries.append({
                'category': categories[0] if categories else 'hdx_datasets',
                'title': f'{title} - Data Summary',
                'content': content,
                'source': org,
                'source_url': hdx_link,
                'tags': dataset_summary.get('tags', [])[:10] + ['data', 'statistics'],
                'priority': 6
            })

        except Exception as e:
            logger.error(f"Error processing CSV {csv_path}: {e}", module='HDX')

        return entries

    def build_dataset_metadata_entry(self, dataset_summary: Dict) -> Dict:
        """Create a knowledge entry describing an HDX dataset"""
        title = dataset_summary.get('title', 'Unknown')
        org = dataset_summary.get('organization', 'Unknown')
        notes = dataset_summary.get('notes', '')[:500]
        tags = dataset_summary.get('tags', [])
        num_resources = dataset_summary.get('num_resources', 0)
        modified = dataset_summary.get('metadata_modified', '')
        hdx_link = dataset_summary.get('hdx_link', '')
        resources = dataset_summary.get('resources', [])

        content = f"HDX Dataset: {title}\n"
        content += f"Organization: {org}\n"
        content += f"Last Updated: {modified}\n"
        content += f"Resources: {num_resources}\n\n"

        if notes:
            content += f"Description: {notes}\n\n"

        if resources:
            content += "Available files:\n"
            for r in resources[:5]:
                content += f"  - {r.get('name', 'Unnamed')} ({r.get('format', 'N/A')})"

        content += f"\n\nURL: {hdx_link}"

        categories = dataset_summary.get('_kb_categories', ['hdx_datasets'])

        # Increase priority for key humanitarian datasets with actual data
        key_orgs = ['wfp', 'iom', 'ocha', 'unhcr', 'who', 'unicef', 'ifrc', 'icrc', 'acled', 'ipc']
        priority = 6 if any(key in org.lower() for key in key_orgs) else 3

        return {
            'category': categories[0] if categories else 'hdx_datasets',
            'title': f'HDX: {title}',
            'content': content,
            'source': org,
            'source_url': hdx_link,
            'tags': tags[:10] + ['hdx', 'dataset'],
            'priority': priority
        }

    def get_stats(self) -> Dict:
        """Get processing statistics"""
        return {
            'entries_created': self.entries_created,
            'entries_updated': self.entries_updated
        }
