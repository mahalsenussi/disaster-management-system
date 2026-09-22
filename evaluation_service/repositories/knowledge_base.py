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
        # Check which categories already exist
        existing_rows = self.execute_query("SELECT name FROM knowledge_categories")
        existing_names = {row['name'] for row in existing_rows}
        
        # Seed categories (skip any that already exist)
        categories = [
            # Core LRC categories
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
            # HDX humanitarian data categories
            ('displacement', 'Displacement and Migration Data', None),
            ('humanitarian_needs', 'Humanitarian Needs Assessments', None),
            ('conflict_security', 'Conflict and Security Events', None),
            ('operational_presence', 'Humanitarian Operational Presence', None),
            ('funding', 'Humanitarian Funding and Appeals', None),
            ('food_security', 'Food Security and Nutrition', None),
            ('population', 'Population and Demographics', None),
            ('climate_data', 'Climate and Weather Data', None),
            ('health', 'Health Data and Facilities', None),
            ('education', 'Education Data', None),
            ('infrastructure', 'Infrastructure and Transportation', None),
            ('geodata', 'Geographic and Administrative Data', None),
            ('hdx_datasets', 'HDX Dataset Catalog', None),
        ]
        
        added = 0
        for name, desc, parent in categories:
            if name not in existing_names:
                self.execute_update(
                    "INSERT OR IGNORE INTO knowledge_categories (name, description, parent_category) VALUES (?, ?, ?)",
                    (name, desc, parent)
                )
                added += 1
        
        if added > 0:
            logger.info(f"Knowledge base: added {added} new categories (total: {len(categories)})", module='KNOWLEDGE_BASE')
        else:
            logger.info("Knowledge base categories already up to date", module='KNOWLEDGE_BASE')
    
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

    def search_entries_scored(self, query_text: str, limit: int = 20,
                              locations: Optional[List[str]] = None,
                              boost_categories: Optional[List[str]] = None) -> List[Dict]:
        """Scored keyword search.

        Extracts keywords from the query and ranks entries by how many keywords
        they match, giving extra weight to title/tags hits, an exact location
        hit (if a location is detected in the query), and category matches.
        """
        import re
        from collections import Counter

        stopwords = {'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had',
                     'was', 'one', 'our', 'has', 'how', 'tell', 'what', 'about', 'does',
                     'there', 'this', 'that', 'with', 'from', 'have', 'some', 'do', 'me',
                     'would', 'could', 'should', 'will', 'any', 'just', 'your', 'its',
                     'been', 'they', 'them', 'their', 'these', 'those', 'were', 'said',
                     'whats', 'whats', 'lets', 'let', 'check', 'see', 'look', 'want',
                     'available', 'avilable', 'we', 'ok', 'okay', 'yeah', 'yes', 'aids'}

        # Tokenize the query into meaningful keywords (skip locations, handled separately)
        words = re.findall(r'[a-zA-Z]{3,}', query_text.lower())
        keywords = [w for w in words if w not in stopwords]

        if locations:
            kw_set = set(k for k in keywords if k not in [loc.lower().replace(' ', '') for loc in locations])
        else:
            kw_set = set(keywords)

        # SQL LIKE matching any keyword
        like_conds = []
        params = []
        for kw in list(kw_set)[:8]:
            like_conds.append("(title LIKE ? OR content LIKE ? OR tags LIKE ?)")
            params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])
        if not like_conds:
            like_conds.append("1=1")
        like_clause = " OR ".join(like_conds)

        query = f"""
        SELECT * FROM knowledge_entries 
        WHERE is_active = 1 AND ({like_clause})
        """
        rows = self.execute_query(query, params)

        scored = []
        for e in rows:
            title_l = e.get('title', '').lower()
            content_l = e.get('content', '').lower()
            tags_l = (e.get('tags') or '').lower()
            words_title = [w.strip('.,;:()[]{}\"\'!?') for w in title_l.split()]
            words_content = [w.strip('.,;:()[]{}\"\'!?') for w in content_l.split()[:400]]
            score = 0
            matched = 0
            for kw in kw_set:
                in_title = kw in title_l or any((kw in w or w.startswith(kw) or kw.startswith(w)) and len(w) >= 3 for w in words_title)
                in_tags = kw in tags_l
                in_content = kw in content_l or any((kw in w or w.startswith(kw) or kw.startswith(w)) and len(w) >= 3 for w in words_content)
                if in_title or in_tags or in_content:
                    matched += 1
                if in_title:
                    score += 3
                elif in_tags:
                    score += 2
                elif in_content:
                    score += 1
            if locations:
                for loc in locations:
                    loc_l = loc.lower()
                    if loc_l in title_l:
                        score += 5
                    elif loc_l in content_l or loc_l in tags_l:
                        score += 3
            if boost_categories and e.get('category') in boost_categories:
                score += 4
            # Prefer entries that matched multiple distinct keywords
            score += min(matched, 4) * 2
            scored.append((score, matched, e))

        scored.sort(key=lambda x: (-x[0], x[1]))
        # Drop zero-score rows (shouldn't happen with LIKE, but be safe)
        return [e for s, m, e in scored if s > 0][:limit]
    
    def get_all_categories(self) -> List[Dict]:
        """Get all categories"""
        return self.execute_query("SELECT * FROM knowledge_categories ORDER BY name")
    
    def delete_entry(self, entry_id: int) -> bool:
        """Soft delete an entry"""
        return self.execute_update("UPDATE knowledge_entries SET is_active = 0 WHERE id = ?", (entry_id,)) > 0
    
    def upsert_entry(self, category: str, title: str, content: str, source: str,
                     source_url: Optional[str] = None, tags: Optional[List[str]] = None,
                     priority: int = 0) -> int:
        """Insert or update a knowledge entry (dedup by category+title)"""
        existing = self.execute_query(
            "SELECT id FROM knowledge_entries WHERE category = ? AND title = ? AND is_active = 1",
            (category, title)
        )
        if existing:
            self.update_entry(existing[0]['id'], content=content, tags=tags, priority=priority)
            return existing[0]['id']
        else:
            return self.add_entry(category, title, content, source, source_url, tags, priority)

    def get_entries_count_by_category(self) -> Dict[str, Dict]:
        """Get entry counts grouped by category"""
        query = """
        SELECT category, COUNT(*) as count, MAX(updated_at) as last_updated
        FROM knowledge_entries WHERE is_active = 1
        GROUP BY category ORDER BY category
        """
        rows = self.execute_query(query)
        return {row['category']: dict(row) for row in rows}

    def get_knowledge_context(self, categories: Optional[List[str]] = None, max_entries: int = 50) -> str:
        """Get formatted knowledge context for AI prompt"""
        if categories:
            entries = []
            for cat in categories:
                # For hdx_datasets category, limit to high priority entries only
                if cat == 'hdx_datasets':
                    cat_entries = self.execute_query(
                        "SELECT * FROM knowledge_entries WHERE category = ? AND is_active = 1 AND priority >= 6 ORDER BY priority DESC, created_at DESC LIMIT 10",
                        (cat,)
                    )
                    entries.extend(cat_entries)
                else:
                    entries.extend(self.get_entries_by_category(cat))
        else:
            # Get high priority entries from all categories, exclude low-priority metadata
            query = f"""
            SELECT * FROM knowledge_entries 
            WHERE is_active = 1 AND priority >= 5
            ORDER BY priority DESC, created_at DESC
            LIMIT {max_entries}
            """
            entries = self.execute_query(query)
        
        # Format as context
        context_parts = []
        for entry in entries:
            context_parts.append(f"**{entry['title']}** (Source: {entry['source']})\n{entry['content']}")
        
        return "\n\n".join(context_parts)
