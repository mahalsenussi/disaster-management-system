#!/usr/bin/env python3
"""
Test news collector with detailed search factors
"""
import os
import sys
from pathlib import Path

# Add the evaluation_service to path
sys.path.insert(0, '/home/mahmoud/v2/evaluation_service')

def _load_env():
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)

_load_env()

# API keys loaded from .env (gitignored) or environment

from evaluation_service.modules.news.collector import NewsCollector, NEWS_CATEGORIES

def test_collector_detailed():
    print("Testing NewsCollector with detailed search factors...\n")
    
    collector = NewsCollector()
    
    print(f"NewsAPI Key set: {bool(collector.newsapi_key)}")
    print(f"GNews Key set: {bool(collector.gnews_key)}")
    print()
    
    # Test comprehensive category
    category = 'comprehensive'
    category_info = NEWS_CATEGORIES.get(category, NEWS_CATEGORIES["comprehensive"])
    
    print(f"Category: {category}")
    print(f"Description: {category_info['description']}")
    print(f"Priority: {category_info['priority']}")
    print()
    
    print("NewsAPI search terms:")
    for term in category_info.get('newsapi_terms', []):
        print(f"  - {term}")
    print()
    
    print("GNews search terms:")
    for term in category_info.get('gnews_terms', []):
        print(f"  - {term}")
    print()
    
    print("=" * 60)
    print("COLLECTING NEWS...")
    print("=" * 60)
    
    success, message, data = collector.collect_news(category)
    
    print(f"\nSuccess: {success}")
    print(f"Message: {message}")
    print()
    
    if data:
        print(f"Category: {data.get('category')}")
        print(f"Description: {data.get('description')}")
        print(f"Total Articles: {data.get('total_articles')}")
        print(f"Sources Used: {data.get('sources_used')}")
        print(f"Priority: {data.get('priority')}")
        print(f"Last Updated: {data.get('last_updated')}")
        
        articles = data.get('articles', [])
        print(f"\nArticles ({len(articles)}):")
        print("-" * 60)
        for i, article in enumerate(articles):
            print(f"\n{i+1}. {article.get('title', 'No title')}")
            print(f"   Description: {article.get('description', 'No description')[:100]}...")
            
            source = article.get('source')
            if isinstance(source, dict):
                print(f"   Source: {source.get('name', 'Unknown')}")
            else:
                print(f"   Source: {source or 'Unknown'}")
            
            print(f"   Published: {article.get('publishedAt', 'No date')}")
            print(f"   URL: {article.get('url', 'No URL')}")
    else:
        print("No data returned")

if __name__ == '__main__':
    test_collector_detailed()
