"""
FixStuckQualityTestJob.py
Script to fix stuck quality testing jobs that are showing in the Activity dashboard.
"""

import sys
import os
from datetime import datetime, timedelta

# Add the parent directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


def FixStuckQualityTestJobs():
    """Fix stuck quality testing jobs that have been running too long."""
    try:
        LoggingService.LogInfo("Starting fix for stuck quality testing jobs", "FixStuckQualityTestJob", "FixStuckQualityTestJobs")
        
        db = DatabaseManager()
        
        # Find jobs that have been running for more than 2 hours
        cutoff_time = datetime.now() - timedelta(hours=2)
        
        query = """
            SELECT Id, TranscodeAttemptId, FileName, DateStarted, Status 
            FROM QualityTestingQueue 
            WHERE Status = 'Running' AND DateStarted < ?
            ORDER BY DateStarted ASC
        """
        
        stuck_jobs = db.DatabaseService.ExecuteQuery(query, (cutoff_time,))
        
        if not stuck_jobs:
            LoggingService.LogInfo("No stuck quality testing jobs found", "FixStuckQualityTestJob", "FixStuckQualityTestJobs")
            return
        
        LoggingService.LogInfo(f"Found {len(stuck_jobs)} stuck quality testing jobs", "FixStuckQualityTestJob", "FixStuckQualityTestJobs")
        
        for job in stuck_jobs:
            job_id = job['Id']
            transcode_attempt_id = job['TranscodeAttemptId']
            file_name = job['FileName']
            date_started = job['DateStarted']
            
            LoggingService.LogInfo(f"Fixing stuck job {job_id} for file: {file_name}", "FixStuckQualityTestJob", "FixStuckQualityTestJobs")
            
            # Update the job status to Failed with appropriate error message
            update_query = """
                UPDATE QualityTestingQueue 
                SET Status = 'Failed', 
                    DateCompleted = ?, 
                    ErrorMessage = ?
                WHERE Id = ?
            """
            
            error_message = f"Job stuck in running state since {date_started}. Automatically marked as failed due to timeout."
            current_time = datetime.now()
            
            result = db.DatabaseService.ExecuteNonQuery(update_query, (current_time, error_message, job_id))
            
            if result > 0:
                LoggingService.LogInfo(f"Successfully marked job {job_id} as failed", "FixStuckQualityTestJob", "FixStuckQualityTestJobs")
                
                # Also create a progress record to show the failure
                db.SaveQualityTestProgress(
                    VMAFQueueId=job_id,
                    TranscodeAttemptId=transcode_attempt_id,
                    Status="Failed",
                    ProgressPercent=0.0,
                    CurrentPhase="Job Timeout - Automatically Failed",
                    StartTime=date_started,
                    EndTime=current_time,
                    ErrorMessage=error_message,
                    StrategyType="Unknown"
                )
                
                LoggingService.LogInfo(f"Created failure progress record for job {job_id}", "FixStuckQualityTestJob", "FixStuckQualityTestJobs")
            else:
                LoggingService.LogError(f"Failed to update job {job_id}", "FixStuckQualityTestJob", "FixStuckQualityTestJobs")
        
        LoggingService.LogInfo("Completed fix for stuck quality testing jobs", "FixStuckQualityTestJob", "FixStuckQualityTestJobs")
        
    except Exception as e:
        LoggingService.LogException("Error fixing stuck quality testing jobs", e, "FixStuckQualityTestJob", "FixStuckQualityTestJobs")


def CheckQualityTestJobStatus():
    """Check the current status of quality testing jobs."""
    try:
        db = DatabaseManager()
        
        # Get all running jobs
        running_jobs = db.GetRunningQualityTestingJobs()
        print(f"Currently running quality testing jobs: {len(running_jobs)}")
        
        for job in running_jobs:
            print(f"  Job ID: {job.Id}")
            print(f"  File: {job.FileName}")
            print(f"  Status: {job.Status}")
            print(f"  Started: {job.DateStarted}")
            print(f"  Progress: ", end="")
            
            # Get progress data
            progress = db.GetQualityTestProgress(job.Id, job.TranscodeAttemptId)
            if progress:
                print(f"{progress['ProgressPercentage']}% - {progress['CurrentStep']}")
            else:
                print("No progress data found")
            print()
        
    except Exception as e:
        print(f"Error checking quality test job status: {e}")


if __name__ == "__main__":
    print("Quality Testing Job Status Check")
    print("=" * 40)
    CheckQualityTestJobStatus()
    
    print("\nFixing stuck jobs...")
    print("=" * 40)
    FixStuckQualityTestJobs()
    
    print("\nQuality Testing Job Status After Fix")
    print("=" * 40)
    CheckQualityTestJobStatus()
