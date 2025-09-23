#!/usr/bin/env python3
"""
CheckNewJob.py - Check details of the new scan job
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager

def CheckNewJob():
    """Check details of the new scan job."""
    try:
        dm = DatabaseManager()
        
        # Check the new job
        job_id = "d12a9672-7413-4545-9736-51b00fc7abe7"
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
            
    except Exception as e:
        print(f"Error checking job details: {e}")

if __name__ == "__main__":
    CheckNewJob()

