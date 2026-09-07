"""
Base repository pattern for database abstraction
Enables future migration from SQLite to PostgreSQL
"""
import sqlite3
import os
from contextlib import contextmanager
from typing import List, Dict, Any, Optional
from evaluation_service.core.logger import get_logger

logger = get_logger()

class BaseRepository:
    """Base repository with common database operations"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_database_exists()
    
    def _ensure_database_exists(self):
        """Ensure database directory and file exist"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
        if not os.path.exists(self.db_path):
            # Create empty database file
            with sqlite3.connect(self.db_path) as conn:
                pass
            logger.info(f"Created database: {self.db_path}", module='REPOSITORY')
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}", module='REPOSITORY', exc_info=True)
            raise
        finally:
            conn.close()
    
    def execute_query(self, query: str, params: tuple = None) -> List[Dict]:
        """Execute a SELECT query and return results as list of dicts"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return [dict(row) for row in cursor.fetchall()]
    
    def execute_update(self, query: str, params: tuple = None) -> int:
        """Execute an INSERT/UPDATE/DELETE query and return rowcount"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return cursor.rowcount
    
    def execute_insert(self, query: str, params: tuple = None) -> int:
        """Execute an INSERT query and return last row ID"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return cursor.lastrowid
    
    def get_by_id(self, table: str, id: int) -> Optional[Dict]:
        """Get record by ID"""
        query = f"SELECT * FROM {table} WHERE id = ?"
        results = self.execute_query(query, (id,))
        return results[0] if results else None
    
    def get_all(self, table: str, limit: int = None, offset: int = None) -> List[Dict]:
        """Get all records from table"""
        query = f"SELECT * FROM {table}"
        if limit:
            query += f" LIMIT {limit}"
        if offset:
            query += f" OFFSET {offset}"
        return self.execute_query(query)
    
    def delete_by_id(self, table: str, id: int) -> bool:
        """Delete record by ID"""
        query = f"DELETE FROM {table} WHERE id = ?"
        return self.execute_update(query, (id,)) > 0
    
    def count(self, table: str) -> int:
        """Count records in table"""
        query = f"SELECT COUNT(*) as count FROM {table}"
        results = self.execute_query(query)
        return results[0]['count'] if results else 0
