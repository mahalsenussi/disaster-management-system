#!/usr/bin/env python3
"""
Seed Knowledge Base
Populates the knowledge base with initial humanitarian data and optional HDX collection
"""

import sys
import os
import argparse

# Add evaluation_service to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from evaluation_service.repositories.knowledge_base import KnowledgeBaseRepository
from evaluation_service.data.initial_knowledge_base import INITIAL_KNOWLEDGE_ENTRIES

def seed_knowledge_base():
    """Seed the knowledge base with initial LRC data"""
    kb_repo = KnowledgeBaseRepository()
    
    print("Seeding knowledge base with LRC data...")
    
    for entry in INITIAL_KNOWLEDGE_ENTRIES:
        entry_id = kb_repo.upsert_entry(
            category=entry['category'],
            title=entry['title'],
            content=entry['content'],
            source=entry['source'],
            source_url=entry.get('source_url'),
            tags=entry.get('tags'),
            priority=entry.get('priority', 0)
        )
        print(f"  Added: {entry['title']} (ID: {entry_id})")
    
    print(f"\nLRC knowledge base seeded with {len(INITIAL_KNOWLEDGE_ENTRIES)} entries")

def collect_hdx_data():
    """Collect humanitarian data from HDX"""
    from evaluation_service.modules.hdx.collector import HDXCollector
    
    kb_repo = KnowledgeBaseRepository()
    collector = HDXCollector()
    
    print("Collecting data from HDX (HAPI + CKAN)...")
    print("This may take a few minutes...\n")
    
    result = collector.collect_and_save(kb_repo)
    
    print(f"\nHDX Collection Complete:")
    print(f"  Total entries: {result['entries_total']}")
    print(f"  New entries: {result['entries_saved']}")
    print(f"  Updated entries: {result['entries_updated']}")
    print(f"  HAPI entries: {result['hapi_entries']}")
    print(f"  CKAN dataset summaries: {result['ckan_entries']}")
    print(f"  CSV data summaries: {result['csv_entries']}")
    print(f"  Datasets discovered: {result['datasets_discovered']}")
    print(f"  Errors: {result['errors']}")

def show_status():
    """Show knowledge base status"""
    kb_repo = KnowledgeBaseRepository()
    stats = kb_repo.get_entries_count_by_category()
    total = sum(s.get('count', 0) for s in stats.values())
    
    print(f"\nKnowledge Base Status:")
    print(f"  Total entries: {total}")
    print(f"\n  Entries by category:")
    for cat, data in sorted(stats.items()):
        print(f"    {cat}: {data.get('count', 0)} entries (last updated: {data.get('last_updated', 'never')})")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Knowledge Base Management')
    parser.add_argument('--seed', action='store_true', help='Seed initial LRC data')
    parser.add_argument('--hdx', action='store_true', help='Collect data from HDX')
    parser.add_argument('--all', action='store_true', help='Seed LRC data + collect HDX')
    parser.add_argument('--status', action='store_true', help='Show KB status')
    
    args = parser.parse_args()
    
    if args.all:
        seed_knowledge_base()
        print("\n" + "="*60 + "\n")
        collect_hdx_data()
        print("\n" + "="*60 + "\n")
        show_status()
    elif args.seed:
        seed_knowledge_base()
    elif args.hdx:
        collect_hdx_data()
    elif args.status:
        show_status()
    else:
        # Default: seed + show status
        seed_knowledge_base()
        print()
        show_status()
