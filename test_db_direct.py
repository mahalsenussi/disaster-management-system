#!/usr/bin/env python3
"""
Test database directly
"""
import sys
import json

sys.path.insert(0, '/home/mahmoud/v2/evaluation_service')

from evaluation_service.modules.news.repository import NewsRepository

def test_db():
    print("Testing database directly...")
    
    repo = NewsRepository()
    news_data = repo.get_latest_news('comprehensive')
    
    if news_data:
        print(f"Articles type: {type(news_data.get('articles'))}")
        print(f"Articles length: {len(news_data.get('articles', []))}")
        print(f"First article type: {type(news_data.get('articles', [])[0]) if news_data.get('articles') else 'N/A'}")
        print(f"Sources type: {type(news_data.get('sources_used'))}")
        print(f"Sources: {news_data.get('sources_used')}")
    else:
        print("No data found")

if __name__ == '__main__':
    test_db()
