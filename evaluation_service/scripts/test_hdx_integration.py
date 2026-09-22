#!/usr/bin/env python3
"""
Test HDX Integration
Tests the improved HDX knowledge base and web search integration
"""

import sys
import os

# Add evaluation_service to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from evaluation_service.repositories.knowledge_base import KnowledgeBaseRepository
from evaluation_service.modules.chatbot.websearch import ChatbotWebSearch

def test_knowledge_base():
    """Test knowledge base with HDX data"""
    print("Testing Knowledge Base HDX Integration")
    print("=" * 60)
    
    kb_repo = KnowledgeBaseRepository()
    
    # Test 1: Check high priority entries
    print("\n1. High Priority Entries (priority >= 6):")
    high_priority = kb_repo.execute_query(
        "SELECT category, title, source, priority FROM knowledge_entries WHERE is_active = 1 AND priority >= 6 ORDER BY priority DESC LIMIT 10"
    )
    for entry in high_priority:
        print(f"  [{entry['priority']}] {entry['title']} ({entry['category']}) - {entry['source']}")
    
    # Test 2: Check HAPI data
    print("\n2. HAPI Data Entries:")
    hapi_entries = kb_repo.execute_query(
        "SELECT title, source, priority FROM knowledge_entries WHERE source LIKE '%HAPI%' AND is_active = 1 LIMIT 5"
    )
    for entry in hapi_entries:
        print(f"  [{entry['priority']}] {entry['title']} - {entry['source']}")
    
    # Test 3: Test category-based retrieval
    print("\n3. Category-based Retrieval:")
    for category in ['displacement', 'food_security', 'conflict_security']:
        entries = kb_repo.get_entries_by_category(category)
        print(f"  {category}: {len(entries)} entries")
        if entries:
            print(f"    Top: {entries[0]['title']} (priority: {entries[0]['priority']})")
    
    # Test 4: Knowledge context retrieval
    print("\n4. Knowledge Context for displacement:")
    context = kb_repo.get_knowledge_context(categories=['displacement'], max_entries=5)
    print(f"  Context length: {len(context)} characters")
    print(f"  Preview: {context[:200]}...")

def test_web_search():
    """Test improved web search integration"""
    print("\n\nTesting Web Search HDX Integration")
    print("=" * 60)
    
    searcher = ChatbotWebSearch()
    
    # Test 1: HDX search with category filters
    print("\n1. HDX Search with Category Filters:")
    results = searcher.search_hdx("displacement", categories=['displacement'], rows=3)
    print(f"  Found {len(results)} results")
    for r in results:
        has_data = " [has data]" if r.get('has_data') else ""
        print(f"    - {r['title']}{has_data} ({r['organization']})")
    
    # Test 2: HAPI direct search
    print("\n2. HAPI Direct Search:")
    results = searcher.search_hapi_direct("idps", categories=['displacement'], rows=2)
    print(f"  Found {len(results)} results")
    for r in results:
        print(f"    - {r['title']} ({r['records_count']} records)")
    
    # Test 3: Full search integration (skip news to avoid rate limits)
    print("\n3. Search Integration (HDX + Web + Wiki):")
    # Test only HDX, web, and wiki sources
    results = []
    results.extend(searcher.search_hdx("food prices libya", categories=['food_security'], rows=3))
    results.extend(searcher.search_web("food prices libya", categories=['food_security'], rows=2))
    results.extend(searcher.search_wikipedia("food prices libya", categories=['food_security'], rows=1))
    
    print(f"  Found {len(results)} results from various sources")
    for r in results:
        src_type = r.get('source_type', 'unknown')
        print(f"    [{src_type}] {r['title']} ({r['organization']})")
    
    # Test 4: Result formatting
    print("\n4. Result Formatting:")
    if results:
        formatted = searcher.format_results(results[:2], max_items=2)
        print(f"  Formatted output preview:")
        print(f"  {formatted[:300]}...")

if __name__ == '__main__':
    test_knowledge_base()
    test_web_search()
    print("\n\nTest complete!")