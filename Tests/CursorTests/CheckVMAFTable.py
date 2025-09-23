#!/usr/bin/env python3
"""
Check VMAF Table Schema and Data
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager

def CheckVMAFTable():
    """Check VMAF table schema and data."""
    try:
        db = DatabaseManager()
        
        # Check VMAF table schema
        print('=== VMAF TABLE SCHEMA ===')
        schema_query = 'PRAGMA table_info(VMAFQueue)'
        result = db.DatabaseService.ExecuteQuery(schema_query)
        
        for row in result:
            print(f'{row["name"]}: {row["type"]}')
        
        # Check VMAF data
        print('\n=== VMAF TABLE DATA ===')
        data_query = 'SELECT * FROM VMAFQueue ORDER BY Id DESC LIMIT 5'
        data_result = db.DatabaseService.ExecuteQuery(data_query)
        
        if data_result:
            for i, row in enumerate(data_result, 1):
                print(f'\n--- Row {i} ---')
                for key in row.keys():
                    print(f'{key}: {row[key]}')
        else:
            print('No VMAF data found')
            
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    CheckVMAFTable()
