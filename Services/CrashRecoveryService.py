#!/usr/bin/env python3
"""
Crash Recovery Service
Automated crash recovery for transcoding and quality testing jobs
Implements MVVM pattern using MVVM architecture
"""

import json
from typing import Dict, List, Optional
from datetime import datetime
from Services.LoggingService import LoggingService
from Services.ProcessManagementService import ProcessManagementService


class CrashRecoveryService:
    """Service for automated crash recovery of stuck jobs."""
    
    def __init__(self, DatabaseManagerInstance):
        """Initialize the crash recovery service."""
        self.DatabaseManager = DatabaseManagerInstance
        self.ProcessManager = ProcessManagementService()
        LoggingService.LogInfo("CrashRecoveryService initialized", "CrashRecoveryService", "__init__")
    
    def RecoverServiceJobs(self, ServiceName: str) -> Dict:
        """Recover all stuck jobs for a specific service."""
        try:
            LoggingService.LogInfo(f"Starting crash recovery for service: {ServiceName}", "CrashRecoveryService", "RecoverServiceJobs")
            
            # Get all active jobs for this service
            active_jobs = self.DatabaseManager.GetActiveJobsByService(ServiceName)
            
            if not active_jobs:
                LoggingService.LogInfo(f"No active jobs found for service {ServiceName}", "CrashRecoveryService", "RecoverServiceJobs")
                return {
                    "Success": True,
                    "Message": "No active jobs found",
                    "JobsRecovered": 0,
                    "OrphanedProcessesKilled": 0
                }
            
            LoggingService.LogInfo(f"Found {len(active_jobs)} active jobs for service {ServiceName}", "CrashRecoveryService", "RecoverServiceJobs")
            
            jobs_recovered = 0
            orphaned_processes_killed = 0
            recovery_details = []
            
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
                        orphaned_processes_killed += 1
                        LoggingService.LogWarning(f"Killed orphaned process {process_id} for job {job_id}", "CrashRecoveryService", "RecoverServiceJobs")
                    else:
                        recovery_action = "FailedToKillProcess"
                        LoggingService.LogError(f"Failed to kill orphaned process {process_id} for job {job_id}", "CrashRecoveryService", "RecoverServiceJobs")
                else:
                    LoggingService.LogInfo(f"Process {process_id} for job {job_id} is not running", "CrashRecoveryService", "RecoverServiceJobs")
                
                # Reset the job in the appropriate queue
                if self.ResetJobInQueue(queue_id, job_type):
                    jobs_recovered += 1
                    LoggingService.LogInfo(f"Reset job {job_id} in queue (QueueId: {queue_id})", "CrashRecoveryService", "RecoverServiceJobs")
                else:
                    LoggingService.LogError(f"Failed to reset job {job_id} in queue (QueueId: {queue_id})", "CrashRecoveryService", "RecoverServiceJobs")
                
                # Clean up progress records
                self.CleanupProgressRecords(queue_id, job_type)
                
                # Record recovery details
                recovery_details.append({
                    "JobId": job_id,
                    "ProcessId": process_id,
                    "QueueId": queue_id,
                    "JobType": job_type,
                    "RecoveryAction": recovery_action,
                    "ProcessWasOrphaned": process_exists
                })
            
            # Clean up ActiveJobs records
            deleted_active_jobs = self.CleanupActiveJobs(ServiceName)
            
            # Special handling for QualityTestingService: Delete only crashed jobs
            if ServiceName == "QualityTestingService":
                # Only delete jobs that were in ActiveJobs (actually crashed)
                crashed_queue_ids = [detail['QueueId'] for detail in recovery_details]
                if crashed_queue_ids:
                    placeholders = ','.join('?' * len(crashed_queue_ids))
                    delete_query = f"DELETE FROM QualityTestingQueue WHERE Id IN ({placeholders})"
                    deleted_count = self.DatabaseManager.DatabaseService.ExecuteNonQuery(
                        delete_query, crashed_queue_ids
                    )
                    LoggingService.LogInfo(
                        f"Deleted {deleted_count} crashed quality test queue items", 
                        "CrashRecoveryService", "RecoverServiceJobs"
                    )
                else:
                    LoggingService.LogInfo("No crashed quality test queue items to delete", 
                                          "CrashRecoveryService", "RecoverServiceJobs")
            
            # Log recovery summary
            self.LogRecoverySummary(ServiceName, jobs_recovered, orphaned_processes_killed, recovery_details)
            
            result = {
                "Success": True,
                "Message": f"Recovered {jobs_recovered} jobs, killed {orphaned_processes_killed} orphaned processes",
                "JobsRecovered": jobs_recovered,
                "OrphanedProcessesKilled": orphaned_processes_killed,
                "ActiveJobsCleaned": deleted_active_jobs,
                "RecoveryDetails": recovery_details
            }
            
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
            
            # Reset status to Pending and clear DateStarted
            query = """
                UPDATE TranscodeQueue 
                SET Status = 'Pending', DateStarted = NULL 
                WHERE Id IN ({})
            """.format(','.join('?' * len(QueueIds)))
            
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
            """.format(','.join('?' * len(QueueIds)))
            
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
                            SELECT FilePath FROM TranscodeQueue WHERE Id = ?
                        )
                    )
                """
                affected_rows = self.DatabaseManager.DatabaseService.ExecuteNonQuery(query, (QueueId,))
                
            elif JobType == "QualityTest":
                # Clean up QualityTestProgress records
                query = "DELETE FROM QualityTestProgress WHERE TranscodeAttemptId IN (SELECT TranscodeAttemptId FROM QualityTestingQueue WHERE Id = ?)"
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
        """Clean up ActiveJobs records for a service."""
        try:
            query = "DELETE FROM ActiveJobs WHERE ServiceName = ?"
            affected_rows = self.DatabaseManager.DatabaseService.ExecuteNonQuery(query, (ServiceName,))
            
            LoggingService.LogInfo(f"Cleaned up {affected_rows} ActiveJobs records for service {ServiceName}", "CrashRecoveryService", "CleanupActiveJobs")
            return affected_rows
            
        except Exception as e:
            LoggingService.LogException(f"Error cleaning up ActiveJobs for service {ServiceName}", e, "CrashRecoveryService", "CleanupActiveJobs")
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
