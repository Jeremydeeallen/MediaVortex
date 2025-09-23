#!/usr/bin/env python3
"""
Check TranscodeAttempts Table
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager

def CheckTranscodeAttempts():
    """Check the TranscodeAttempts table."""
    try:
        db = DatabaseManager()
        
        # Check TranscodeAttempts schema
        result = db.DatabaseService.ExecuteQuery('PRAGMA table_info(TranscodeAttempts)')
        print('TranscodeAttempts table schema:')
        for row in result:
            print(f'  {row["name"]} - {row["type"]}')
        print()
        
        # Get recent transcode attempts
        result = db.DatabaseService.ExecuteQuery('SELECT * FROM TranscodeAttempts ORDER BY AttemptDate DESC LIMIT 3')
        print('Recent TranscodeAttempts:')
        for row in result:
            print(f'  {dict(row)}')
            print('---')
            
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    CheckTranscodeAttempts()
