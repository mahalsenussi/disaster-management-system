"""
Knowledge Base Repository
Stores and retrieves humanitarian information for LRC chatbot
"""
import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Any
from evaluation_service.repositories.base_repository import BaseRepository
from evaluation_service.core.logger import get_logger

logger = get_logger()

class KnowledgeBaseRepository(BaseRepository):
    """Repository for humanitarian knowledge base"""
    
    def __init__(self):
        db_path = os.path.join(os.path.dirname(__file__), '..', 'database', 'knowledge_base.db')
        super().__init__(db_path)
        self._init_tables()
        self._seed_initial_data()
    
    def _init_tables(self):
        """Initialize knowledge base tables"""
        # Knowledge entries table
        query = """
        CREATE TABLE IF NOT EXISTS knowledge_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            source TEXT NOT NULL,
            source_url TEXT,
            tags TEXT,
            priority INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            is_active INTEGER DEFAULT 1
        )
        """
        self.execute_update(query)
        
        # Categories table
        query = """
        CREATE TABLE IF NOT EXISTS knowledge_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            parent_category TEXT
        )
        """
        self.execute_update(query)
        
        # Create indexes
        self.execute_update("CREATE INDEX IF NOT EXISTS idx_kb_category ON knowledge_entries(category)")
        self.execute_update("CREATE INDEX IF NOT EXISTS idx_kb_source ON knowledge_entries(source)")
        self.execute_update("CREATE INDEX IF NOT EXISTS idx_kb_tags ON knowledge_entries(tags)")
        self.execute_update("CREATE INDEX IF NOT EXISTS idx_kb_active ON knowledge_entries(is_active)")
        
        logger.info("Knowledge base database initialized", module='KNOWLEDGE_BASE')
    
    def _seed_initial_data(self):
        """Seed initial categories and data"""
        # Check if categories exist
        existing = self.execute_query("SELECT COUNT(*) as count FROM knowledge_categories")
        if existing[0]['count'] > 0:
            return
        
        # Seed categories
        categories = [
            ('lrc_organization', 'Libyan Red Crescent Organization', None),
            ('lrc_branches', 'LRC Branches and Offices', 'lrc_organization'),
            ('lrc_services', 'LRC Services and Programs', 'lrc_organization'),
            ('humanitarian_principles', 'Humanitarian Principles and Standards', None),
            ('emergency_response', 'Emergency Response Protocols', None),
            ('first_aid', 'First Aid and Medical Services', None),
            ('disaster_management', 'Disaster Management', None),
            ('contact_information', 'Contact Information and Addresses', None),
            ('partners', 'Partner Organizations (IFRC, ICRC, UN)', None),
            ('training', 'Training and Capacity Building', None),
            ('volunteers', 'Volunteer Management', None),
        ]
        
        for name, desc, parent in categories:
            self.execute_update(
                "INSERT OR IGNORE INTO knowledge_categories (name, description, parent_category) VALUES (?, ?, ?)",
                (name, desc, parent)
            )
        
        logger.info("Knowledge base categories seeded", module='KNOWLEDGE_BASE')
    
    def add_entry(self, category: str, title: str, content: str, source: str,
                  source_url: Optional[str] = None, tags: Optional[List[str]] = None,
                  priority: int = 0) -> int:
        """Add a knowledge entry"""
        now = datetime.now().isoformat()
        tags_str = ','.join(tags) if tags else ''
        
        query = """
        INSERT INTO knowledge_entries (category, title, content, source, source_url, tags, priority, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        return self.execute_insert(query, (category, title, content, source, source_url, tags_str, priority, now, now))
    
    def update_entry(self, entry_id: int, title: Optional[str] = None, content: Optional[str] = None,
                    tags: Optional[List[str]] = None, priority: Optional[int] = None) -> bool:
        """Update a knowledge entry"""
        updates = []
        params = []
        
        if title:
            updates.append("title = ?")
            params.append(title)
        if content:
            updates.append("content = ?")
            params.append(content)
        if tags is not None:
            updates.append("tags = ?")
            params.append(','.join(tags))
        if priority is not None:
            updates.append("priority = ?")
            params.append(priority)
        
        if not updates:
            return False
        
        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(entry_id)
        
        query = f"UPDATE knowledge_entries SET {', '.join(updates)} WHERE id = ?"
        self.execute_update(query, params)
        return True
    
    def get_entry(self, entry_id: int) -> Optional[Dict]:
        """Get a specific knowledge entry"""
        query = "SELECT * FROM knowledge_entries WHERE id = ?"
        results = self.execute_query(query, (entry_id,))
        return results[0] if results else None
    
    def get_entries_by_category(self, category: str, active_only: bool = True) -> List[Dict]:
        """Get all entries for a category"""
        if active_only:
            query = "SELECT * FROM knowledge_entries WHERE category = ? AND is_active = 1 ORDER BY priority DESC, created_at DESC"
        else:
            query = "SELECT * FROM knowledge_entries WHERE category = ? ORDER BY priority DESC, created_at DESC"
        return self.execute_query(query, (category,))
    
    def search_entries(self, query_text: str, limit: int = 20) -> List[Dict]:
        """Search knowledge entries"""
        query = f"""
        SELECT * FROM knowledge_entries 
        WHERE is_active = 1 
        AND (title LIKE ? OR content LIKE ? OR tags LIKE ?)
        ORDER BY priority DESC, created_at DESC
        LIMIT {limit}
        """
        search_pattern = f"%{query_text}%"
        return self.execute_query(query, (search_pattern, search_pattern, search_pattern))
    
    def get_all_categories(self) -> List[Dict]:
        """Get all categories"""
        return self.execute_query("SELECT * FROM knowledge_categories ORDER BY name")
    
    def delete_entry(self, entry_id: int) -> bool:
        """Soft delete an entry"""
        return self.execute_update("UPDATE knowledge_entries SET is_active = 0 WHERE id = ?", (entry_id,)) > 0
    
    def get_knowledge_context(self, categories: Optional[List[str]] = None, max_entries: int = 50) -> str:
        """Get formatted knowledge context for AI prompt"""
        if categories:
            entries = []
            for cat in categories:
                entries.extend(self.get_entries_by_category(cat))
        else:
            # Get high priority entries from all categories
            query = f"""
            SELECT * FROM knowledge_entries 
            WHERE is_active = 1 
            ORDER BY priority DESC, created_at DESC
            LIMIT {max_entries}
            """
            entries = self.execute_query(query)
        
        # Format as context
        context_parts = []
        for entry in entries:
            context_parts.append(f"**{entry['title']}** (Source: {entry['source']})\n{entry['content']}")
        
        return "\n\n".join(context_parts)
