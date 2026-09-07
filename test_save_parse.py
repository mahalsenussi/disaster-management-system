#!/usr/bin/env python3
"""
Test saving and parsing news data
"""
import os
import sys
import json
from pathlib import Path

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

def test_save_parse():
    print("Testing save and parse...")
    
    collector = NewsCollector()
    success, message, data = collector.collect_news('comprehensive')
    
    print(f"Collected data type: {type(data)}")
    print(f"Articles type: {type(data.get('articles'))}")
    print(f"Articles length: {len(data.get('articles', []))}")
    print(f"First article type: {type(data.get('articles', [])[0]) if data.get('articles') else 'N/A'}")
    
    # Test JSON serialization
    articles_json = json.dumps(data.get('articles', []))
    print(f"\nJSON serialized length: {len(articles_json)}")
    print(f"JSON first 200 chars: {articles_json[:200]}")
    
    # Test JSON deserialization
    articles_parsed = json.loads(articles_json)
    print(f"\nParsed articles length: {len(articles_parsed)}")
    print(f"First article type: {type(articles_parsed[0]) if articles_parsed else 'N/A'}")

if __name__ == '__main__':
    test_save_parse()
