#!/usr/bin/env python3
import sqlite3
import json

conn = sqlite3.connect('/home/mahmoud/v2/evaluation_service/database/news.db')
cursor = conn.cursor()

cursor.execute('SELECT articles FROM news_data WHERE id=1')
row = cursor.fetchone()
articles_str = row[0]

print(f'Raw type: {type(articles_str)}')
print(f'Raw length: {len(articles_str)}')
print(f'First 500 chars: {articles_str[:500]}')
print(f'Last 100 chars: {articles_str[-100:]}')

# Try to understand the structure
parsed = json.loads(articles_str)
print(f'\nAfter JSON parse:')
print(f'Type: {type(parsed)}')
print(f'Length: {len(parsed) if isinstance(parsed, (str, list)) else "N/A"}')

if isinstance(parsed, str):
    print('Parsed result is a STRING, not a list!')
    print(f'First 200 chars of parsed string: {parsed[:200]}')
    # Try parsing again
    try:
        parsed2 = json.loads(parsed)
        print(f'\nAfter second JSON parse:')
        print(f'Type: {type(parsed2)}')
        print(f'Length: {len(parsed2) if isinstance(parsed2, (str, list)) else "N/A"}')
    except:
        print('Second parse failed')

conn.close()
