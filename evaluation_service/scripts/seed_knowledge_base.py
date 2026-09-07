#!/usr/bin/env python3
"""
Seed Knowledge Base
Populates the knowledge base with initial humanitarian data
"""

import sys
import os

# Add evaluation_service to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from evaluation_service.repositories.knowledge_base import KnowledgeBaseRepository
from evaluation_service.data.initial_knowledge_base import INITIAL_KNOWLEDGE_ENTRIES

def seed_knowledge_base():
    """Seed the knowledge base with initial data"""
    kb_repo = KnowledgeBaseRepository()
    
    print("Seeding knowledge base...")
    
    for entry in INITIAL_KNOWLEDGE_ENTRIES:
        entry_id = kb_repo.add_entry(
            category=entry['category'],
            title=entry['title'],
            content=entry['content'],
            source=entry['source'],
            source_url=entry.get('source_url'),
            tags=entry.get('tags'),
            priority=entry.get('priority', 0)
        )
        print(f"✓ Added: {entry['title']} (ID: {entry_id})")
    
    print(f"\nKnowledge base seeded with {len(INITIAL_KNOWLEDGE_ENTRIES)} entries")
    
    # Display categories
    categories = kb_repo.get_all_categories()
    print(f"\nCategories: {len(categories)}")
    for cat in categories:
        print(f"  - {cat['name']}: {cat['description']}")

if __name__ == '__main__':
    seed_knowledge_base()
