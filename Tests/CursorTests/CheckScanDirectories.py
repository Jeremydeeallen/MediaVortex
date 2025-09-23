#!/usr/bin/env python3
"""
CheckScanDirectories.py - Check scan directory configuration
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager

def CheckScanDirectories():
    """Check scan directory configuration."""
    try:
        dm = DatabaseManager()
        
        # Check all system settings
        print("=== All System Settings ===")
        settings = dm.DatabaseService.ExecuteQuery("SELECT * FROM SystemSettings ORDER BY SettingKey")
        
        if settings:
            for row in settings:
                print(f"{row['SettingKey']}: {row['SettingValue']}")
        else:
            print("No system settings found")
            
    except Exception as e:
        print(f"Error checking scan directories: {e}")

if __name__ == "__main__":
    CheckScanDirectories()
