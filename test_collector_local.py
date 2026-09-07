#!/usr/bin/env python3
"""
Test news collector locally with API keys
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

from evaluation_service.modules.news.collector import NewsCollector

def test_collector():
    print("Testing NewsCollector locally...")
    
    collector = NewsCollector()
    
    print(f"NewsAPI Key set: {bool(collector.newsapi_key)}")
    print(f"GNews Key set: {bool(collector.gnews_key)}")
    
    success, message, data = collector.collect_news('comprehensive')
    
    print(f"\nSuccess: {success}")
    print(f"Message: {message}")
    
    if data:
        print(f"Category: {data.get('category')}")
        print(f"Description: {data.get('description')}")
        print(f"Total Articles: {data.get('total_articles')}")
        print(f"Sources Used: {data.get('sources_used')}")
        
        articles = data.get('articles', [])
        print(f"\nArticles ({len(articles)}):")
        for i, article in enumerate(articles[:5]):
            print(f"  {i+1}. {article.get('title', 'No title')}")
            print(f"     Source: {article.get('source', {}).get('name', 'Unknown') if isinstance(article.get('source'), dict) else article.get('source', 'Unknown')}")
            print(f"     Date: {article.get('publishedAt', 'No date')}")
    else:
        print("No data returned")

if __name__ == '__main__':
    test_collector()
