"""
News repository for database operations
"""
import os
import ast
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from evaluation_service.repositories.base_repository import BaseRepository
from evaluation_service.core.logger import get_logger

logger = get_logger()

class NewsRepository(BaseRepository):
    """Repository for news data operations"""
    
    def __init__(self):
        db_path = os.path.join(os.path.dirname(__file__), '..', '..', 'database', 'news.db')
        super().__init__(db_path)
        self._init_tables()
    
    def _init_tables(self):
        """Initialize news data table"""
        query = """
        CREATE TABLE IF NOT EXISTS news_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            description TEXT,
            articles TEXT,
            total_articles INTEGER,
            sources_used TEXT,
            priority TEXT,
            risk_score REAL,
            ollama_evaluation TEXT,
            evaluated_at TIMESTAMP,
            collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        self.execute_update(query)
        
        # Migrate: add columns if they don't exist (check via PRAGMA to avoid noisy errors)
        try:
            existing_cols = {r['name'] for r in self.execute_query("PRAGMA table_info(news_data)")}
        except Exception:
            existing_cols = set()
        
        migration_cols = {
            'category': 'TEXT',
            'description': 'TEXT',
            'articles': 'TEXT',
            'total_articles': 'INTEGER',
            'sources_used': 'TEXT',
            'priority': 'TEXT',
            'evaluated_at': 'TIMESTAMP'
        }
        for col, col_type in migration_cols.items():
            if col not in existing_cols:
                try:
                    self.execute_update(f"ALTER TABLE news_data ADD COLUMN {col} {col_type}")
                except Exception as e:
                    logger.warning(f"Failed to migrate column {col}: {e}", module='NEWS_REPOSITORY')
        
        # Create indexes
        self.execute_update("CREATE INDEX IF NOT EXISTS idx_news_collected_at ON news_data(collected_at)")
        self.execute_update("CREATE INDEX IF NOT EXISTS idx_news_category ON news_data(category)")
        
        # Only create evaluated_at index if column exists
        try:
            self.execute_update("CREATE INDEX IF NOT EXISTS idx_news_evaluated_at ON news_data(evaluated_at)")
        except:
            pass  # Column might not exist yet
        
        logger.info("News database initialized", module='NEWS_REPOSITORY')
    
    def save_news_data(self, data: Dict) -> int:
        """Save news data to database"""
        import json
        query = """
        INSERT INTO news_data (category, description, articles, total_articles, sources_used, priority, risk_score, ollama_evaluation)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            data.get('category'),
            data.get('description'),
            json.dumps(data.get('articles', [])),
            data.get('total_articles'),
            json.dumps(data.get('sources_used', [])),
            data.get('priority'),
            data.get('risk_score'),
            data.get('ollama_evaluation')
        )
        return self.execute_insert(query, params)
    
    def get_latest_news(self, category: str = None) -> Optional[Dict]:
        """Get latest news data"""
        import json
        if category:
            query = """
            SELECT * FROM news_data 
            WHERE category = ?
            ORDER BY collected_at DESC 
            LIMIT 1
            """
            results = self.execute_query(query, (category,))
        else:
            query = """
            SELECT * FROM news_data 
            ORDER BY collected_at DESC 
            LIMIT 1
            """
            results = self.execute_query(query)
        
        if results:
            result = results[0]
            # Parse JSON fields
            if result.get('articles'):
                articles_str = result['articles']
                logger.info(f"Articles field type: {type(articles_str)}, length: {len(articles_str) if isinstance(articles_str, str) else 'N/A'}", module='NEWS_REPOSITORY')
                if isinstance(articles_str, str):
                    try:
                        result['articles'] = json.loads(articles_str)
                        logger.info(f"Successfully parsed articles as JSON, count: {len(result['articles'])}", module='NEWS_REPOSITORY')
                    except json.JSONDecodeError as e:
                        # If JSON parsing fails, try ast.literal_eval for Python string representation (safe)
                        try:
                            result['articles'] = ast.literal_eval(articles_str)
                            logger.info(f"Successfully parsed articles with ast.literal_eval, count: {len(result['articles'])}", module='NEWS_REPOSITORY')
                        except Exception as parse_e:
                            logger.error(f"Failed to parse articles: JSON error {e}, parse error {parse_e}", module='NEWS_REPOSITORY')
                            result['articles'] = []
                else:
                    # Already a list, use as-is
                    logger.info(f"Articles already a list, count: {len(articles_str)}", module='NEWS_REPOSITORY')
                    result['articles'] = articles_str
            if result.get('sources_used'):
                sources_str = result['sources_used']
                if isinstance(sources_str, str):
                    try:
                        # Try to parse as JSON first
                        result['sources_used'] = json.loads(sources_str)
                    except json.JSONDecodeError as e:
                        # If that fails, try ast.literal_eval (safe)
                        try:
                            result['sources_used'] = ast.literal_eval(sources_str)
                        except Exception as parse_e:
                            logger.error(f"Failed to parse sources: JSON error {e}, parse error {parse_e}", module='NEWS_REPOSITORY')
                            result['sources_used'] = [sources_str] if sources_str else []
                else:
                    # Already a list, use as-is
                    result['sources_used'] = sources_str
            return result
        return None
    
    def get_news_history(self, hours: int = 24, category: str = None) -> List[Dict]:
        """Get news history"""
        import json
        since = datetime.utcnow() - timedelta(hours=hours)
        
        if category:
            query = """
            SELECT * FROM news_data 
            WHERE category = ? AND collected_at >= ?
            ORDER BY collected_at DESC
            """
            results = self.execute_query(query, (category, since.isoformat()))
        else:
            query = """
            SELECT * FROM news_data 
            WHERE collected_at >= ?
            ORDER BY collected_at DESC
            """
            results = self.execute_query(query, (since.isoformat(),))
        
        # Parse JSON fields
        for result in results:
            if result.get('articles'):
                result['articles'] = json.loads(result['articles'])
            if result.get('sources_used'):
                result['sources_used'] = json.loads(result['sources_used'])
        
        return results
    
    def update_risk_score(self, news_id: int, risk_score: float, ollama_evaluation: str):
        """Update risk score and evaluation for news data"""
        query = """
        UPDATE news_data 
        SET risk_score = ?, ollama_evaluation = ?, evaluated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """
        self.execute_update(query, (risk_score, ollama_evaluation, news_id))
    
    def is_data_fresh(self, category: str = None, max_age_hours: int = 1) -> bool:
        """Check if news data is fresh (less than max_age_hours old)"""
        latest = self.get_latest_news(category)
        if not latest:
            return False
        
        collected_at = latest.get('collected_at')
        if not collected_at:
            return False
        
        try:
            collected_time = datetime.fromisoformat(collected_at)
            age = datetime.utcnow() - collected_time
            return age.total_seconds() < (max_age_hours * 3600)
        except:
            return False
    
    def is_evaluation_fresh(self, category: str = None, max_age_hours: int = 1) -> bool:
        """Check if evaluation is fresh (less than max_age_hours old)"""
        latest = self.get_latest_news(category)
        if not latest:
            return False
        
        evaluated_at = latest.get('evaluated_at')
        if not evaluated_at:
            return False
        
        try:
            evaluated_time = datetime.fromisoformat(evaluated_at)
            age = datetime.utcnow() - evaluated_time
            return age.total_seconds() < (max_age_hours * 3600)
        except:
            return False
