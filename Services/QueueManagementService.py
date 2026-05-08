"""
QueueManagementService
Shared service for managing queue operations across different queue types
"""

from typing import Dict, Any, List
from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


class QueueManagementService:
    """Shared service for managing queue operations across different queue types."""
    
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
    
    def ResetRunningJobsToPending(self, QueueType: str, CancelReason: str = "Cancelled by user stop request", WorkerName: str = None) -> Dict[str, Any]:
        """Reset running jobs to pending status for specified queue type.
        WorkerName scopes to a single worker. None = all workers (admin action)."""
        try:
            LoggingService.LogFunctionEntry("ResetRunningJobsToPending", "QueueManagementService", QueueType)

            if QueueType == "TranscodeQueue":
                return self.ResetTranscodeQueueRunningJobs(CancelReason, WorkerName)
            elif QueueType == "QualityTestingQueue":
                return self.ResetQualityTestingQueueRunningJobs(CancelReason)
            else:
                return {
                    "Success": False,
                    "ErrorMessage": f"Unknown queue type: {QueueType}"
                }

        except Exception as e:
            LoggingService.LogException("Error resetting running jobs", e, "QueueManagementService", "ResetRunningJobsToPending")
            return {
                "Success": False,
                "ErrorMessage": str(e)
            }
    
    def ResetTranscodeQueueRunningJobs(self, CancelReason: str, WorkerName: str = None) -> Dict[str, Any]:
        """Reset running transcoding jobs to pending and cancel associated attempts.
        WorkerName scopes to a single worker. None = all workers (admin action)."""
        try:
            LoggingService.LogFunctionEntry("ResetTranscodeQueueRunningJobs", "QueueManagementService")

            # Get running transcoding jobs (filtered by worker if specified)
            runningJobs = self.DatabaseManager.GetTranscodeQueueItemsByStatus("Running")
            if WorkerName and runningJobs:
                runningJobs = [j for j in runningJobs if j.ClaimedBy == WorkerName]

            if runningJobs and len(runningJobs) > 0:
                LoggingService.LogInfo(f"Resetting {len(runningJobs)} running transcoding jobs to pending status (worker={WorkerName or 'all'})",
                                     "QueueManagementService", "ResetTranscodeQueueRunningJobs")

                # Reset queue items to pending and clear ownership
                if WorkerName:
                    queueResetQuery = """
                    UPDATE TranscodeQueue
                    SET Status = 'Pending', DateStarted = NULL, ClaimedBy = NULL, ClaimedAt = NULL
                    WHERE Status = 'Running' AND ClaimedBy = %s
                    """
                    queueAffectedRows = self.DatabaseManager.DatabaseService.ExecuteNonQuery(queueResetQuery, (WorkerName,))
                else:
                    queueResetQuery = """
                    UPDATE TranscodeQueue
                    SET Status = 'Pending', DateStarted = NULL, ClaimedBy = NULL, ClaimedAt = NULL
                    WHERE Status = 'Running'
                    """
                    queueAffectedRows = self.DatabaseManager.DatabaseService.ExecuteNonQuery(queueResetQuery)

                # Cancel associated transcode attempts
                transcodeAttemptsQuery = """
                UPDATE TranscodeAttempts
                SET Success = FALSE, ErrorMessage = %s
                WHERE MediaFileId IN (
                    SELECT MediaFileId FROM TranscodeQueue
                    WHERE Status = 'Pending' AND DateStarted IS NULL
                    AND MediaFileId IS NOT NULL
                ) AND Success IS NULL
                """
                attemptsAffectedRows = self.DatabaseManager.DatabaseService.ExecuteNonQuery(transcodeAttemptsQuery, (CancelReason,))
                
                LoggingService.LogInfo(f"Reset {queueAffectedRows} transcoding queue items to pending and cancelled {attemptsAffectedRows} transcode attempts", 
                                     "QueueManagementService", "ResetTranscodeQueueRunningJobs")
                
                # Log details of reset jobs
                for job in runningJobs:
                    LoggingService.LogInfo(f"  - Reset transcoding job {job.Id}: {job.FileName}", 
                                         "QueueManagementService", "ResetTranscodeQueueRunningJobs")
                
                return {
                    "Success": True,
                    "Message": f"Reset {queueAffectedRows} transcoding jobs to pending",
                    "QueueAffectedRows": queueAffectedRows,
                    "AttemptsAffectedRows": attemptsAffectedRows,
                    "Jobs": [{"Id": job.Id, "FileName": job.FileName} for job in runningJobs]
                }
            else:
                LoggingService.LogInfo("No running transcoding jobs found to reset", 
                                     "QueueManagementService", "ResetTranscodeQueueRunningJobs")
                return {
                    "Success": True,
                    "Message": "No running transcoding jobs found",
                    "QueueAffectedRows": 0,
                    "AttemptsAffectedRows": 0,
                    "Jobs": []
                }
            
        except Exception as e:
            LoggingService.LogException("Error resetting transcoding queue running jobs", e, 
                                      "QueueManagementService", "ResetTranscodeQueueRunningJobs")
            return {
                "Success": False,
                "ErrorMessage": str(e)
            }
    
    
    def GetRunningJobsCount(self, QueueType: str) -> int:
        """Get count of running jobs for specified queue type."""
        try:
            if QueueType == "TranscodeQueue":
                query = "SELECT COUNT(*) FROM TranscodeQueue WHERE Status = 'Running'"
            elif QueueType == "QualityTestingQueue":
                query = "SELECT COUNT(*) FROM QualityTestingQueue WHERE DateStarted IS NOT NULL AND DateCompleted IS NULL"
            else:
                return 0

            result = self.DatabaseManager.DatabaseService.ExecuteQuery(query)
            return result[0]['count'] if result and len(result) > 0 else 0

        except Exception as e:
            LoggingService.LogException("Error getting running jobs count", e, "QueueManagementService", "GetRunningJobsCount")
            return 0
    
    def GetQueueStatus(self, QueueType: str) -> Dict[str, Any]:
        """Get status summary for specified queue type."""
        try:
            if QueueType == "TranscodeQueue":
                query = """
                SELECT Status, COUNT(*) as Count 
                FROM TranscodeQueue 
                GROUP BY Status
                """
            elif QueueType == "QualityTestingQueue":
                query = """
                SELECT
                    CASE
                        WHEN DateCompleted IS NOT NULL THEN 'Completed'
                        WHEN DateStarted IS NOT NULL THEN 'Running'
                        ELSE 'Pending'
                    END as Status,
                    COUNT(*) as Count
                FROM QualityTestingQueue
                GROUP BY Status
                """
            else:
                return {"Success": False, "ErrorMessage": f"Unknown queue type: {QueueType}"}
            
            results = self.DatabaseManager.DatabaseService.ExecuteQuery(query)
            
            statusSummary = {}
            for row in results:
                statusSummary[row['Status']] = row['Count']
            
            return {
                "Success": True,
                "QueueType": QueueType,
                "StatusSummary": statusSummary,
                "TotalJobs": sum(statusSummary.values())
            }
            
        except Exception as e:
            LoggingService.LogException("Error getting queue status", e, "QueueManagementService", "GetQueueStatus")
            return {
                "Success": False,
                "ErrorMessage": str(e)
            }
