#!/usr/bin/env python3
"""
Database Cleanup Service
Shared service for cleaning up orphaned microservice state
"""

import sys
import os
from datetime import datetime

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


class DatabaseCleanupService:
    """Shared service for cleaning up orphaned microservice state."""
    
    def __init__(self, DatabaseManagerInstance=None):
        """Initialize the cleanup service with dependencies."""
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        
        LoggingService.LogInfo("DatabaseCleanupService initialized", "DatabaseCleanupService", "__init__")
    
    def CleanupMicroserviceState(self, ServiceName: str) -> dict:
        """Clean up orphaned state for a specific microservice."""
        try:
            LoggingService.LogInfo(f"Starting cleanup for microservice: {ServiceName}", "DatabaseCleanupService", "CleanupMicroserviceState")
            
            cleanup_results = {
                "ServiceName": ServiceName,
                "JobsReset": 0,
                "ActiveJobsRemoved": 0,
                "ProgressRecordsCleaned": 0,
                "Success": True,
                "Message": "Cleanup completed successfully"
            }
            
            # 1. Reset any "Running" jobs back to "Pending" in QualityTestingQueue
            if ServiceName == "QualityTestingService":
                jobs_reset = self.ResetRunningQualityTestJobs()
                cleanup_results["JobsReset"] = jobs_reset
                LoggingService.LogInfo(f"Reset {jobs_reset} running quality test jobs to pending", "DatabaseCleanupService", "CleanupMicroserviceState")
            
            # 2. Remove all active jobs for this service
            active_jobs_removed = self.RemoveActiveJobs(ServiceName)
            cleanup_results["ActiveJobsRemoved"] = active_jobs_removed
            LoggingService.LogInfo(f"Removed {active_jobs_removed} active jobs for {ServiceName}", "DatabaseCleanupService", "CleanupMicroserviceState")
            
            # 3. Clean up orphaned progress records
            if ServiceName == "QualityTestingService":
                progress_cleaned = self.CleanupOrphanedProgressRecords()
                cleanup_results["ProgressRecordsCleaned"] = progress_cleaned
                LoggingService.LogInfo(f"Cleaned up {progress_cleaned} orphaned progress records", "DatabaseCleanupService", "CleanupMicroserviceState")
            
            LoggingService.LogInfo(f"Cleanup completed for {ServiceName}: {cleanup_results}", "DatabaseCleanupService", "CleanupMicroserviceState")
            return cleanup_results
            
        except Exception as e:
            LoggingService.LogException(f"Error during cleanup for {ServiceName}", e, "DatabaseCleanupService", "CleanupMicroserviceState")
            return {
                "ServiceName": ServiceName,
                "Success": False,
                "Message": str(e)
            }
    
    def ResetRunningQualityTestJobs(self) -> int:
        """Reset any running quality test jobs back to pending."""
        try:
            query = """
                UPDATE QualityTestingQueue 
                SET Status = 'Pending', DateStarted = NULL, DateCompleted = NULL
                WHERE Status = 'Running'
            """
            rows_affected = self.DatabaseManager.DatabaseService.ExecuteNonQuery(query)
            return rows_affected
        except Exception as e:
            LoggingService.LogException("Error resetting running quality test jobs", e, "DatabaseCleanupService", "ResetRunningQualityTestJobs")
            return 0
    
    def RemoveActiveJobs(self, ServiceName: str) -> int:
        """Remove all active jobs for a specific service."""
        try:
            query = "DELETE FROM ActiveJobs WHERE ServiceName = ?"
            rows_affected = self.DatabaseManager.DatabaseService.ExecuteNonQuery(query, (ServiceName,))
            return rows_affected
        except Exception as e:
            LoggingService.LogException(f"Error removing active jobs for {ServiceName}", e, "DatabaseCleanupService", "RemoveActiveJobs")
            return 0
    
    def CleanupOrphanedProgressRecords(self) -> int:
        """Clean up orphaned progress records that are stuck in 'Running' state."""
        try:
            # Find progress records that are running but have no corresponding transcode attempt
            query = """
                DELETE FROM QualityTestProgress 
                WHERE Status = 'Running' 
                AND TranscodeAttemptId NOT IN (
                    SELECT Id FROM TranscodeAttempts WHERE Success IS NULL
                )
            """
            rows_affected = self.DatabaseManager.DatabaseService.ExecuteNonQuery(query)
            return rows_affected
        except Exception as e:
            LoggingService.LogException("Error cleaning up orphaned progress records", e, "DatabaseCleanupService", "CleanupOrphanedProgressRecords")
            return 0
    
    def CleanupAllMicroservices(self) -> dict:
        """Clean up state for all known microservices."""
        try:
            LoggingService.LogInfo("Starting cleanup for all microservices", "DatabaseCleanupService", "CleanupAllMicroservices")
            
            # List of known microservices
            microservices = [
                "QualityTestingService",
                "TranscodeService", 
                "FileScanningService",
                "SystemOrchestratorService"
            ]
            
            results = {}
            for service in microservices:
                results[service] = self.CleanupMicroserviceState(service)
            
            LoggingService.LogInfo(f"Cleanup completed for all microservices: {results}", "DatabaseCleanupService", "CleanupAllMicroservices")
            return {
                "Success": True,
                "Message": "Cleanup completed for all microservices",
                "Results": results
            }
            
        except Exception as e:
            LoggingService.LogException("Error during cleanup for all microservices", e, "DatabaseCleanupService", "CleanupAllMicroservices")
            return {
                "Success": False,
                "Message": str(e)
            }
    
    def GetOrphanedStateSummary(self) -> dict:
        """Get a summary of orphaned state across all microservices."""
        try:
            summary = {
                "RunningQualityTestJobs": 0,
                "ActiveJobs": {},
                "OrphanedProgressRecords": 0
            }
            
            # Count running quality test jobs
            query = "SELECT COUNT(*) FROM QualityTestingQueue WHERE Status = 'Running'"
            result = self.DatabaseManager.DatabaseService.ExecuteQuery(query)
            if result:
                summary["RunningQualityTestJobs"] = result[0][0]
            
            # Count active jobs by service
            query = "SELECT ServiceName, COUNT(*) FROM ActiveJobs GROUP BY ServiceName"
            result = self.DatabaseManager.DatabaseService.ExecuteQuery(query)
            if result:
                for row in result:
                    summary["ActiveJobs"][row[0]] = row[1]
            
            # Count orphaned progress records
            query = """
                SELECT COUNT(*) FROM QualityTestProgress 
                WHERE Status = 'Running' 
                AND TranscodeAttemptId NOT IN (
                    SELECT Id FROM TranscodeAttempts WHERE Success IS NULL
                )
            """
            result = self.DatabaseManager.DatabaseService.ExecuteQuery(query)
            if result:
                summary["OrphanedProgressRecords"] = result[0][0]
            
            return summary
            
        except Exception as e:
            LoggingService.LogException("Error getting orphaned state summary", e, "DatabaseCleanupService", "GetOrphanedStateSummary")
            return {"Error": str(e)}


def main():
    """Main entry point for standalone cleanup."""
    try:
        cleanup_service = DatabaseCleanupService()
        
        # Get summary first
        summary = cleanup_service.GetOrphanedStateSummary()
        print(f"Orphaned state summary: {summary}")
        
        # Clean up all microservices
        results = cleanup_service.CleanupAllMicroservices()
        print(f"Cleanup results: {results}")
        
    except Exception as e:
        print(f"Error during cleanup: {e}")


if __name__ == "__main__":
    main()
