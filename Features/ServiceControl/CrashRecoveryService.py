#!/usr/bin/env python3
"""
Crash Recovery Service
Automated crash recovery for transcoding and quality testing jobs
Implements MVVM pattern using MVVM architecture
"""

import json
from typing import Dict, List, Optional
from datetime import datetime
from Core.Logging.LoggingService import LoggingService
from Services.ProcessManagementService import ProcessManagementService


class CrashRecoveryService:
    """Service for automated crash recovery of stuck jobs."""

    def __init__(self, DatabaseManagerInstance, WorkerName: str = None):
        """Initialize the crash recovery service."""
        self.DatabaseManager = DatabaseManagerInstance
        self.ProcessManager = ProcessManagementService()
        self.WorkerName = WorkerName
        LoggingService.LogInfo(f"CrashRecoveryService initialized (worker={WorkerName or 'all'})", "CrashRecoveryService", "__init__")

    def RecoverServiceJobs(self, ServiceName: str) -> Dict:
        """Recover stuck jobs for a specific service, scoped to this worker's jobs only."""
        try:
            LoggingService.LogInfo(f"Starting crash recovery for service: {ServiceName}, worker: {self.WorkerName or 'all'}", "CrashRecoveryService", "RecoverServiceJobs")

            # Get active jobs scoped to this worker (all statuses for recovery)
            active_jobs = self.DatabaseManager.GetActiveJobsByService(ServiceName, WorkerName=self.WorkerName, RunningOnly=False)

            if not active_jobs:
                LoggingService.LogInfo(f"No active jobs found for service {ServiceName}", "CrashRecoveryService", "RecoverServiceJobs")
                return {
                    "Success": True,
                    "Message": "No active jobs found",
                    "JobsRecovered": 0,
                    "OrphanedProcessesKilled": 0
                }

            LoggingService.LogInfo(f"Found {len(active_jobs)} active jobs for service {ServiceName}", "CrashRecoveryService", "RecoverServiceJobs")

            JobsRecovered = 0
            OrphanedProcessesKilled = 0
            RecoveryDetails = []

            # Process each active job
            for job in active_jobs:
                job_id = job.get('Id')
                process_id = job.get('ProcessId')
                queue_id = job.get('QueueId')
                job_type = job.get('JobType')

                LoggingService.LogInfo(f"Processing job {job_id} (PID: {process_id}, QueueId: {queue_id})", "CrashRecoveryService", "RecoverServiceJobs")

                # Check if the process is still running
                process_exists = self.ProcessManager.IsProcessRunning(process_id) if process_id else False

                recovery_action = "ProcessNotFound"
                if process_exists:
                    # Process is orphaned - kill it
                    if self.ProcessManager.KillProcess(process_id, Graceful=True):
                        recovery_action = "OrphanedProcessKilled"
                        OrphanedProcessesKilled += 1
                        LoggingService.LogWarning(f"Killed orphaned process {process_id} for job {job_id}", "CrashRecoveryService", "RecoverServiceJobs")
                    else:
                        recovery_action = "FailedToKillProcess"
                        LoggingService.LogError(f"Failed to kill orphaned process {process_id} for job {job_id}", "CrashRecoveryService", "RecoverServiceJobs")
                else:
                    LoggingService.LogInfo(f"Process {process_id} for job {job_id} is not running", "CrashRecoveryService", "RecoverServiceJobs")

                # Clean up progress records BEFORE resetting/deleting queue records
                self.CleanupProgressRecords(queue_id, job_type)

                # Reset the job in the appropriate queue
                if self.ResetJobInQueue(queue_id, job_type):
                    JobsRecovered += 1
                    LoggingService.LogInfo(f"Reset job {job_id} in queue (QueueId: {queue_id})", "CrashRecoveryService", "RecoverServiceJobs")
                else:
                    LoggingService.LogError(f"Failed to reset job {job_id} in queue (QueueId: {queue_id})", "CrashRecoveryService", "RecoverServiceJobs")

                # Record recovery details
                RecoveryDetails.append({
                    "JobId": job_id,
                    "ProcessId": process_id,
                    "QueueId": queue_id,
                    "JobType": job_type,
                    "RecoveryAction": recovery_action,
                    "ProcessWasOrphaned": process_exists
                })

            # Clean up ActiveJobs records
            DeletedActiveJobs = self.CleanupActiveJobs(ServiceName)

            # Special handling for QualityTestService: Delete only crashed jobs and reset interrupted tests
            if ServiceName == "QualityTestService":
                # Only delete jobs that were in ActiveJobs (actually crashed)
                CrashedQueueIds = [detail['QueueId'] for detail in RecoveryDetails]
                if CrashedQueueIds:
                    Placeholders = ','.join(['%s'] * len(CrashedQueueIds))
                    DeleteQuery = f"DELETE FROM QualityTestingQueue WHERE Id IN ({Placeholders})"
                    DeletedCount = self.DatabaseManager.DatabaseService.ExecuteNonQuery(
                        DeleteQuery, CrashedQueueIds
                    )
                    LoggingService.LogInfo(
                        f"Deleted {DeletedCount} crashed quality test queue items",
                        "CrashRecoveryService", "RecoverServiceJobs"
                    )

                    # Reset failed quality test results for interrupted tests so they can be restarted
                    ResetCount = self.ResetInterruptedQualityTests(CrashedQueueIds)
                else:
                    LoggingService.LogInfo("No crashed quality test queue items to delete",
                                          "CrashRecoveryService", "RecoverServiceJobs")

            # Log recovery summary
            self.LogRecoverySummary(ServiceName, JobsRecovered, OrphanedProcessesKilled, RecoveryDetails)

            result = {
                "Success": True,
                "Message": f"Recovered {JobsRecovered} jobs, killed {OrphanedProcessesKilled} orphaned processes",
                "JobsRecovered": JobsRecovered,
                "OrphanedProcessesKilled": OrphanedProcessesKilled,
                "ActiveJobsCleaned": DeletedActiveJobs,
                "RecoveryDetails": RecoveryDetails
            }

            # Add quality test reset count for QualityTestService
            if ServiceName == "QualityTestService" and 'ResetCount' in locals():
                result["QualityTestsReset"] = ResetCount

            LoggingService.LogInfo(f"Crash recovery completed for {ServiceName}: {result['Message']}", "CrashRecoveryService", "RecoverServiceJobs")
            return result

        except Exception as e:
            error_msg = f"Error during crash recovery for service {ServiceName}: {str(e)}"
            LoggingService.LogException(error_msg, e, "CrashRecoveryService", "RecoverServiceJobs")
            return {
                "Success": False,
                "Message": error_msg,
                "JobsRecovered": 0,
                "OrphanedProcessesKilled": 0
            }

    def ResetJobInQueue(self, QueueId: int, JobType: str) -> bool:
        """Reset a job in the appropriate queue table."""
        try:
            if JobType == "Transcode":
                return self.ResetTranscodeQueue([QueueId])
            elif JobType == "QualityTest":
                return self.ResetQualityTestQueue([QueueId])
            else:
                LoggingService.LogWarning(f"Unknown job type {JobType} for queue ID {QueueId}", "CrashRecoveryService", "ResetJobInQueue")
                return False

        except Exception as e:
            LoggingService.LogException(f"Error resetting job {QueueId} of type {JobType}", e, "CrashRecoveryService", "ResetJobInQueue")
            return False

    def ResetTranscodeQueue(self, QueueIds: List[int]) -> bool:
        """Reset transcode queue jobs to Pending status."""
        try:
            if not QueueIds:
                return True

            # Reset status to Pending and clear ownership
            query = """
                UPDATE TranscodeQueue
                SET Status = 'Pending', DateStarted = NULL, ClaimedBy = NULL, ClaimedAt = NULL
                WHERE Id IN ({})
            """.format(','.join(['%s'] * len(QueueIds)))

            affected_rows = self.DatabaseManager.DatabaseService.ExecuteNonQuery(query, QueueIds)

            LoggingService.LogInfo(f"Reset {affected_rows} transcode queue jobs to Pending", "CrashRecoveryService", "ResetTranscodeQueue")
            return affected_rows > 0

        except Exception as e:
            LoggingService.LogException(f"Error resetting transcode queue jobs {QueueIds}", e, "CrashRecoveryService", "ResetTranscodeQueue")
            return False

    def ResetQualityTestQueue(self, QueueIds: List[int]) -> bool:
        """Delete running quality test queue jobs (they'll be recreated by RecoverMissedQualityTests if needed)."""
        try:
            if not QueueIds:
                return True

            # Delete running jobs from queue (they'll be recreated by RecoverMissedQualityTests if needed)
            query = """
                DELETE FROM QualityTestingQueue
                WHERE Id IN ({})
            """.format(','.join(['%s'] * len(QueueIds)))

            affected_rows = self.DatabaseManager.DatabaseService.ExecuteNonQuery(query, QueueIds)

            LoggingService.LogInfo(f"Deleted {affected_rows} running quality test queue jobs", "CrashRecoveryService", "ResetQualityTestQueue")
            return affected_rows > 0

        except Exception as e:
            LoggingService.LogException(f"Error deleting running quality test queue jobs {QueueIds}", e, "CrashRecoveryService", "ResetQualityTestQueue")
            return False

    def CleanupProgressRecords(self, QueueId: int, JobType: str) -> int:
        """Clean up progress records for a specific job."""
        try:
            if JobType == "Transcode":
                # Clean up TranscodeProgress records
                query = """
                    DELETE FROM TranscodeProgress
                    WHERE TranscodeAttemptId IN (
                        SELECT Id FROM TranscodeAttempts
                        WHERE FilePath IN (
                            SELECT FilePath FROM TranscodeQueue WHERE Id = %s
                        )
                    )
                """
                affected_rows = self.DatabaseManager.DatabaseService.ExecuteNonQuery(query, (QueueId,))

            elif JobType == "QualityTest":
                # Clean up QualityTestProgress records
                query = "DELETE FROM QualityTestProgress WHERE TranscodeAttemptId IN (SELECT TranscodeAttemptId FROM QualityTestingQueue WHERE Id = %s)"
                affected_rows = self.DatabaseManager.DatabaseService.ExecuteNonQuery(query, (QueueId,))

            else:
                LoggingService.LogWarning(f"Unknown job type {JobType} for progress cleanup", "CrashRecoveryService", "CleanupProgressRecords")
                return 0

            if affected_rows > 0:
                LoggingService.LogInfo(f"Cleaned up {affected_rows} progress records for {JobType} job {QueueId}", "CrashRecoveryService", "CleanupProgressRecords")

            return affected_rows

        except Exception as e:
            LoggingService.LogException(f"Error cleaning up progress records for {JobType} job {QueueId}", e, "CrashRecoveryService", "CleanupProgressRecords")
            return 0

    def CleanupActiveJobs(self, ServiceName: str) -> int:
        """Clean up ActiveJobs records for a service, scoped to this worker."""
        try:
            if self.WorkerName:
                query = "DELETE FROM ActiveJobs WHERE ServiceName = %s AND WorkerName = %s"
                affected_rows = self.DatabaseManager.DatabaseService.ExecuteNonQuery(query, (ServiceName, self.WorkerName))
            else:
                query = "DELETE FROM ActiveJobs WHERE ServiceName = %s"
                affected_rows = self.DatabaseManager.DatabaseService.ExecuteNonQuery(query, (ServiceName,))

            LoggingService.LogInfo(f"Cleaned up {affected_rows} ActiveJobs records for service {ServiceName} (worker={self.WorkerName or 'all'})", "CrashRecoveryService", "CleanupActiveJobs")
            return affected_rows

        except Exception as e:
            LoggingService.LogException(f"Error cleaning up ActiveJobs for service {ServiceName}", e, "CrashRecoveryService", "CleanupActiveJobs")
            return 0

    def ResetInterruptedQualityTests(self, CrashedQueueIds: List[int]) -> int:
        """Reset failed quality test results for interrupted tests so they can be retried."""
        try:
            if not CrashedQueueIds:
                return 0

            # Use DatabaseManager method to reset failed quality test results
            AffectedRows = self.DatabaseManager.ResetFailedQualityTestResultsForRetry()

            if AffectedRows > 0:
                LoggingService.LogInfo(
                    f"Reset {AffectedRows} failed quality test results for retry",
                    "CrashRecoveryService", "ResetInterruptedQualityTests"
                )
            else:
                LoggingService.LogInfo(
                    "No failed quality test results found to reset",
                    "CrashRecoveryService", "ResetInterruptedQualityTests"
                )

            return AffectedRows

        except Exception as e:
            LoggingService.LogException(f"Error resetting interrupted quality tests", e, "CrashRecoveryService", "ResetInterruptedQualityTests")
            return 0

    def LogRecoverySummary(self, ServiceName: str, JobsRecovered: int, OrphanedProcessesKilled: int, RecoveryDetails: List[Dict]):
        """Log a summary of the recovery operation to the Logs table."""
        try:
            summary_data = {
                "ServiceName": ServiceName,
                "JobsRecovered": JobsRecovered,
                "OrphanedProcessesKilled": OrphanedProcessesKilled,
                "RecoveryDetails": RecoveryDetails,
                "Timestamp": datetime.now().isoformat()
            }

            # Log the summary
            LoggingService.LogInfo(
                f"Crash recovery summary for {ServiceName}: {JobsRecovered} jobs recovered, {OrphanedProcessesKilled} orphaned processes killed",
                "LogRecoverySummary",
                "CrashRecoveryService"
            )

        except Exception as e:
            LoggingService.LogException(f"Error logging recovery summary for {ServiceName}", e, "CrashRecoveryService", "LogRecoverySummary")

    def GetRecoveryStatistics(self, ServiceName: str) -> Dict:
        """Get statistics about recent recovery operations."""
        try:
            # This could be enhanced to query the Logs table for recovery statistics
            # For now, return basic info
            active_jobs = self.DatabaseManager.GetActiveJobsByService(ServiceName)

            return {
                "ServiceName": ServiceName,
                "CurrentActiveJobs": len(active_jobs),
                "LastRecoveryCheck": datetime.now().isoformat()
            }

        except Exception as e:
            LoggingService.LogException(f"Error getting recovery statistics for {ServiceName}", e, "CrashRecoveryService", "GetRecoveryStatistics")
            return {
                "ServiceName": ServiceName,
                "CurrentActiveJobs": 0,
                "LastRecoveryCheck": None,
                "Error": str(e)
            }
