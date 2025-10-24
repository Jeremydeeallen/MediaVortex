#!/usr/bin/env python3
"""
Check Z: Drive RootFolders Script
"""

import os
import sys

# Add project root to path
ProjectRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ProjectRoot)

from Repositories.DatabaseManager import DatabaseManager

def main():
    db = DatabaseManager()
    result = db.DatabaseService.ExecuteQuery("SELECT Id, RootFolder FROM RootFolders WHERE LOWER(RootFolder) LIKE 'z:%' ORDER BY RootFolder")
    print('Current Z: drive RootFolders:')
    for row in result:
        print(f'  ID {row["Id"]}: {row["RootFolder"]}')

if __name__ == "__main__":
    main()
