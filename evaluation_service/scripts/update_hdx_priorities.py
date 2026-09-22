#!/usr/bin/env python3
"""
Update HDX Knowledge Base Priorities
Adjusts priorities to prioritize actual humanitarian data over generic metadata
"""

import sys
import os
import sqlite3

# Add evaluation_service to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

def update_priorities():
    """Update priorities in the knowledge base"""
    db_path = os.path.join(os.path.dirname(__file__), '..', 'database', 'knowledge_base.db')
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("Updating HDX knowledge base priorities...")
    
    # Reduce priority of generic HDX dataset metadata entries
    cursor.execute("""
        UPDATE knowledge_entries 
        SET priority = 3 
        WHERE category = 'hdx_datasets' 
        AND priority = 4 
        AND source NOT LIKE '%WFP%' 
        AND source NOT LIKE '%IOM%' 
        AND source NOT LIKE '%OCHA%' 
        AND source NOT LIKE '%UNHCR%' 
        AND source NOT LIKE '%WHO%' 
        AND source NOT LIKE '%UNICEF%' 
        AND source NOT LIKE '%IFRC%' 
        AND source NOT LIKE '%ICRC%' 
        AND source NOT LIKE '%ACLED%' 
        AND source NOT LIKE '%IPC%'
    """)
    generic_updated = cursor.rowcount
    print(f"  Reduced priority of {generic_updated} generic HDX dataset entries")
    
    # Increase priority of key humanitarian organizations
    cursor.execute("""
        UPDATE knowledge_entries 
        SET priority = 6 
        WHERE category = 'hdx_datasets' 
        AND priority = 4 
        AND (source LIKE '%WFP%' 
             OR source LIKE '%IOM%' 
             OR source LIKE '%OCHA%' 
             OR source LIKE '%UNHCR%' 
             OR source LIKE '%WHO%' 
             OR source LIKE '%UNICEF%' 
             OR source LIKE '%IFRC%' 
             OR source LIKE '%ICRC%' 
             OR source LIKE '%ACLED%' 
             OR source LIKE '%IPC%')
    """)
    key_updated = cursor.rowcount
    print(f"  Increased priority of {key_updated} key humanitarian dataset entries")
    
    # Ensure HAPI data entries remain high priority
    cursor.execute("""
        UPDATE knowledge_entries 
        SET priority = 9 
        WHERE source LIKE '%HAPI%'
    """)
    hapi_updated = cursor.rowcount
    print(f"  Increased priority of {hapi_updated} HAPI data entries")
    
    conn.commit()
    conn.close()
    
    print(f"\nPriority update complete!")
    print(f"  Generic HDX entries reduced: {generic_updated}")
    print(f"  Key humanitarian entries increased: {key_updated}")
    print(f"  HAPI data entries increased: {hapi_updated}")

if __name__ == '__main__':
    update_priorities()