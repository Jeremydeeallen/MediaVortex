#!/usr/bin/env python3
"""
Check Logs Table Schema
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager

def CheckLogsSchema():
    """Check Logs table schema."""
    try:
        db = DatabaseManager()
        
        # Check Logs table schema
        print('=== LOGS TABLE SCHEMA ===')
        schema_query = 'PRAGMA table_info(Logs)'
        result = db.DatabaseService.ExecuteQuery(schema_query)
        
        for row in result:
            print(f'{row["name"]}: {row["type"]}')
            
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    CheckLogsSchema()