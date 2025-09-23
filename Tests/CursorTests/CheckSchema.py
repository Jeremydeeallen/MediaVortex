#!/usr/bin/env python3
"""
Check Database Schema
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager

def CheckSchema():
    """Check the database schema for profile-related tables."""
    try:
        db = DatabaseManager()
        
        # Check ProfileThresholds schema
        result = db.DatabaseService.ExecuteQuery('PRAGMA table_info(ProfileThresholds)')
        print('ProfileThresholds table schema:')
        for row in result:
            print(f'  {row["name"]} - {row["type"]}')
        print()
        
        # Check Profiles schema
        result = db.DatabaseService.ExecuteQuery('PRAGMA table_info(Profiles)')
        print('Profiles table schema:')
        for row in result:
            print(f'  {row["name"]} - {row["type"]}')
        print()
        
        # Get all profile thresholds
        result = db.DatabaseService.ExecuteQuery('SELECT * FROM ProfileThresholds LIMIT 5')
        print('Sample ProfileThresholds data:')
        for row in result:
            print(f'  {dict(row)}')
            
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    CheckSchema()
