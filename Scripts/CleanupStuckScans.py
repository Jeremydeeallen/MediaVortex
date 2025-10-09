#!/usr/bin/env python3
"""
Script to clean up stuck scan jobs in the database.
This will mark any 'Pending' or 'Running' scan jobs as 'Failed' so new scans can start.
"""

import os
import sys
from pathlib import Path

# Add the parent directory to the path so we can import our modules
sys.path.append(str(Path(__file__).parent.parent))

from Services.DatabaseService import DatabaseService
from Services.LoggingService import LoggingService

def CleanupStuckScans():
    """Clean up stuck scan jobs."""
    try:
        LoggingService.LogInfo("Starting cleanup of stuck scan jobs", "CleanupStuckScans", "main")
        
        DatabaseServiceInstance = DatabaseService()
        
        # First, let's see what stuck jobs we have
        Query = "SELECT Id, JobId, RootFolderPath, Status, StartTime FROM ScanJobs WHERE Status IN ('Pending', 'Running')"
        StuckJobs = DatabaseServiceInstance.ExecuteQuery(Query)
        
        if not StuckJobs:
            LoggingService.LogInfo("No stuck scan jobs found", "CleanupStuckScans", "main")
            return
        
        LoggingService.LogInfo(f"Found {len(StuckJobs)} stuck scan jobs", "CleanupStuckScans", "main")
        
        for Job in StuckJobs:
            LoggingService.LogInfo(f"Stuck job: ID={Job['Id']}, JobId={Job['JobId']}, Path={Job['RootFolderPath']}, Status={Job['Status']}, StartTime={Job['StartTime']}", "CleanupStuckScans", "main")
        
        # Update stuck jobs to 'Failed' status
        UpdateQuery = """
        UPDATE ScanJobs 
        SET Status = 'Failed', 
            EndTime = datetime('now', 'localtime'),
            ErrorMessage = 'Cleaned up by CleanupStuckScans script - job was stuck',
            LastUpdated = datetime('now', 'localtime')
        WHERE Status IN ('Pending', 'Running')
        """
        
        AffectedRows = DatabaseServiceInstance.ExecuteNonQuery(UpdateQuery)
        LoggingService.LogInfo(f"Updated {AffectedRows} stuck scan jobs to 'Failed' status", "CleanupStuckScans", "main")
        
        # Verify the cleanup
        RemainingStuckJobs = DatabaseServiceInstance.ExecuteQuery(Query)
        if not RemainingStuckJobs:
            LoggingService.LogInfo("Cleanup completed successfully - no stuck jobs remain", "CleanupStuckScans", "main")
        else:
            LoggingService.LogError(f"Warning: {len(RemainingStuckJobs)} stuck jobs still remain after cleanup", "CleanupStuckScans", "main")
        
    except Exception as e:
        LoggingService.LogException("Error during cleanup of stuck scan jobs", e, "CleanupStuckScans", "main")
        raise

if __name__ == "__main__":
    CleanupStuckScans()
    print("Cleanup completed. Check the Logs table for details.")
