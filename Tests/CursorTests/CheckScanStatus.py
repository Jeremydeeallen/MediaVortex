#!/usr/bin/env python3
"""
CheckScanStatus.py - Check current scan status and running processes
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager

def CheckScanStatus():
    """Check current scan status."""
    try:
        dm = DatabaseManager()
        
        # Check for running scans
        print("=== Running Scans ===")
        scans = dm.DatabaseService.ExecuteQuery(
            "SELECT * FROM ScanJobs WHERE Status = 'Running' ORDER BY StartTime DESC LIMIT 5"
        )
        
        if scans:
            for row in scans:
                print(f"Job {row['JobId']}: {row['Status']} - Started: {row['StartTime']}")
        else:
            print("No running scans found")
        
        # Check recent scans
        print("\n=== Recent Scans (Last 10) ===")
        recent_scans = dm.DatabaseService.ExecuteQuery(
            "SELECT * FROM ScanJobs ORDER BY StartTime DESC LIMIT 10"
        )
        
        if recent_scans:
            for row in recent_scans:
                EndTime = row['EndTime'] if 'EndTime' in row.keys() and row['EndTime'] else 'N/A'
                print(f"Job {row['JobId']}: {row['Status']} - Started: {row['StartTime']} - Ended: {EndTime}")
        else:
            print("No recent scans found")
        
        # Check scan directories
        print("\n=== Scan Directories ===")
        scan_dirs = dm.DatabaseService.ExecuteQuery(
            "SELECT * FROM SystemSettings WHERE SettingKey LIKE 'ScanDirectory_%'"
        )
        
        if scan_dirs:
            for row in scan_dirs:
                print(f"Directory: {row['SettingValue']}")
        else:
            print("No scan directories configured")
            
    except Exception as e:
        print(f"Error checking scan status: {e}")

if __name__ == "__main__":
    CheckScanStatus()
