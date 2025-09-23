#!/usr/bin/env python3
"""
CheckSpecificJob.py - Check details of a specific scan job
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager

def CheckSpecificJob():
    """Check details of a specific scan job."""
    try:
        dm = DatabaseManager()
        
        # Check the specific pending job
        job_id = "81f05144-5a3f-420e-bc5b-dd2171bf1f20"
        print(f"=== Job Details for {job_id} ===")
        job = dm.DatabaseService.ExecuteQuery(
            f"SELECT * FROM ScanJobs WHERE JobId = '{job_id}'"
        )
        
        if job:
            row = job[0]
            for key in row.keys():
                print(f"{key}: {row[key]}")
        else:
            print("Job not found")
            
        # Check if there are any stuck scans
        print("\n=== All Scan Jobs ===")
        all_jobs = dm.DatabaseService.ExecuteQuery(
            "SELECT JobId, Status, StartTime, EndTime FROM ScanJobs ORDER BY StartTime DESC LIMIT 5"
        )
        
        if all_jobs:
            for row in all_jobs:
                print(f"Job {row['JobId']}: {row['Status']} - Started: {row['StartTime']} - Ended: {row.get('EndTime', 'N/A')}")
        else:
            print("No scan jobs found")
            
    except Exception as e:
        print(f"Error checking job details: {e}")

if __name__ == "__main__":
    CheckSpecificJob()
