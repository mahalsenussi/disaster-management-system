"""
Web search for the LRC chatbot.

Searches reliable humanitarian/web sources and returns formatted, citable,
sourced snippets. Used when the knowledge base has no strong match so the
chatbot can answer from live humanitarian data instead of dumping irrelevant
knowledge-base entries.

Sources (ordered by trust for humanitarian facts):
  1. HDX CKAN dataset catalog (humanitarian datasets, authoritative)
  2. DuckDuckGo HTML search (general reliable web, WHO/WB/UN/official pages)
  3. Wikipedia (encyclopedic background)
  4. News feeds via NewsCollector (GDELT, rate-limited; used only as last resort)
"""
import re
import html as html_lib
import requests
from typing import Dict, List, Optional
from urllib.parse import unquote

from evaluation_service.core.logger import get_logger
from evaluation_service.modules.hdx.ckan_client import CKANClient
from evaluation_service.modules.hdx.hapi_client import HAPIClient

logger = get_logger()

UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) LRC-DisasterMgmt/2.0 '
                    '(contact: info@lrc.org.ly)'}


class ChatbotWebSearch:
    """Searches humanitarian + reliable web sources for chatbot grounding."""

    SOURCE_ORDER = {'hapi_direct': 0, 'hapi_poc': 1, 'hdx': 2, 'web': 3, 'wiki': 4, 'news': 5}

    def __init__(self):
        self.ckan = CKANClient()

    # ------------------------------------------------------------------ utils
    def _build_query(self, message: str, categories: Optional[List[str]] = None) -> str:
        """Build a compact search query from the user message, with topic anchoring."""
        stopwords = {'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can',
                     'was', 'one', 'our', 'has', 'how', 'tell', 'what', 'about',
                     'does', 'there', 'this', 'that', 'with', 'from', 'have',
                     'some', 'do', 'me', 'would', 'could', 'should', 'will',
                     'any', 'just', 'your', 'its', 'been', 'they', 'them',
                     'their', 'these', 'those', 'were', 'said', 'whats', 'lets',
                     'let', 'check', 'see', 'want', 'available', 'avilable',
                     'doesnt', 'didnt', 'couldnt', 'shouldnt', 'neces', 'info',
                     'information', 'numbers', 'list', 'give', 'know', 'please',
                     'confirmed', 'registered', 'office', 'official', 'moh',
                     'may', 'might', 'many', 'how', 'would', 'could',
                     'made', 'making', 'contains'}
        corrections = {
            'refuges': 'refugees', 'refiges': 'refugees', 'refigees': 'refugees',
            'refugees': 'refugees', 'displced': 'displaced', 'displacemnt': 'displacement',
            'idps': 'idps', 'disasteres': 'disasters', 'fatalit': 'fatalities',
            'fatalities': 'fatalities', 'casulties': 'casualties', 'unhcr': 'unhcr',
            'covid19': 'covid', 'tubercolosis': 'tuberculosis', 'tuberculois': 'tuberculosis',
        }
        words = re.findall(r"[a-zA-Z]{3,}", message.lower())
        fixed = [corrections.get(w, w) for w in words]
        cities = {'tripoli', 'benghazi', 'misrata', 'misurata', 'derna', 'ejdabia',
                  'albayda', 'albaida', 'sabha', 'zawiya', 'zawia', 'zuwara',
                  'sirte', 'gharyan', 'kufra', 'gadames', 'ghat', 'surt',
                  'mizda', 'ubari', 'tarhuna', 'sabratha', 'zintan'}
        terms = []
        seen = set()
        for w in fixed:
            if w in stopwords or w in cities:
                continue
            if 'libya' in w and w != 'libya':
                continue
            if w not in seen:
                seen.add(w)
                terms.append(w)
        if not terms:
            terms = ['libya']

        anchors = {
            'food_security': 'food prices',
            'displacement': 'refugees',
            'conflict_security': 'conflict',
            'funding': 'funding appeal',
            'population': 'population',
            'health': 'health',
            'education': 'education',
            'infrastructure': 'infrastructure',
            'climate_data': 'drought',
            'humanitarian_needs': 'humanitarian needs',
        }
        if categories:
            for cat in categories:
                if cat in anchors:
                    terms.append(anchors[cat])
                    break

        if 'libya' not in terms and 'libya' not in message.lower():
            terms.append('libya')
        return " ".join(terms[:6])

    # ------------------------------------------------------------------ HDX
    def search_hdx(self, message: str, categories: Optional[List[str]] = None,
                   rows: int = 5) -> List[Dict]:
        """Search HDX CKAN dataset catalog (authoritative humanitarian data)."""
        q = self._build_query(message, categories=categories)
        
        # Add organization filters for key humanitarian data sources
        org_filters = {
            'displacement': 'organization:iom OR organization:unhcr',
            'food_security': 'organization:wfp OR organization:ipc',
            'conflict_security': 'organization:acled OR organization:ocha',
            'health': 'organization:who OR organization:unicef',
            'funding': 'organization:fts OR organization:ocha',
            'humanitarian_needs': 'organization:ocha OR organization:reuters',
        }
        
        fq = 'groups:lby'
        if categories:
            for cat in categories:
                if cat in org_filters:
                    fq += f' AND ({org_filters[cat]})'
                    break
        
        params = {
            'q': q,
            'fq': fq,
            'rows': rows,
            'sort': 'metadata_modified desc'
        }
        try:
            resp = self.ckan.session.get(
                "https://data.humdata.org/api/3/action/package_search",
                params=params, timeout=20
            )
            if resp.status_code != 200:
                logger.warning(f"HDX search error: {resp.status_code}", module='CHATBOT')
                return []
            results = resp.json().get('result', {}).get('results', [])
            out = []
            for d in results:
                org = (d.get('organization') or {}).get('title', 'Unknown')
                tags = [t.get('display_name') or t.get('name') for t in d.get('tags', [])]
                # Prioritize datasets with actual data resources
                resources = d.get('resources', [])
                has_data = any(r.get('datastore_active', False) for r in resources)
                has_csv = any(r.get('format', '').upper() == 'CSV' for r in resources)
                
                # Extract key numbers from description if available
                notes = d.get('notes', '')
                numbers = []
                import re
                number_patterns = re.findall(r'(\d+[,\d]*\s*(?:refugees|people|persons|displaced|IDPs))', notes, re.IGNORECASE)
                if number_patterns:
                    snippet = f"Key figures: {', '.join(number_patterns[:3])}. {notes[:200]}"
                else:
                    snippet = notes[:400]
                
                out.append({
                    'source_type': 'hdx',
                    'title': d.get('title', ''),
                    'snippet': snippet,
                    'organization': org,
                    'tags': tags[:8],
                    'url': f"https://data.humdata.org/dataset/{d.get('name', '')}",
                    'updated': d.get('metadata_modified', ''),
                    'has_data': has_data or has_csv,
                    'has_numbers': len(number_patterns) > 0
                })
            # Sort by data availability and numbers first
            out.sort(key=lambda x: (not x.get('has_numbers', False), not x.get('has_data', False)))
            logger.info(f"HDX search '{q}' -> {len(out)} results", module='CHATBOT')
            return out
        except Exception as e:
            logger.error(f"HDX websearch failed: {e}", module='CHATBOT')
            return []

    # --------------------------------------------------------------- refugee guard
    def _is_registered_poc_query(self, message: str) -> bool:
        """Detect when the user specifically asks about registered refugees / UNHCR registration."""
        q = message.lower()
        keywords = ["refugee", "registered", "unhcr", "registered", "sudan"]
        return any(kw in q for kw in keywords)

    # --------------------------------------------------------------- HAPI Direct Data
    def search_hapi_direct(self, message: str, categories: Optional[List[str]] = None,
                           rows: int = 3) -> List[Dict]:
        """Query HAPI endpoints directly for specific humanitarian data."""
        from evaluation_service.modules.hdx.hapi_client import HAPIClient, HAPI_THEMES
        from evaluation_service.modules.hdx.data_processor import DataProcessor
        c = HAPIClient()
        processor = DataProcessor()
        
        # Map categories to HAPI themes
        theme_map = {
            'displacement': ['idps', 'refugees'],
            'humanitarian_needs': 'humanitarian_needs',
            'operational_presence': 'operational_presence',
            'funding': 'funding',
            'conflict_security': 'conflict_events',
            'food_security': 'food_security',
            'population': 'population',
            'climate_data': 'rainfall',
        }
        
        out = []
        if categories:
            for cat in categories:
                themes = theme_map.get(cat, [])
                if isinstance(themes, str):
                    themes = [themes]
                
                for theme_key in themes:
                    try:
                        records = c.fetch_endpoint(theme_key, location_code='LBY', limit=rows)
                        if records:
                            # Process the records to extract actual data
                            entries = processor.process_hapi_theme(theme_key, records)
                            if entries:
                                # Use the first entry which should contain the summary data
                                summary_entry = entries[0]
                                out.append({
                                    'source_type': 'hapi_direct',
                                    'title': summary_entry.get('title', ''),
                                    'snippet': summary_entry.get('content', ''),
                                    'organization': summary_entry.get('source', 'HDX HAPI'),
                                    'url': summary_entry.get('source_url', ''),
                                    'updated': '',
                                    'theme': theme_key,
                                    'records_count': len(records),
                                    'has_data': True
                                })
                                break  # Only fetch one relevant theme per category
                    except Exception as e:
                        logger.warning(f"HAPI direct search for {theme_key} failed: {e}", module='CHATBOT')
        
        return out

    # --------------------------------------------------------------- HAPI PoC
    def search_hapi_poc(self, message: str, rows: int = 3) -> List[Dict]:
        """Query HAPI /affected-people/refugees-persons-of-concern for Libya + Sudan origin."""
        from evaluation_service.modules.hdx.hapi_client import HAPIClient
        c = HAPIClient()
        base = "https://hapi.humdata.org/api/v2"
        ep = base + "/affected-people/refugees-persons-of-concern"
        try:
            # Try to get all data for Libya first, then filter for Sudan origin
            r = c.session.get(
                ep,
                params={
                    "asylum_location_code": "LBY",
                    "limit": str(rows * 10),  # Get more records to filter
                    "output": "json",
                },
                timeout=45,
            )
            if r.status_code != 200:
                logger.warning(f"HAPI PoC query failed {r.status_code}", module='CHATBOT')
                return []
            data = r.json().get("data", [])
            
            # Filter for Sudan origin and get the most recent data
            sudan_data = [row for row in data if row.get("origin_location_code") == "SDN"]
            
            if not sudan_data:
                # If no Sudan data, return generic Libya refugee data
                recent_data = sorted(data, key=lambda x: x.get("reference_period_start", ""), reverse=True)[:rows]
                out = []
                for row in recent_data:
                    org = row.get("origin_location_name") or "Unknown"
                    pop = row.get("population") or 0
                    ref = row.get("reference_period_start") or ""
                    out.append(
                        {
                            "source_type": "hapi_poc",
                            "title": f"UNHCR Registered {org} Refugees in Libya {ref[:4] if ref else ''}",
                            "snippet": f"Population: {pop:,}",
                            "organization": "UNHCR / HAPI",
                            "url": f"https://data.humdata.org/dataset/refugees-persons-of-concern",
                            "updated": ref or "",
                        }
                    )
                return out
            
            # Sum latest reference-period population for Sudan-origin
            out = []
            for row in sudan_data[:rows]:
                org = row.get("origin_location_name") or "Unknown"
                pop = row.get("population") or 0
                ref = row.get("reference_period_start") or ""
                out.append(
                    {
                        "source_type": "hapi_poc",
                        "title": f"UNHCR Registered {org} Refugees in Libya {ref[:4] if ref else ''}",
                        "snippet": f"Population: {pop:,}",
                        "organization": "UNHCR / HAPI",
                        "url": f"https://data.humdata.org/dataset/refugees-persons-of-concern",
                        "updated": ref or "",
                    }
                )
            return out
        except Exception as e:
            logger.error(f"HAPI PoC query error: {e}", module='CHATBOT')
            return []

    # --------------------------------------------------------------- DuckDuckGo
    def search_web(self, message: str, categories: Optional[List[str]] = None,
                   rows: int = 5) -> List[Dict]:
        """General reliable web search via DuckDuckGo HTML (no API key)."""
        q = self._build_query(message, categories=categories)
        
        # For refugee queries, add specific terms to get better results
        if 'refugee' in message.lower() or 'sudan' in message.lower():
            q = f"libya refugees numbers statistics unhcr {q}"
        
        try:
            resp = requests.get(
                "https://html.duckduckgo.com/html/",
                params={'q': q}, headers=UA, timeout=20
            )
            if resp.status_code != 200:
                logger.warning(f"DDG search error: {resp.status_code}", module='CHATBOT')
                return []

            results = re.findall(
                r'<a rel="nofollow" class="result__a" href="([^"]+)">(.*?)</a>',
                resp.text
            )
            snips = re.findall(
                r'class="result__snippet"[^>]*>(.*?)</a>', resp.text, re.S
            )
            out = []
            for i, (href, title) in enumerate(results[:rows]):
                url = unquote(href.split('uddg=')[-1].split('&rut=')[0])
                snip = ''
                if i < len(snips):
                    snip = html_lib.unescape(re.sub(r'<[^>]+>', '', snips[i]))
                title_txt = html_lib.unescape(re.sub(r'<[^>]+>', '', title)).strip()
                
                # Extract numbers from snippets for refugee queries
                if 'refugee' in message.lower():
                    import re
                    numbers = re.findall(r'(\d+[,\d]*\s*(?:refugees|people|persons))', snip, re.IGNORECASE)
                    if numbers:
                        snip = f"Key figures: {', '.join(numbers[:2])}. {snip[:200]}"
                
                out.append({
                    'source_type': 'web',
                    'title': title_txt,
                    'snippet': snip[:300],
                    'organization': self._domain(url),
                    'url': url,
                    'updated': '',
                    'has_numbers': len(re.findall(r'\d+[,\d]*', snip)) > 0
                })
            
            # Sort results with numbers first
            out.sort(key=lambda x: not x.get('has_numbers', False))
            logger.info(f"DDG search '{q}' -> {len(out)} results", module='CHATBOT')
            return out
        except Exception as e:
            logger.error(f"DDG websearch failed: {e}", module='CHATBOT')
            return []

    @staticmethod
    def _domain(url: str) -> str:
        try:
            from urllib.parse import urlparse
            return (urlparse(url).netloc or 'web').replace('www.', '')
        except Exception:
            return 'web'

    # ----------------------------------------------------------------- Wikipedia
    def search_wikipedia(self, message: str, categories: Optional[List[str]] = None,
                         rows: int = 3) -> List[Dict]:
        """Wikipedia opensearch + summary (encyclopedic reliable background)."""
        q = self._build_query(message, categories=categories)
        try:
            resp = requests.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    'action': 'opensearch', 'search': q, 'limit': rows, 'format': 'json'
                },
                headers=UA, timeout=20
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            titles = data[1]
            urls = data[3]
            out = []
            for title, url in zip(titles[:rows], urls[:rows]):
                out.append({
                    'source_type': 'wiki',
                    'title': title,
                    'snippet': title,
                    'organization': 'Wikipedia',
                    'url': url,
                    'updated': ''
                })
            return out
        except Exception as e:
            logger.warning(f"Wikipedia search failed: {e}", module='CHATBOT')
            return []

    # ------------------------------------------------------------------- news
    def search_news(self, message: str, rows: int = 4) -> List[Dict]:
        """Live news feed search via NewsCollector GDELT (free, rate-limited)."""
        from evaluation_service.modules.news.collector import NewsCollector
        q = self._build_query(message)
        collector = NewsCollector()
        articles = []
        for m in collector._search_gdelt(q, max_articles=rows):
            articles.append({
                'source_type': 'news',
                'title': m.get('title', ''),
                'snippet': (m.get('description') or '')[:300],
                'organization': m.get('source', 'GDELT'),
                'url': m.get('url', ''),
                'updated': m.get('publishedAt', '')
            })
        return articles[:rows]

    # ------------------------------------------------------------------ master
    def search(self, message: str, categories: Optional[List[str]] = None,
               max_results: int = 7) -> List[Dict]:
        """Search all reliable sources, humanitarian data first. Deduped + ranked."""
        results = []
        seen = set()

        def _push(source_results):
            for r in source_results:
                key = (r.get('title') or '').lower().strip()
                if key and key not in seen:
                    seen.add(key)
                    results.append(r)

        # Priority 1: Direct HAPI data for specific categories
        _push(self.search_hapi_direct(message, categories, rows=3))
        
        # Priority 2: HDX CKAN search with organization filters
        _push(self.search_hdx(message, categories, rows=5))
        
        # Priority 3: General web search
        _push(self.search_web(message, categories, rows=5))
        
        # Priority 4: Wikipedia for background
        _push(self.search_wikipedia(message, categories, rows=2))
        
        # Priority 5: News as last resort
        _push(self.search_news(message, rows=3))

        # UNHCR registered persons-of-concern figure (number-bearing) when the
        # query is specifically about refugees/registered/UNHCR registration.
        if self._is_registered_poc_query(message):
            _push(self.search_hapi_poc(message, rows=3))

        results.sort(key=lambda x: self.SOURCE_ORDER.get(x['source_type'], 9))
        return results[:max_results]

    def format_results(self, results: List[Dict], max_items: int = 5) -> str:
        """Format web search results as a source list for the response."""
        if not results:
            return ""
        labels = {'hapi_direct': 'HDX HAPI live data',
                  'hapi_poc': 'HDX HAPI refugees data',
                  'hdx': 'HDX humanitarian dataset',
                  'web': 'web result',
                  'wiki': 'Wikipedia (background)',
                  'news': 'News'}
        parts = []
        
        # Separate HAPI direct results (which contain actual data) from others
        hapi_results = [r for r in results if r.get('source_type') == 'hapi_direct']
        other_results = [r for r in results if r.get('source_type') != 'hapi_direct']
        
        # Process HAPI results first - they contain actual data
        for r in hapi_results[:2]:
            src_label = labels.get(r['source_type'], 'source')
            org = r.get('organization', 'Unknown')
            snippet = r.get('snippet', '')
            
            # For HAPI direct data, the snippet is the actual data content
            parts.append(
                f"**{r.get('title', 'Untitled')}**"
                f" ({org} - {src_label})\n"
                f"{snippet}\n"
                f"Source: {r.get('url', '')}"
            )
        
        # Process other results as references
        for r in other_results[:max_items - len(hapi_results)]:
            src_label = labels.get(r['source_type'], 'source')
            org = r.get('organization', 'Unknown')
            snippet = r.get('snippet', '')[:350]
            
            # For HDX datasets, emphasize the data availability
            if r.get('source_type') == 'hdx' and r.get('has_data'):
                snippet = f"[Contains data] {snippet}"
            
            # For web results with numbers, emphasize them
            if r.get('source_type') == 'web' and r.get('has_numbers'):
                snippet = f"[Contains figures] {snippet}"
            
            parts.append(
                f"**{r.get('title', 'Untitled')}**"
                f" ({org} - {src_label})\n"
                f"{snippet}\n"
                f"Source: {r.get('url', '')}"
            )
        
        return "\n\n".join(parts)