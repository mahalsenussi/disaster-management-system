"""
Chat History Repository
Stores chat conversations in database for later review and model training
"""
import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Any
from evaluation_service.repositories.base_repository import BaseRepository
from evaluation_service.core.logger import get_logger

logger = get_logger()

class ChatRepository(BaseRepository):
    """Repository for chat history storage"""
    
    def __init__(self):
        db_path = os.path.join(os.path.dirname(__file__), '..', 'database', 'chat_history.db')
        super().__init__(db_path)
        self._init_tables()
    
    def _init_tables(self):
        """Initialize chat history tables"""
        # Sessions table
        query = """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            user_id TEXT,
            created_at TEXT NOT NULL,
            last_activity TEXT NOT NULL,
            model_used TEXT,
            context TEXT
        )
        """
        self.execute_update(query)
        
        # Messages table
        query = """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            message_type TEXT NOT NULL,
            content TEXT NOT NULL,
            model TEXT,
            file_path TEXT,
            metadata TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
        )
        """
        self.execute_update(query)
        
        # Create indexes
        self.execute_update("CREATE INDEX IF NOT EXISTS idx_chat_session_id ON chat_messages(session_id)")
        self.execute_update("CREATE INDEX IF NOT EXISTS idx_chat_timestamp ON chat_messages(timestamp)")
        self.execute_update("CREATE INDEX IF NOT EXISTS idx_chat_user_id ON chat_sessions(user_id)")
        
        logger.info("Chat history database initialized", module='CHAT_REPOSITORY')
    
    def create_session(self, session_id: str, user_id: Optional[str] = None, context: Optional[Dict] = None) -> int:
        """Create a new chat session"""
        now = datetime.now().isoformat()
        query = """
        INSERT INTO chat_sessions (session_id, user_id, created_at, last_activity, context)
        VALUES (?, ?, ?, ?, ?)
        """
        params = (
            session_id,
            user_id or 'anonymous',
            now,
            now,
            str(context) if context else '{}'
        )
        return self.execute_insert(query, params)
    
    def update_session_activity(self, session_id: str, model_used: Optional[str] = None):
        """Update session last activity"""
        now = datetime.now().isoformat()
        query = """
        UPDATE chat_sessions 
        SET last_activity = ?, model_used = COALESCE(?, model_used)
        WHERE session_id = ?
        """
        self.execute_update(query, (now, model_used, session_id))
    
    def add_message(self, session_id: str, message_type: str, content: str, 
                   model: Optional[str] = None, file_path: Optional[str] = None,
                   metadata: Optional[Dict] = None) -> int:
        """Add a message to a session"""
        now = datetime.now().isoformat()
        query = """
        INSERT INTO chat_messages (session_id, message_type, content, model, file_path, metadata, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            session_id,
            message_type,
            content,
            model,
            file_path,
            str(metadata) if metadata else '{}',
            now
        )
        return self.execute_insert(query, params)
    
    def get_session_messages(self, session_id: str, limit: int = 50) -> List[Dict]:
        """Get all messages for a session"""
        query = f"""
        SELECT * FROM chat_messages 
        WHERE session_id = ? 
        ORDER BY timestamp ASC 
        LIMIT {limit}
        """
        return self.execute_query(query, (session_id,))
    
    def get_session_info(self, session_id: str) -> Optional[Dict]:
        """Get session information"""
        query = "SELECT * FROM chat_sessions WHERE session_id = ?"
        results = self.execute_query(query, (session_id,))
        return results[0] if results else None
    
    def get_user_sessions(self, user_id: str, limit: int = 20) -> List[Dict]:
        """Get all sessions for a user"""
        query = f"""
        SELECT * FROM chat_sessions 
        WHERE user_id = ? 
        ORDER BY last_activity DESC 
        LIMIT {limit}
        """
        return self.execute_query(query, (user_id,))
    
    def get_all_sessions(self, limit: int = 100) -> List[Dict]:
        """Get all sessions"""
        query = f"""
        SELECT * FROM chat_sessions 
        ORDER BY last_activity DESC 
        LIMIT {limit}
        """
        return self.execute_query(query)
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session and its messages"""
        try:
            # Delete messages first
            self.execute_update("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
            # Delete session
            self.execute_update("DELETE FROM chat_sessions WHERE session_id = ?", (session_id,))
            return True
        except Exception as e:
            logger.error(f"Error deleting session: {e}")
            return False
    
    def export_session(self, session_id: str) -> Optional[Dict]:
        """Export a session for training purposes"""
        session = self.get_session_info(session_id)
        if not session:
            return None
        
        messages = self.get_session_messages(session_id)
        
        return {
            'session': session,
            'messages': messages,
            'exported_at': datetime.now().isoformat()
        }
