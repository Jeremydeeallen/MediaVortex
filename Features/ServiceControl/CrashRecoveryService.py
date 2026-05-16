#!/usr/bin/env python3
"""
Crash Recovery Service
Automated crash recovery for transcoding and quality testing jobs
Implements MVVM pattern using MVVM architecture
"""

import json
import os
from typing import Dict, List, Optional
from datetime import datetime, timezone
from Core.Logging.LoggingService import LoggingService
from Core.DateTimeHelpers import ToUtcIsoZ
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

                # Check if the process is still running.
                # Skip the live-process check when the recorded PID matches our own PID:
                # in Docker containers Python runs as PID 1, so a stale ActiveJobs row from a
                # prior container instance always points back at the new process and would
                # cause crash recovery to terminate itself.
                own_pid = os.getpid()
                if process_id and process_id == own_pid:
                    process_exists = False
                    LoggingService.LogInfo(f"Skipping process check for PID {process_id} (matches own PID, treating as dead)", "CrashRecoveryService", "RecoverServiceJobs")
                else:
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

            # Sweep orphaned progress records from prior crashes (SIGKILL, OOM,
            # power loss) where the signal handler never ran and ActiveJobs were
            # cleaned by a previous crash recovery pass without reaching all
            # associated TranscodeProgress rows.
            InProgressFilesCleaned = 0
            PartialReplacementsCompleted = 0
            if ServiceName == "TranscodeService":
                OrphanedCleaned = self.CleanupOrphanedProgressRecords()
                # Worker-lifecycle criteria 11, 12: clean .inprogress artifacts
                # left on disk and complete partial replacements where the
                # `-mv.<ext>` file is in place but the original was not deleted.
                InProgressFilesCleaned, PartialReplacementsCompleted = self._RecoverInProgressArtifacts()
            else:
                OrphanedCleaned = 0

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
                "Message": (
                    f"Recovered {JobsRecovered} jobs, killed {OrphanedProcessesKilled} orphaned processes, "
                    f"cleaned {OrphanedCleaned} orphaned progress records, "
                    f"deleted {InProgressFilesCleaned} .inprogress artifacts, "
                    f"completed {PartialReplacementsCompleted} partial replacements"
                ),
                "JobsRecovered": JobsRecovered,
                "OrphanedProcessesKilled": OrphanedProcessesKilled,
                "ActiveJobsCleaned": DeletedActiveJobs,
                "OrphanedProgressCleaned": OrphanedCleaned,
                "InProgressFilesCleaned": InProgressFilesCleaned,
                "PartialReplacementsCompleted": PartialReplacementsCompleted,
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
                # Mark incomplete attempts as failed with the unified crash/kill
                # reason (worker-lifecycle.feature.md criterion 13).
                fail_query = """
                    UPDATE TranscodeAttempts
                    SET Success = FALSE, CompletedDate = NOW(),
                        ErrorMessage = COALESCE(ErrorMessage, 'worker crashed/restarted')
                    WHERE Success IS NULL
                      AND MediaFileId = (SELECT MediaFileId FROM TranscodeQueue WHERE Id = %s)
                """
                failed_rows = self.DatabaseManager.DatabaseService.ExecuteNonQuery(fail_query, (QueueId,))
                if failed_rows > 0:
                    LoggingService.LogInfo(f"Marked {failed_rows} incomplete transcode attempts as failed for queue {QueueId}", "CrashRecoveryService", "CleanupProgressRecords")

                # Clean up TranscodeProgress records
                query = """
                    DELETE FROM TranscodeProgress
                    WHERE TranscodeAttemptId IN (
                        SELECT Id FROM TranscodeAttempts
                        WHERE MediaFileId = (SELECT MediaFileId FROM TranscodeQueue WHERE Id = %s)
                        AND Success = FALSE
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

    def CleanupOrphanedProgressRecords(self) -> int:
        """Delete TranscodeProgress rows for any non-successful TranscodeAttempt.
        Covers both explicit failures (Success = FALSE) and incomplete attempts
        (Success IS NULL) left by hard kills (SIGKILL, OOM) where no signal handler ran."""
        try:
            # First, mark incomplete attempts as failed so they don't masquerade as in-progress.
            # Exclude attempts with recently-updated progress (active transcodes).
            # worker-lifecycle.feature.md criterion 13: unified crash/kill reason.
            mark_query = """
                UPDATE TranscodeAttempts
                SET Success = FALSE, CompletedDate = NOW(),
                    ErrorMessage = COALESCE(ErrorMessage, 'worker crashed/restarted')
                WHERE Success IS NULL
                  AND Id NOT IN (
                      SELECT TranscodeAttemptId FROM TranscodeProgress
                      WHERE LastProgressUpdate > NOW() - INTERVAL '5 minutes'
                  )
            """
            marked_rows = self.DatabaseManager.DatabaseService.ExecuteNonQuery(mark_query, ())
            if marked_rows > 0:
                LoggingService.LogInfo(f"Marked {marked_rows} incomplete transcode attempts as failed", "CrashRecoveryService", "CleanupOrphanedProgressRecords")

            # Then delete progress rows for all failed attempts
            query = """
                DELETE FROM TranscodeProgress
                WHERE TranscodeAttemptId IN (
                    SELECT Id FROM TranscodeAttempts WHERE Success = FALSE
                )
            """
            affected_rows = self.DatabaseManager.DatabaseService.ExecuteNonQuery(query, ())
            if affected_rows > 0:
                LoggingService.LogInfo(f"Cleaned up {affected_rows} orphaned TranscodeProgress records for failed attempts", "CrashRecoveryService", "CleanupOrphanedProgressRecords")
            return affected_rows
        except Exception as e:
            LoggingService.LogException("Error cleaning up orphaned progress records", e, "CrashRecoveryService", "CleanupOrphanedProgressRecords")
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

    def _RecoverInProgressArtifacts(self) -> tuple:
        """Sweep disk artifacts left by a prior crash/restart for this worker.

        For every TemporaryFilePaths row owned by this worker:
          - If the final (`.inprogress` stripped) file exists AND the original
            source still exists, finalize the partial replacement (rename was
            done, original-delete was not). Criterion 12.
          - Otherwise, delete any leftover `.inprogress` artifact. Criterion 11.

        TemporaryFilePaths rows are deleted on successful FileReplacement, so
        a surviving row implies the attempt did not complete cleanly. After
        cleanup, the surviving TemporaryFilePaths row is left in place; the
        associated TranscodeAttempt is already (or about to be) marked
        Success=FALSE by the standard recovery flow, and a subsequent queue
        re-pop will create a fresh attempt+TFP pair.

        Returns (InProgressFilesDeleted, PartialReplacementsCompleted).
        """
        if not self.WorkerName:
            return 0, 0
        try:
            Query = """
                SELECT tfp.Id AS tfp_id,
                       tfp.LocalSourcePath AS local_source,
                       tfp.LocalOutputPath AS local_output,
                       tfp.OriginalPath AS canonical_original
                FROM TemporaryFilePaths tfp
                JOIN TranscodeAttempts ta ON ta.Id = tfp.TranscodeAttemptId
                WHERE ta.WorkerName = %s
            """
            Rows = self.DatabaseManager.DatabaseService.ExecuteQuery(Query, (self.WorkerName,))
            if not Rows:
                return 0, 0

            InProgressDeleted = 0
            PartialCompleted = 0

            for Row in Rows:
                LocalSource = Row.get('local_source') or ''
                LocalOutput = Row.get('local_output') or ''
                CanonicalOriginal = Row.get('canonical_original') or ''
                if not LocalOutput:
                    continue

                if LocalOutput.endswith('.inprogress'):
                    FinalPath = LocalOutput[:-len('.inprogress')]
                else:
                    FinalPath = LocalOutput

                FinalExists = os.path.exists(FinalPath)
                OriginalExists = LocalSource and os.path.exists(LocalSource)
                InProgressExists = LocalOutput.endswith('.inprogress') and os.path.exists(LocalOutput)

                if FinalExists and OriginalExists and CanonicalOriginal:
                    try:
                        from Features.FileReplacement.FileReplacementBusinessService import FileReplacementBusinessService
                        Frb = FileReplacementBusinessService(self.DatabaseManager, WorkerName=self.WorkerName)
                        FinalizeResult = Frb.FinalizePartialReplacement(
                            OriginalLocalPath=LocalSource,
                            FinalLocalPath=FinalPath,
                            CanonicalOriginalPath=CanonicalOriginal,
                        )
                        if FinalizeResult.get('Success'):
                            PartialCompleted += 1
                            LoggingService.LogWarning(
                                f"Crash recovery: completed partial replacement for {LocalSource} -> {FinalPath}",
                                "CrashRecoveryService", "_RecoverInProgressArtifacts"
                            )
                    except Exception as FinalizeEx:
                        LoggingService.LogException(
                            f"Crash recovery: FinalizePartialReplacement failed for {FinalPath}",
                            FinalizeEx, "CrashRecoveryService", "_RecoverInProgressArtifacts"
                        )

                if InProgressExists:
                    try:
                        os.remove(LocalOutput)
                        InProgressDeleted += 1
                        LoggingService.LogWarning(
                            f"Crash recovery: deleted orphaned .inprogress file {LocalOutput}",
                            "CrashRecoveryService", "_RecoverInProgressArtifacts"
                        )
                    except Exception as RmEx:
                        LoggingService.LogException(
                            f"Crash recovery: could not delete .inprogress {LocalOutput}",
                            RmEx, "CrashRecoveryService", "_RecoverInProgressArtifacts"
                        )

            return InProgressDeleted, PartialCompleted
        except Exception as e:
            LoggingService.LogException(
                "Error during _RecoverInProgressArtifacts",
                e, "CrashRecoveryService", "_RecoverInProgressArtifacts"
            )
            return 0, 0

    def LogRecoverySummary(self, ServiceName: str, JobsRecovered: int, OrphanedProcessesKilled: int, RecoveryDetails: List[Dict]):
        """Log a summary of the recovery operation to the Logs table."""
        try:
            summary_data = {
                "ServiceName": ServiceName,
                "JobsRecovered": JobsRecovered,
                "OrphanedProcessesKilled": OrphanedProcessesKilled,
                "RecoveryDetails": RecoveryDetails,
                "Timestamp": ToUtcIsoZ(datetime.now(timezone.utc))
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
                "LastRecoveryCheck": ToUtcIsoZ(datetime.now(timezone.utc))
            }

        except Exception as e:
            LoggingService.LogException(f"Error getting recovery statistics for {ServiceName}", e, "CrashRecoveryService", "GetRecoveryStatistics")
            return {
                "ServiceName": ServiceName,
                "CurrentActiveJobs": 0,
                "LastRecoveryCheck": None,
                "Error": str(e)
            }
