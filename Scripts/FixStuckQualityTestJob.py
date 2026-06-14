#!/usr/bin/env python3
"""
FixStuckQualityTestJob.py - Fix the stuck quality test job
"""

import sys
import os
import psutil

# Add current directory to path
sys.path.append('.')

try:
    from Repositories.DatabaseManager import DatabaseManager
    from Services.LoggingService import LoggingService
    
    def main():
        print("=== FIXING STUCK QUALITY TEST JOB ===")
        
        # Initialize database
        db = DatabaseManager()
        
        # Get active quality test jobs
        from Features.ServiceControl.ActiveJobRepository import ActiveJobRepository as _AJR
        activeJobs = db.GetActiveJobsByService(_AJR.BuildActiveJobsQuery("QualityTest"))
        print(f"Found {len(activeJobs)} active quality test jobs:")
        
        for job in activeJobs:
            jobId = job["Id"]
            queueId = job.get("QueueId")
            processId = job.get("ProcessId")
            startedAt = job.get("StartedAt")
            
            print(f"  Active Job {jobId}: Queue {queueId}, PID {processId}, Started: {startedAt}")
            
            # Check if process exists
            if processId:
                processExists = psutil.pid_exists(processId)
                print(f"    Process {processId} exists: {processExists}")
                
                if not processExists:
                    print(f"    ❌ Process {processId} is dead - marking job as failed")
                    
                    # Mark the active job as failed
                    success = db.CompleteActiveJob(jobId, Success=False, ErrorMessage="Process died - cleaned by stuck job detection")
                    if success:
                        print(f"    ✅ Marked Active Job {jobId} as failed")
                    else:
                        print(f"    ❌ Failed to mark Active Job {jobId} as failed")
            else:
                print(f"    ❌ No ProcessId recorded - marking job as failed")
                success = db.CompleteActiveJob(jobId, Success=False, ErrorMessage="No ProcessId recorded - cleaned by stuck job detection")
                if success:
                    print(f"    ✅ Marked Active Job {jobId} as failed")
                else:
                    print(f"    ❌ Failed to mark Active Job {jobId} as failed")
        
        # Get quality test queue to see what's there
        queue = db.GetQualityTestQueue()
        print(f"\nQuality Test Queue has {len(queue)} items:")
        for item in queue:
            print(f"  Queue Item {item['Id']}: {item.get('OriginalFilePath', 'Unknown')}")
            print(f"    Date Added: {item.get('DateAdded', 'Unknown')}")
            print(f"    Date Started: {item.get('DateStarted', 'Not started')}")
        
        print("\n=== FIX COMPLETE ===")
        
    if __name__ == "__main__":
        main()
        
except Exception as e:
    print(f"Error: {str(e)}")
    import traceback
    traceback.print_exc()