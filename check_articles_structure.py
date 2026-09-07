#!/usr/bin/env python3
import sqlite3
import json

conn = sqlite3.connect('/home/mahmoud/v2/evaluation_service/database/news.db')
cursor = conn.cursor()

cursor.execute('SELECT articles FROM news_data WHERE id=1')
row = cursor.fetchone()
articles_str = row[0]

articles = json.loads(articles_str)

print(f'Total parsed items: {len(articles)}')
print(f'Type of articles: {type(articles)}')

if isinstance(articles, list):
    print(f'First item type: {type(articles[0])}')
    print(f'First item: {articles[0]}')
    print(f'Number of dict items: {sum(1 for item in articles if isinstance(item, dict))}')
    print(f'Number of string items: {sum(1 for item in articles if isinstance(item, str))}')
    
    # Check if it's actually a list of dicts
    if all(isinstance(item, dict) for item in articles):
        print('All items are dicts')
        print(f'Actual article count: {len(articles)}')
    else:
        print('Mixed types in articles')
        for i, item in enumerate(articles[:5]):
            print(f'Item {i}: type={type(item)}, value={str(item)[:100]}')

conn.close()
