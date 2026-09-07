#!/usr/bin/env python3
"""
Test script to verify news API keys functionality
"""
import os
import requests
from datetime import datetime, timedelta
from pathlib import Path

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
NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "")
GNEWS_API_KEY = os.environ.get("GNEWS_API_KEY", "")
WORLDNEWS_API_KEY = os.environ.get("WORLDNEWS_API_KEY", "")

def test_newsapi():
    """Test NewsAPI.org"""
    print("\n=== Testing NewsAPI.org ===")
    try:
        from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        to_date = datetime.now().strftime('%Y-%m-%d')
        
        url = "https://newsapi.org/v2/everything"
        params = {
            'q': 'Libya',
            'language': 'en',
            'sortBy': 'publishedAt',
            'from': from_date,
            'to': to_date,
            'pageSize': 5,
            'apiKey': NEWSAPI_KEY
        }
        
        response = requests.get(url, params=params, timeout=30)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            articles = data.get('articles', [])
            print(f"Articles found: {len(articles)}")
            if articles:
                for i, article in enumerate(articles[:2]):
                    print(f"  {i+1}. {article.get('title', 'No title')}")
            return True
        else:
            print(f"Error: {response.text}")
            return False
    except Exception as e:
        print(f"Exception: {e}")
        return False

def test_gnews():
    """Test GNews API"""
    print("\n=== Testing GNews API ===")
    try:
        from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        to_date = datetime.now().strftime('%Y-%m-%d')
        
        url = "https://gnews.io/api/v4/search"
        params = {
            'q': 'Libya news',
            'lang': 'en',
            'country': 'us',
            'max': 5,
            'from': from_date,
            'to': to_date,
            'sortby': 'publishedAt',
            'apikey': GNEWS_API_KEY
        }
        
        response = requests.get(url, params=params, timeout=30)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            articles = data.get('articles', [])
            print(f"Articles found: {len(articles)}")
            if articles:
                for i, article in enumerate(articles[:2]):
                    print(f"  {i+1}. {article.get('title', 'No title')}")
            return True
        else:
            print(f"Error: {response.text}")
            return False
    except Exception as e:
        print(f"Exception: {e}")
        return False

def test_worldnewsapi():
    """Test WorldNewsAPI"""
    print("\n=== Testing WorldNewsAPI ===")
    try:
        from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        url = "https://api.worldnewsapi.com/v2/news"
        params = {
            'apikey': WORLDNEWS_API_KEY,
            'search': 'Libya',
            'limit': 5,
            'date': from_date,
            'language': 'en'
        }
        
        response = requests.get(url, params=params, timeout=10)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if 'data' in data:
                articles = data['data']
                print(f"Articles found: {len(articles)}")
                if articles:
                    for i, article in enumerate(articles[:2]):
                        print(f"  {i+1}. {article.get('title', 'No title')}")
                return True
            else:
                print(f"No data in response: {data}")
                return False
        else:
            print(f"Error: {response.text}")
            return False
    except Exception as e:
        print(f"Exception: {e}")
        return False

if __name__ == '__main__':
    print("Testing News API Keys...")
    
    newsapi_ok = test_newsapi()
    gnews_ok = test_gnews()
    worldnews_ok = test_worldnewsapi()
    
    print("\n=== Summary ===")
    print(f"NewsAPI.org: {'✓ OK' if newsapi_ok else '✗ FAILED'}")
    print(f"GNews: {'✓ OK' if gnews_ok else '✗ FAILED'}")
    print(f"WorldNewsAPI: {'✓ OK' if worldnews_ok else '✗ FAILED'}")
