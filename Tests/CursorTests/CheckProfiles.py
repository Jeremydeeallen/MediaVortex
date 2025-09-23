#!/usr/bin/env python3
"""
Check Profiles Table
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager

def CheckProfiles():
    """Check the Profiles table."""
    try:
        db = DatabaseManager()
        
        # Check Profiles schema
        result = db.DatabaseService.ExecuteQuery('PRAGMA table_info(Profiles)')
        print('Profiles table schema:')
        for row in result:
            print(f'  {row["name"]} - {row["type"]}')
        print()
        
        # Get sample data
        result = db.DatabaseService.ExecuteQuery('SELECT * FROM Profiles LIMIT 5')
        print('Sample Profiles data:')
        for row in result:
            print(f'  {dict(row)}')
            
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    CheckProfiles()
