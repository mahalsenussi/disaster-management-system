"""
News data collector from NewsAPI, GNews, and WorldNewsAPI
"""
import os
import requests
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from evaluation_service.core.logger import get_logger
from evaluation_service.modules.news.service import NewsService

logger = get_logger()

# News Categories for Libya and surrounding areas
NEWS_CATEGORIES = {
    "comprehensive": {
        "description": "Comprehensive Libyan news overview",
        "newsapi_terms": ["Libya", "Tripoli", "Benghazi", "Misrata", "Libya government", "Libya news"],
        "gnews_terms": ["Libya news", "Tripoli Libya", "Benghazi Libya", "ليبيا الأخبار"],
        "priority": "HIGH"
    },
    "libya-danger-assessment": {
        "description": "Libya danger assessment with AI evaluation",
        "newsapi_terms": ["Libya", "Tripoli", "Benghazi", "Misrata", "Libya conflict", "Libya government", "danger", "emergency", "crisis"],
        "gnews_terms": ["Libya news", "Tripoli Libya", "Benghazi Libya", "ليبيا الأخبار", "danger", "emergency"],
        "priority": "CRITICAL"
    },
    "libya_cities": {
        "description": "News from Libyan cities",
        "newsapi_terms": ["Libya", "Tripoli", "Benghazi", "Misrata", "Libya conflict", "Libya government"],
        "gnews_terms": ["Tripoli Libya", "Benghazi Libya", "Misrata Libya", "Libya news", "طرابلس ليبيا"],
        "priority": "HIGH"
    },
    "humanitarian": {
        "description": "Humanitarian crises and relief efforts",
        "newsapi_terms": ["humanitarian", "refugees", "UNHCR", "ICRC", "Red Cross", "aid relief", "humanitarian crisis"],
        "gnews_terms": ["humanitarian crisis", "refugees", "UNHCR", "ICRC", "Red Cross", "aid relief"],
        "priority": "CRITICAL"
    },
    "disasters": {
        "description": "Natural disasters and emergencies",
        "newsapi_terms": ["earthquake", "flood", "wildfire", "hurricane", "disaster", "emergency", "natural disaster"],
        "gnews_terms": ["earthquake", "flood", "storm", "fire", "drought", "disaster", "emergency", "catastrophe"],
        "priority": "CRITICAL"
    },
    "mediterranean": {
        "description": "Mediterranean region news",
        "newsapi_terms": ["Mediterranean", "Italy", "Malta", "Greece", "Turkey", "Egypt", "Mediterranean migration"],
        "gnews_terms": ["Mediterranean", "Italy", "Malta", "Greece", "Turkey", "Egypt migration"],
        "priority": "HIGH"
    },
    "north_africa": {
        "description": "North Africa regional developments",
        "newsapi_terms": ["North Africa", "Tunisia", "Algeria", "Morocco", "Egypt", "Libya", "Maghreb"],
        "gnews_terms": ["North Africa", "Maghreb", "Tunisia", "Algeria", "Morocco", "Egypt", "Sahara"],
        "priority": "HIGH"
    },
    "lrc_operations": {
        "description": "Libyan Red Crescent operations",
        "newsapi_terms": ["Libyan Red Crescent", "LRC", "Red Crescent Libya", "Libya emergency response"],
        "gnews_terms": ["Libyan Red Crescent", "LRC", "الهلال الأحمر الليبي", "volunteers", "emergency response"],
        "priority": "CRITICAL"
    }
}

class NewsCollector:
    """Collects news data from NewsAPI, GNews, and WorldNewsAPI"""
    
    def __init__(self):
        self.service = NewsService()
        self.newsapi_key = os.environ.get('NEWSAPI_KEY')
        self.gnews_key = os.environ.get('GNEWS_API_KEY')
        self.worldnews_key = os.environ.get('WORLDNEWS_API_KEY')
        self.currents_key = os.environ.get('CURRENTS_API_KEY')
        
        self.newsapi_base = "https://newsapi.org/v2"
        self.gnews_base = "https://gnews.io/api/v4"
        self.worldnews_base = "https://api.worldnewsapi.com"
        self.currents_base = "https://api.currentsapi.services/v1"
        
        if not (self.newsapi_key or self.gnews_key or self.worldnews_key or self.currents_key):
            logger.warning("No News API keys set, using mock data", module='NEWS_COLLECTOR')
    
    def collect_news(self, category: str = "comprehensive") -> tuple[bool, str, Optional[Dict]]:
        """Collect news data for a category
        
        Returns:
            (success, message, news_data)
        """
        has_keys = bool(self.newsapi_key or self.gnews_key or self.worldnews_key or self.currents_key)
        
        if not has_keys:
            logger.warning("Using mock data for news collection (no API keys configured)", module='NEWS_COLLECTOR')
            return False, "News API keys not configured. Cannot collect real news data.", self._get_mock_data(category)[2]
        
        try:
            return self._collect_from_apis(category)
        except Exception as e:
            logger.error(f"Failed to collect news: {e}", module='NEWS_COLLECTOR', exc_info=True)
            return False, f"Failed to collect news: {e}", self._get_mock_data(category)[2]
    
    def _collect_from_apis(self, category: str) -> tuple[bool, str, Dict]:
        """Collect news from NewsAPI, GNews, WorldNewsAPI, Currents API, and GDELT"""
        category_info = NEWS_CATEGORIES.get(category, NEWS_CATEGORIES["comprehensive"])
        all_articles = []
        sources_used = []
        
        logger.info(f"Collecting news for {category_info['description']}", module='NEWS_COLLECTOR')
        
        # Try NewsAPI first (primary)
        if self.newsapi_key:
            newsapi_terms = category_info.get('newsapi_terms', [])
            newsapi_count = 0
            for term in newsapi_terms[:2]:
                articles = self._search_newsapi(term, max_articles=5)
                if articles:
                    all_articles.extend(articles)
                    newsapi_count += len(articles)
            if newsapi_count > 0:
                sources_used.append('NewsAPI.org')
                logger.info(f"NewsAPI contributed {newsapi_count} articles", module='NEWS_COLLECTOR')
        
        # Try GNews second (backup)
        if self.gnews_key:
            gnews_terms = category_info.get('gnews_terms', [])
            gnews_count = 0
            for term in gnews_terms[:2]:
                articles = self._search_gnews(term, max_articles=5)
                if articles:
                    all_articles.extend(articles)
                    gnews_count += len(articles)
            if gnews_count > 0:
                sources_used.append('GNews')
                logger.info(f"GNews contributed {gnews_count} articles", module='NEWS_COLLECTOR')
        
        # Try WorldNewsAPI (additional source)
        if self.worldnews_key:
            worldnews_terms = category_info.get('newsapi_terms', [])
            worldnews_count = 0
            for term in worldnews_terms[:2]:
                articles = self._search_worldnewsapi(term, max_articles=5)
                if articles:
                    all_articles.extend(articles)
                    worldnews_count += len(articles)
            if worldnews_count > 0:
                sources_used.append('WorldNewsAPI')
                logger.info(f"WorldNewsAPI contributed {worldnews_count} articles", module='NEWS_COLLECTOR')
        
        # Try Currents API (additional source)
        if self.currents_key:
            currents_terms = category_info.get('newsapi_terms', [])
            currents_count = 0
            for term in currents_terms[:2]:
                articles = self._search_currents(term, max_articles=5)
                if articles:
                    all_articles.extend(articles)
                    currents_count += len(articles)
            if currents_count > 0:
                sources_used.append('Currents API')
                logger.info(f"Currents API contributed {currents_count} articles", module='NEWS_COLLECTOR')
        
        # Try GDELT (optional additional source)
        gdelt_terms = category_info.get('newsapi_terms', [])
        gdelt_count = 0
        for term in gdelt_terms[:2]:
            articles = self._search_gdelt(term, max_articles=5)
            if articles:
                all_articles.extend(articles)
                gdelt_count += len(articles)
        if gdelt_count > 0:
            sources_used.append('GDELT')
            logger.info(f"GDELT contributed {gdelt_count} articles", module='NEWS_COLLECTOR')
        
        # If no articles from any API, use mock data
        if len(all_articles) == 0:
            logger.warning("No articles from any API, using mock data", module='NEWS_COLLECTOR')
            return False, "No articles retrieved from any API", self._get_mock_data(category)[2]
        
        # Remove duplicates based on (title + domain) to handle same title across sources
        seen_combinations = set()
        unique_articles = []
        for article in all_articles:
            title = article.get('title', '').lower().strip()
            source = article.get('source', '')
            # Handle case where source might be a dict (from some APIs)
            if isinstance(source, dict):
                domain = source.get('name', str(source)).lower().strip()
            else:
                domain = str(source).lower().strip()
            combination = f"{title}|{domain}"
            if title and combination not in seen_combinations:
                seen_combinations.add(combination)
                unique_articles.append(article)
        
        # Sort by publication date (newest first)
        unique_articles.sort(key=lambda x: x.get('publishedAt', ''), reverse=True)
        
        news_data = {
            'category': category,
            'description': category_info['description'],
            'articles': unique_articles[:15],
            'total_articles': len(unique_articles),
            'sources_used': sources_used if sources_used else ['Mock Data'],
            'last_updated': datetime.now().isoformat(),
            'priority': category_info.get('priority', 'MEDIUM')
        }
        
        logger.collector_run('news', f"Collected {len(unique_articles)} articles for {category}", f"Sources: {news_data['sources_used']}")
        
        return True, "News data collected successfully", news_data
    
    def _search_newsapi(self, query: str, max_articles: int = 10) -> List[Dict]:
        """Search NewsAPI.org for articles"""
        try:
            from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            to_date = datetime.now().strftime('%Y-%m-%d')
            
            url = f"{self.newsapi_base}/everything"
            params = {
                'q': query,
                'language': 'en',
                'sortBy': 'publishedAt',
                'from': from_date,
                'to': to_date,
                'pageSize': max_articles,
                'apiKey': self.newsapi_key
            }
            
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"NewsAPI found {len(data.get('articles', []))} articles for '{query}'", module='NEWS_COLLECTOR')
                return data.get('articles', [])
            elif response.status_code == 429:
                logger.warning("NewsAPI rate limit reached", module='NEWS_COLLECTOR')
                return None
            else:
                logger.warning(f"NewsAPI error: {response.status_code}", module='NEWS_COLLECTOR')
                return None
        except Exception as e:
            logger.error(f"NewsAPI search failed: {e}", module='NEWS_COLLECTOR')
            return None
    
    def _search_gnews(self, query: str, max_articles: int = 10) -> List[Dict]:
        """Search GNews API for articles"""
        try:
            from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            to_date = datetime.now().strftime('%Y-%m-%d')
            
            url = f"{self.gnews_base}/search"
            params = {
                'q': query,
                'lang': 'en',
                'country': 'us',
                'max': max_articles,
                'from': from_date,
                'to': to_date,
                'sortby': 'publishedAt',
                'apikey': self.gnews_key
            }
            
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"GNews found {len(data.get('articles', []))} articles for '{query}'", module='NEWS_COLLECTOR')
                return data.get('articles', [])
            else:
                logger.warning(f"GNews API error: {response.status_code}", module='NEWS_COLLECTOR')
                return []
        except Exception as e:
            logger.error(f"GNews search failed: {e}", module='NEWS_COLLECTOR')
            return []
    
    def _search_gdelt(self, query: str, max_articles: int = 10) -> List[Dict]:
        """Search GDELT API for articles (optional additional source) with rate limit handling"""
        import time
        
        url = "https://api.gdeltproject.org/api/v2/doc/doc"
        params = {
            'query': query,
            'mode': 'ArtList',
            'format': 'json',
            'maxrecords': max_articles
        }
        
        # Retry logic with exponential backoff for rate limits
        max_retries = 3
        retry_delay = 2  # seconds
        
        for attempt in range(max_retries):
            try:
                # Add delay before retry (except first attempt)
                if attempt > 0:
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                
                response = requests.get(url, params=params, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    articles = []
                    
                    if 'articles' in data:
                        for item in data['articles'][:max_articles]:
                            article = {
                                'title': item.get('title', ''),
                                'description': item.get('summary', ''),
                                'url': item.get('url', ''),
                                'source': item.get('domain', 'GDELT'),
                                'publishedAt': item.get('seendate', ''),
                                'image': '',
                                'category': 'gdelt'
                            }
                            articles.append(article)
                    
                    logger.info(f"GDELT found {len(articles)} articles for '{query}'", module='NEWS_COLLECTOR')
                    return articles
                elif response.status_code == 429:
                    logger.warning(f"GDELT rate limit hit (attempt {attempt + 1}/{max_retries}), retrying...", module='NEWS_COLLECTOR')
                    continue
                else:
                    logger.warning(f"GDELT API error: {response.status_code}", module='NEWS_COLLECTOR')
                    return []
            except Exception as e:
                logger.warning(f"GDELT search failed (non-critical): {e}", module='NEWS_COLLECTOR')
                if attempt == max_retries - 1:
                    return []
                continue
        
        logger.warning(f"GDELT API rate limit exceeded after {max_retries} attempts", module='NEWS_COLLECTOR')
        return []
    
    def _search_worldnewsapi(self, query: str, max_articles: int = 10) -> List[Dict]:
        """Search WorldNewsAPI for articles"""
        try:
            from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            
            url = f"{self.worldnews_base}/search-news"
            params = {
                'api-key': self.worldnews_key,
                'text': query,
                'number': max_articles,
                'earliest-publish-date': from_date,
                'language': 'en',
                'sort': 'publish-time',
                'sort-direction': 'DESC'
            }
            
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                articles = []
                
                if 'news' in data:
                    for item in data['news'][:max_articles]:
                        article = {
                            'title': item.get('title', ''),
                            'description': item.get('summary', '') or item.get('text', '')[:200],
                            'url': item.get('url', ''),
                            'source': item.get('source', 'WorldNewsAPI'),
                            'publishedAt': item.get('publish_date', ''),
                            'image': item.get('image', ''),
                            'category': 'worldnews'
                        }
                        articles.append(article)
                
                logger.info(f"WorldNewsAPI found {len(articles)} articles for '{query}'", module='NEWS_COLLECTOR')
                return articles
            else:
                logger.warning(f"WorldNewsAPI error: {response.status_code}", module='NEWS_COLLECTOR')
                if response.status_code == 429:
                    return None
                return []
        except Exception as e:
            logger.error(f"WorldNewsAPI search failed: {e}", module='NEWS_COLLECTOR')
            return []
    
    def _search_currents(self, query: str, max_articles: int = 10) -> List[Dict]:
        """Search CurrentsAPI for articles"""
        try:
            url = f"{self.currents_base}/search"
            params = {
                'apiKey': self.currents_key,
                'keywords': query,
                'language': 'en',
                'limit': max_articles,
                'type': '1'
            }
            
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                articles = []
                
                if 'news' in data:
                    for item in data['news'][:max_articles]:
                        article = {
                            'title': item.get('title', ''),
                            'description': item.get('description', ''),
                            'url': item.get('url', ''),
                            'source': item.get('author', 'Currents API'),
                            'publishedAt': item.get('published', ''),
                            'image': item.get('image', ''),
                            'category': 'currents'
                        }
                        articles.append(article)
                
                logger.info(f"CurrentsAPI found {len(articles)} articles for '{query}'", module='NEWS_COLLECTOR')
                return articles
            else:
                logger.warning(f"CurrentsAPI error: {response.status_code}", module='NEWS_COLLECTOR')
                return []
        except Exception as e:
            logger.error(f"CurrentsAPI search failed: {e}", module='NEWS_COLLECTOR')
            return []
    
    def _get_mock_data(self, category: str) -> tuple[bool, str, Dict]:
        """Generate mock news data for testing"""
        category_info = NEWS_CATEGORIES.get(category, NEWS_CATEGORIES["comprehensive"])
        
        mock_articles = []
        for i in range(5):
            mock_articles.append({
                'title': f"Sample news article {i+1} for {category}",
                'description': f"Sample description for {category_info['description']}",
                'url': f"https://example.com/article-{i+1}",
                'source': 'Mock Source',
                'publishedAt': datetime.now().isoformat(),
                'image': ''
            })
        
        news_data = {
            'category': category,
            'description': category_info['description'],
            'articles': mock_articles,
            'total_articles': len(mock_articles),
            'sources_used': ['Mock Data'],
            'last_updated': datetime.now().isoformat(),
            'priority': category_info.get('priority', 'MEDIUM')
        }
        
        logger.collector_run('news', f"Collected {len(mock_articles)} mock articles for {category}", "Mock data")
        
        return True, "News data collected successfully (mock)", news_data
    
    def collect_and_save(self, category: str = "comprehensive") -> tuple[bool, str]:
        """Collect and save news data"""
        success, message, news_data = self.collect_news(category)
        
        if not success:
            return success, message
        
        # Save to database
        success, message, news_id = self.service.save_news(news_data)
        
        if success:
            logger.info("Collected and saved news data", module='NEWS_COLLECTOR')
        else:
            logger.error(f"Failed to save news data: {message}", module='NEWS_COLLECTOR')
        
        return success, message
