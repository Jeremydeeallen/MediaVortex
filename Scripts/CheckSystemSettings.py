#!/usr/bin/env python3
"""
Check SystemSettings Script
"""

import os
import sys

# Add project root to path
ProjectRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ProjectRoot)

from Repositories.DatabaseManager import DatabaseManager

def main():
    db = DatabaseManager()
    result = db.DatabaseService.ExecuteQuery("SELECT SettingKey, SettingValue, Description FROM SystemSettings WHERE SettingKey LIKE 'ScanDir%' ORDER BY SettingKey")
    print('SystemSettings ScanDirectories:')
    for row in result:
        print(f'  {row["SettingKey"]}: {row["SettingValue"]} - {row["Description"]}')

if __name__ == "__main__":
    main()
