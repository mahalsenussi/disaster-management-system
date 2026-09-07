#!/usr/bin/env python3
import sqlite3
import json

conn = sqlite3.connect('/home/mahmoud/v2/evaluation_service/database/news.db')
cursor = conn.cursor()

cursor.execute('SELECT articles FROM news_data WHERE id=1')
row = cursor.fetchone()
articles_str = row[0]

print('String length:', len(articles_str))
print('First 300 chars:', articles_str[:300])
print('Last 100 chars:', articles_str[-100:])

try:
    articles = json.loads(articles_str)
    print('JSON parsed successfully, length:', len(articles))
except Exception as e:
    print('JSON parse error:', e)
    print('Trying eval...')
    try:
        articles = eval(articles_str)
        print('Eval successful, length:', len(articles))
    except Exception as e2:
        print('Eval error:', e2)

conn.close()
