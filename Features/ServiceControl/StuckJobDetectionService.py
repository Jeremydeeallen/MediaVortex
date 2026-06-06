"""
StuckJobDetectionService
Detects and cleans up stuck transcode jobs where FFmpeg processes have died but database status remains "Running".
"""

import psutil
import re
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from Repositories.DatabaseManager import DatabaseManager
from Core.Logging.LoggingService import LoggingService
from Core.DateTimeHelpers import AsAwareUtc
from Services.ProcessManagementService import ProcessManagementService


class StuckJobDetectionService:
    """Service for detecting and cleaning up stuck transcode jobs."""

    def __init__(self, DatabaseManagerInstance: DatabaseManager = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.ProcessManagementService = ProcessManagementService()

    def DetectAndCleanStuckTranscodeJobs(self) -> Dict[str, Any]:
        """Main entry point for detecting and cleaning up stuck transcode jobs."""
        try:
            LoggingService.LogFunctionEntry("DetectAndCleanStuckTranscodeJobs", "StuckJobDetectionService")

            # Get all running transcode jobs
            runningJobs = self.DatabaseManager.GetTranscodeQueueItemsByStatus("Running")

            if not runningJobs:
                LoggingService.LogInfo("Stuck job detection: No running transcode jobs found",
                                     "StuckJobDetectionService", "DetectAndCleanStuckTranscodeJobs")
                return {
                    "Success": True,
                    "Message": "No running jobs to check",
                    "StuckJobsFound": 0,
                    "JobsCleaned": 0
                }

            LoggingService.LogInfo(f"Stuck job detection started - checking {len(runningJobs)} running jobs",
                                 "StuckJobDetectionService", "DetectAndCleanStuckTranscodeJobs")

            stuckJobs = []
            cleanedJobs = []

            for job in runningJobs:
                try:
                    # Check if this job is stuck
                    isStuck, reason = self.IsJobStuck(job)

                    if isStuck:
                        LoggingService.LogWarning(f"Stuck job detected: Job ID {job.Id}, File: {job.FileName}, Reason: {reason}",
                                                "StuckJobDetectionService", "DetectAndCleanStuckTranscodeJobs")

                        stuckJobs.append({
                            "JobId": job.Id,
                            "FileName": job.FileName,
                            "FilePath": job.FilePath,
                            "Reason": reason
                        })

                        # Clean up the stuck job
                        cleanupResult = self.CleanupStuckJob(job.Id, reason)
                        if cleanupResult.get("Success", False):
                            cleanedJobs.append(job.Id)
                            LoggingService.LogInfo(f"Cleaned up stuck job: Job ID {job.Id}, File: {job.FileName}",
                                                 "StuckJobDetectionService", "DetectAndCleanStuckTranscodeJobs")
                        else:
                            LoggingService.LogError(f"Failed to clean up stuck job: Job ID {job.Id}, Error: {cleanupResult.get('ErrorMessage', 'Unknown error')}",
                                                   "StuckJobDetectionService", "DetectAndCleanStuckTranscodeJobs")
                    else:
                        LoggingService.LogInfo(f"Job {job.Id} is healthy - process still running",
                                             "StuckJobDetectionService", "DetectAndCleanStuckTranscodeJobs")

                except Exception as e:
                    LoggingService.LogException(f"Error checking job {job.Id} for stuck status", e,
                                             "StuckJobDetectionService", "DetectAndCleanStuckTranscodeJobs")

            # Log summary
            LoggingService.LogInfo(f"Stuck job detection completed - found {len(stuckJobs)} stuck jobs, cleaned {len(cleanedJobs)} jobs",
                                 "StuckJobDetectionService", "DetectAndCleanStuckTranscodeJobs")

            return {
                "Success": True,
                "Message": f"Detection completed - found {len(stuckJobs)} stuck jobs, cleaned {len(cleanedJobs)} jobs",
                "StuckJobsFound": len(stuckJobs),
                "JobsCleaned": len(cleanedJobs),
                "StuckJobs": stuckJobs,
                "CleanedJobs": cleanedJobs
            }

        except Exception as e:
            errorMsg = f"Exception during stuck job detection: {str(e)}"
            LoggingService.LogException(errorMsg, e, "StuckJobDetectionService", "DetectAndCleanStuckTranscodeJobs")
            return {
                "Success": False,
                "ErrorMessage": errorMsg,
                "StuckJobsFound": 0,
                "JobsCleaned": 0
            }

    # Default frame-stagnation threshold in minutes if SystemSetting is missing.
    # Lowered from 15 to 5 (stuck-job-detection.feature.md criterion 3); SVT-AV1
    # at observed FPS rates never goes >30s without a frame advance during a
    # normal encode, so 5 min is well clear of any legitimate transient pause.
    # The actual threshold is read from SystemSettings.FrozenProgressThresholdMin
    # at every detection cycle (criterion 4) so the operator can tune at runtime.
    FROZEN_PROGRESS_THRESHOLD_MINUTES = 5

    def _GetFrozenProgressThresholdMin(self) -> int:
        """Read FrozenProgressThresholdMin from SystemSettings each cycle.

        Falls back to FROZEN_PROGRESS_THRESHOLD_MINUTES when the setting is
        missing or unparseable. No caching -- per-cycle read so operator
        changes take effect without restart.
        """
        try:
            from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
            value = SystemSettingsRepository().GetSystemSetting('FrozenProgressThresholdMin')
            if value is None:
                return self.FROZEN_PROGRESS_THRESHOLD_MINUTES
            return max(1, int(value))
        except Exception:
            return self.FROZEN_PROGRESS_THRESHOLD_MINUTES

    # Quality test queue jobs sitting with DateStarted=NULL longer than this are stale (never picked up)
    STALE_QUALITY_TEST_THRESHOLD_MINUTES = 60

    # If worker heartbeat is older than this many minutes, consider the worker offline
    WORKER_HEARTBEAT_STALE_MINUTES = 5

    # ScanJobs in Status='Running' with LastUpdated older than this are stuck.
    # Default 15 min: a healthy scan ticks LastUpdated every few seconds during
    # the walk; 15 min is well clear of any legitimate transient pause. Operator
    # override via SystemSettings('StuckScanThresholdMin').
    STUCK_SCAN_THRESHOLD_MINUTES = 15

    def _GetStuckScanThresholdMin(self) -> int:
        """Read StuckScanThresholdMin from SystemSettings each cycle (no cache)."""
        try:
            from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
            value = SystemSettingsRepository().GetSystemSetting('StuckScanThresholdMin')
            if value is None:
                return self.STUCK_SCAN_THRESHOLD_MINUTES
            return max(1, int(value))
        except Exception:
            return self.STUCK_SCAN_THRESHOLD_MINUTES

    def IsJobStuck(self, Job) -> tuple[bool, str]:
        """Check if a specific job is stuck using three-tier detection:
        1. Worker heartbeat (distributed) - if the owning worker is offline
        2. Progress stagnation - if no frame advance for 15 minutes
        3. Local PID check - if the job is owned by this machine"""
        try:
            import socket

            # Get active job record for this transcode job
            activeJobs = self.DatabaseManager.GetActiveJobsByService("TranscodeService")

            # Find the active job for this queue item
            relevantActiveJob = None
            for activeJob in activeJobs:
                if activeJob.get('QueueId') == Job.Id:
                    relevantActiveJob = activeJob
                    break

            if not relevantActiveJob:
                # No active job record found - this could be stuck
                return True, "No ActiveJob record found for running transcode job"

            # Tier 1: Worker heartbeat check (for distributed workers)
            JobWorkerName = relevantActiveJob.get('WorkerName')
            if JobWorkerName:
                isWorkerOffline, workerReason = self._IsWorkerOffline(JobWorkerName)
                if isWorkerOffline:
                    return True, f"Worker '{JobWorkerName}' is offline: {workerReason}"

            workerPid = relevantActiveJob.get('ProcessId')  # Python worker PID -- never killed
            ffmpegPid = relevantActiveJob.get('FFmpegPid')   # FFmpeg subprocess PID -- correct kill target

            # Tier 2: Progress stagnation check (works across all machines).
            # Run BEFORE Tier 3 so a stalled FFmpeg with a still-alive PID is
            # caught regardless of locality.
            isFrozen, frozenReason = self._IsJobFrozen(Job)
            if isFrozen:
                return True, frozenReason

            # Tier 3: FFmpeg-PID liveness (local jobs only).
            # The "no FFmpeg processes on system" heuristic was REMOVED in
            # stuck-job-detection.feature.md criterion D1: it false-positived
            # during the gap between job claim and FFmpeg spawn, self-killing
            # the worker on 2026-05-09 (Incident 2 in the feature doc).
            LocalHostname = socket.gethostname()
            IsLocalJob = (not JobWorkerName) or (JobWorkerName == LocalHostname)

            if IsLocalJob:
                if ffmpegPid is None:
                    # FFmpeg has not started yet (or row predates this feature).
                    # Defer to Tier 2; do NOT flag stuck on PID-absence alone.
                    return False, "FFmpegPid not yet recorded -- relying on frame-stagnation check"

                # Verify the recorded FFmpegPid is alive AND still an FFmpeg
                # process by name (D1). Anything else means FFmpeg exited and
                # the PID may have been reused by an unrelated process.
                actualName = self._GetProcessName(ffmpegPid)
                if actualName is None:
                    return True, f"FFmpeg PID {ffmpegPid} recorded for job {Job.Id} is no longer alive"
                if not self._IsFFmpegProcessName(actualName):
                    return True, f"FFmpeg PID {ffmpegPid} recorded for job {Job.Id} is no longer alive (process name was '{actualName}')"

            return False, "Process is alive and making progress"

        except Exception as e:
            LoggingService.LogException(f"Error checking if job {Job.Id} is stuck", e,
                                     "StuckJobDetectionService", "IsJobStuck")
            # If we can't determine, assume it's not stuck to be safe
            return False, f"Error checking process status: {str(e)}"

    def _IsWorkerOffline(self, WorkerName: str) -> tuple[bool, str]:
        """Check if a worker's heartbeat is stale (indicating it's offline/crashed)."""
        try:
            WorkerConfig = self.WorkersRepository.GetWorkerConfig(WorkerName)
            if not WorkerConfig:
                # No worker record found - might be a legacy job from before distributed mode
                return False, "No worker record (legacy job)"

            LastHeartbeat = WorkerConfig.get('LastHeartbeat') or WorkerConfig.get('lastheartbeat')
            WorkerStatus = WorkerConfig.get('Status') or WorkerConfig.get('status')

            # If worker explicitly marked Paused, it won't pick up new jobs
            if WorkerStatus and WorkerStatus.lower() == 'paused':
                return True, "Worker status is Paused"

            if not LastHeartbeat:
                return False, "No heartbeat recorded yet"

            # Parse heartbeat timestamp
            if isinstance(LastHeartbeat, str):
                LastHeartbeat = datetime.strptime(LastHeartbeat, "%Y-%m-%d %H:%M:%S")

            MinutesSinceHeartbeat = (datetime.now(timezone.utc) - AsAwareUtc(LastHeartbeat)).total_seconds() / 60.0

            if MinutesSinceHeartbeat >= self.WORKER_HEARTBEAT_STALE_MINUTES:
                return True, f"Last heartbeat was {MinutesSinceHeartbeat:.1f} minutes ago (threshold: {self.WORKER_HEARTBEAT_STALE_MINUTES}min)"

            return False, f"Heartbeat {MinutesSinceHeartbeat:.1f} minutes ago (healthy)"

        except Exception as e:
            LoggingService.LogException(f"Error checking worker heartbeat for {WorkerName}", e,
                                     "StuckJobDetectionService", "_IsWorkerOffline")
            return False, f"Error checking heartbeat: {str(e)}"

    # directive: path-schema-migration | # see path.S1
    def _IsJobFrozen(self, Job) -> tuple[bool, str]:
        """Frozen-progress check using LastFrameAdvance on the in-flight TranscodeAttempt."""
        try:
            # Join TranscodeProgress -> TranscodeAttempts on typed-pair (StorageRootId, RelativePath)
            query = (
                "SELECT tp.LastFrameAdvance, tp.LastProgressUpdate, tp.ProgressPercent, tp.CurrentFPS "
                "FROM TranscodeProgress tp "
                "INNER JOIN TranscodeAttempts ta ON tp.TranscodeAttemptId = ta.Id "
                "WHERE ta.StorageRootId = %s AND ta.RelativePath = %s AND ta.Success IS NULL "
                "ORDER BY tp.LastProgressUpdate DESC "
                "LIMIT 1"
            )
            rows = self.DatabaseManager.DatabaseService.ExecuteQuery(query, (Job.StorageRootId, Job.RelativePath))

            if not rows:
                # No progress records yet - job may still be starting up, not frozen
                return False, "No progress records found (job may be starting)"

            row = rows[0]
            # Prefer LastFrameAdvance; fall back to LastProgressUpdate for backward compat
            lastUpdateValue = row.get('LastFrameAdvance') or row.get('LastProgressUpdate')
            progressPercent = row['ProgressPercent']
            currentFPS = row['CurrentFPS']

            if not lastUpdateValue:
                return False, "No LastFrameAdvance/LastProgressUpdate timestamp available"

            # Parse the timestamp and check staleness
            # PostgreSQL returns datetime objects directly, but handle string format as fallback
            if isinstance(lastUpdateValue, str):
                lastUpdate = datetime.strptime(lastUpdateValue, "%Y-%m-%d %H:%M:%S")
            else:
                lastUpdate = lastUpdateValue
            minutesSinceUpdate = (datetime.now(timezone.utc) - AsAwareUtc(lastUpdate)).total_seconds() / 60.0

            thresholdMin = self._GetFrozenProgressThresholdMin()
            if minutesSinceUpdate >= thresholdMin:
                return True, (
                    f"FFmpeg process is alive but frozen - no frame advance for {minutesSinceUpdate:.1f} minutes "
                    f"(threshold: {thresholdMin}min). "
                    f"Last progress: {progressPercent:.1f}%, FPS: {currentFPS}"
                )

            return False, f"Frame advanced {minutesSinceUpdate:.1f} minutes ago"

        except Exception as e:
            LoggingService.LogException(f"Error checking if job {Job.Id} is frozen", e,
                                     "StuckJobDetectionService", "_IsJobFrozen")
            return False, f"Error checking progress stagnation: {str(e)}"

    def IsProcessAlive(self, ProcessId: int) -> bool:
        """Check if the worker process that owns a job is still alive.
        ActiveJob stores the Python worker PID (os.getpid()), not the FFmpeg PID.
        PID reuse is guarded by Tier 1 (heartbeat staleness within 5 minutes)."""
        try:
            if not ProcessId or ProcessId <= 0:
                return False

            process = psutil.Process(ProcessId)
            return process.is_running()

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return False
        except Exception as e:
            LoggingService.LogException(f"Error checking if process {ProcessId} is alive", e,
                                      "StuckJobDetectionService", "IsProcessAlive")
            return False

    def _GetProcessName(self, ProcessId: int) -> Optional[str]:
        """Return the process name for a PID, or None if the process is not alive.

        Used by stuck-job detection and cleanup to verify a kill target is
        actually an FFmpeg/shell process before sending SIGTERM. Never returns
        None for transient failures -- those raise so the caller can decide.
        """
        try:
            if not ProcessId or ProcessId <= 0:
                return None
            return psutil.Process(ProcessId).name()
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            return None
        except psutil.AccessDenied:
            # Process exists but we can't read its name. Treat as "alive but
            # opaque" -- safer than assuming dead.
            return "<access-denied>"

    def _IsFFmpegProcessName(self, Name: Optional[str]) -> bool:
        """True if Name looks like an FFmpeg or its shell parent.

        On Windows with shell=True, Popen.pid is cmd.exe (whose only purpose
        is to spawn ffmpeg.exe). Treat both as legitimate FFmpeg-related kill
        targets. python/python.exe is NEVER a legitimate target -- that's the
        worker process.
        """
        if not Name:
            return False
        n = Name.lower()
        if 'python' in n:
            return False
        return ('ffmpeg' in n) or n in ('cmd.exe', 'cmd', 'sh', 'bash')

    def CleanupStuckJob(self, QueueId: int, Reason: str) -> Dict[str, Any]:
        """Clean up a stuck job by killing the hung FFmpeg process and resetting its status."""
        try:
            LoggingService.LogFunctionEntry("CleanupStuckJob", "StuckJobDetectionService", QueueId, Reason)

            # Get job details for logging
            jobDetails = self.DatabaseManager.GetTranscodeQueueItemById(QueueId)
            if not jobDetails:
                return {
                    "Success": False,
                    "ErrorMessage": f"TranscodeQueue job {QueueId} not found"
                }

            # Kill the hung FFmpeg process before resetting DB records.
            # Three guards to prevent killing the wrong target:
            #   1. FFmpegPid (NEW column, criterion 6) -- not ProcessId, which
            #      is the Python worker PID and must never be killed.
            #   2. Host-locality (criterion 9) -- only kill PIDs on this host.
            #   3. Process name (D1) -- target must be an FFmpeg-or-shell, not
            #      python/python.exe.
            try:
                import socket as _socket
                LocalHostname = _socket.gethostname()
                activeJobs = self.DatabaseManager.GetActiveJobsByService("TranscodeService")
                for activeJob in activeJobs:
                    if activeJob.get('QueueId') != QueueId:
                        continue

                    jobWorkerName = activeJob.get('WorkerName')
                    ffmpegPid = activeJob.get('FFmpegPid')

                    # Host-locality guard: cross-host jobs get DB-only cleanup.
                    if jobWorkerName and jobWorkerName != LocalHostname:
                        LoggingService.LogInfo(
                            f"Skipping kill for stuck job {QueueId}: owned by '{jobWorkerName}', "
                            f"this host is '{LocalHostname}'. DB cleanup will still run.",
                            "StuckJobDetectionService", "CleanupStuckJob"
                        )
                        break

                    # FFmpegPid path: target the recorded subprocess PID.
                    killTarget = None
                    if ffmpegPid:
                        targetName = self._GetProcessName(ffmpegPid)
                        if targetName is None:
                            LoggingService.LogInfo(
                                f"Stuck job {QueueId}: FFmpegPid {ffmpegPid} already gone, skipping kill",
                                "StuckJobDetectionService", "CleanupStuckJob"
                            )
                        elif self._IsFFmpegProcessName(targetName):
                            killTarget = ffmpegPid
                        else:
                            # Recorded PID is alive but is NOT FFmpeg (worker
                            # PID, or a reused PID belonging to something
                            # unrelated). This is exactly the I9-2024
                            # self-kill scenario; refuse to kill.
                            LoggingService.LogWarning(
                                f"Stuck job {QueueId}: refusing to kill PID {ffmpegPid} "
                                f"-- name '{targetName}' is not an FFmpeg/shell process. "
                                f"DB cleanup will still run.",
                                "StuckJobDetectionService", "CleanupStuckJob"
                            )

                    # Legacy fallback: ActiveJobs row from before FFmpegPid
                    # column existed. Find FFmpeg children of the worker PID.
                    if killTarget is None and ffmpegPid is None:
                        workerPid = activeJob.get('ProcessId')
                        if workerPid and self.IsProcessAlive(workerPid):
                            try:
                                workerProc = psutil.Process(workerPid)
                                for child in workerProc.children(recursive=True):
                                    childName = child.name() or ''
                                    if self._IsFFmpegProcessName(childName) and 'ffmpeg' in childName.lower():
                                        killTarget = child.pid
                                        LoggingService.LogInfo(
                                            f"Stuck job {QueueId}: legacy row, found FFmpeg child {killTarget} of worker {workerPid}",
                                            "StuckJobDetectionService", "CleanupStuckJob"
                                        )
                                        break
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass

                    if killTarget:
                        # Final pre-flight name check (paranoia: PID could have
                        # changed identity since we read it).
                        finalName = self._GetProcessName(killTarget)
                        if not self._IsFFmpegProcessName(finalName):
                            LoggingService.LogWarning(
                                f"Stuck job {QueueId}: final name check failed for PID {killTarget} "
                                f"(name='{finalName}'), skipping kill",
                                "StuckJobDetectionService", "CleanupStuckJob"
                            )
                        else:
                            LoggingService.LogInfo(
                                f"Killing FFmpeg PID {killTarget} (name='{finalName}') for stuck job {QueueId}",
                                "StuckJobDetectionService", "CleanupStuckJob"
                            )
                            self.ProcessManagementService.KillProcess(killTarget, Graceful=True)
                    break
            except Exception as killEx:
                LoggingService.LogException(f"Error killing FFmpeg process for stuck job {QueueId} (continuing with DB cleanup)", killEx,
                                          "StuckJobDetectionService", "CleanupStuckJob")

            # Each ExecuteNonQuery auto-commits on its own connection
            # 1. Reset TranscodeQueue status to Pending and clear ownership
            queueUpdateQuery = """
            UPDATE TranscodeQueue
            SET Status = 'Pending', DateStarted = NULL, ClaimedBy = NULL, ClaimedAt = NULL
            WHERE Id = %s
            """
            queueAffected = self.DatabaseManager.DatabaseService.ExecuteNonQuery(queueUpdateQuery, (QueueId,))

            # 2. Update TranscodeAttempts to mark as failed
            attemptUpdateQuery = """
            UPDATE TranscodeAttempts
            SET Success = FALSE, ErrorMessage = %s
            WHERE MediaFileId = %s AND Success IS NULL
            """
            attemptAffected = self.DatabaseManager.DatabaseService.ExecuteNonQuery(
                attemptUpdateQuery,
                (f"FFmpeg process died unexpectedly - cleaned by StuckJobDetectionService: {Reason}", jobDetails.MediaFileId)
            )

            # 3. Delete TranscodeProgress records
            progressDeleteQuery = """
            DELETE FROM TranscodeProgress
            WHERE TranscodeAttemptId IN (
                SELECT Id FROM TranscodeAttempts
                WHERE MediaFileId = %s AND Success = FALSE
            )
            """
            progressAffected = self.DatabaseManager.DatabaseService.ExecuteNonQuery(progressDeleteQuery, (jobDetails.MediaFileId,))

            # 4. Complete ActiveJobs records for this service
            activeJobUpdateQuery = """
            UPDATE ActiveJobs
            SET Status = 'Failed', UpdatedAt = NOW()
            WHERE ServiceName = 'TranscodeService' AND QueueId = %s
            """
            activeJobAffected = self.DatabaseManager.DatabaseService.ExecuteNonQuery(
                activeJobUpdateQuery,
                (QueueId,)
            )

            # Log cleanup details
            LoggingService.LogInfo(f"Cleaned up stuck job {QueueId}: Queue={queueAffected}, Attempts={attemptAffected}, Progress={progressAffected}, ActiveJobs={activeJobAffected}",
                                 "StuckJobDetectionService", "CleanupStuckJob")

            return {
                "Success": True,
                "Message": f"Successfully cleaned up stuck job {QueueId}",
                "QueueAffected": queueAffected,
                "AttemptsAffected": attemptAffected,
                "ProgressAffected": progressAffected,
                "ActiveJobsAffected": activeJobAffected
            }

        except Exception as e:
            errorMsg = f"Exception cleaning up stuck job {QueueId}: {str(e)}"
            LoggingService.LogException(errorMsg, e, "StuckJobDetectionService", "CleanupStuckJob")
            return {
                "Success": False,
                "ErrorMessage": errorMsg
            }

    def GetStuckJobSummary(self) -> Dict[str, Any]:
        """Get a summary of potentially stuck jobs without cleaning them up."""
        try:
            runningJobs = self.DatabaseManager.GetTranscodeQueueItemsByStatus("Running")

            if not runningJobs:
                return {
                    "Success": True,
                    "RunningJobsCount": 0,
                    "StuckJobsCount": 0,
                    "HealthyJobsCount": 0
                }

            stuckCount = 0
            healthyCount = 0

            for job in runningJobs:
                isStuck, _ = self.IsJobStuck(job)
                if isStuck:
                    stuckCount += 1
                else:
                    healthyCount += 1

            return {
                "Success": True,
                "RunningJobsCount": len(runningJobs),
                "StuckJobsCount": stuckCount,
                "HealthyJobsCount": healthyCount
            }

        except Exception as e:
            LoggingService.LogException("Error getting stuck job summary", e,
                                      "StuckJobDetectionService", "GetStuckJobSummary")
            return {
                "Success": False,
                "ErrorMessage": str(e)
            }

    def DetectAndCleanStaleQualityTestJobs(self) -> Dict[str, Any]:
        """Detect and delete quality test queue jobs that were never started (DateStarted=NULL) and are older than the threshold."""
        try:
            LoggingService.LogFunctionEntry("DetectAndCleanStaleQualityTestJobs", "StuckJobDetectionService")

            # Find never-started jobs older than the threshold
            query = """
                SELECT Id, OriginalFilePath, DateAdded
                FROM QualityTestingQueue
                WHERE DateStarted IS NULL
                  AND DateAdded < NOW() - INTERVAL '%s minutes'
            """ % self.STALE_QUALITY_TEST_THRESHOLD_MINUTES
            staleRows = self.DatabaseManager.DatabaseService.ExecuteQuery(query)

            if not staleRows:
                LoggingService.LogInfo("Stale quality test detection: No stale pending jobs found",
                                     "StuckJobDetectionService", "DetectAndCleanStaleQualityTestJobs")
                return {
                    "Success": True,
                    "Message": "No stale pending quality test jobs found",
                    "StaleJobsFound": 0,
                    "StaleJobsCleaned": 0,
                    "StaleJobs": []
                }

            LoggingService.LogInfo(f"Stale quality test detection: Found {len(staleRows)} stale pending jobs",
                                 "StuckJobDetectionService", "DetectAndCleanStaleQualityTestJobs")

            staleJobs = []
            cleanedCount = 0

            for row in staleRows:
                jobId = row['id']
                filePath = row.get('originalfilepath', 'Unknown')
                dateAdded = row.get('dateadded')
                ageHours = 0
                if dateAdded:
                    ageHours = (datetime.now(timezone.utc) - AsAwareUtc(dateAdded)).total_seconds() / 3600.0

                LoggingService.LogWarning(
                    f"Stale quality test job detected: Id={jobId}, File={filePath}, DateAdded={dateAdded}, Age={ageHours:.1f} hours",
                    "StuckJobDetectionService", "DetectAndCleanStaleQualityTestJobs")

                # Delete the stale row
                deleteQuery = "DELETE FROM QualityTestingQueue WHERE Id = %s"
                affected = self.DatabaseManager.DatabaseService.ExecuteNonQuery(deleteQuery, (jobId,))

                if affected > 0:
                    cleanedCount += 1
                    LoggingService.LogInfo(f"Deleted stale quality test job {jobId} (age: {ageHours:.1f} hours)",
                                         "StuckJobDetectionService", "DetectAndCleanStaleQualityTestJobs")

                staleJobs.append({
                    "JobId": jobId,
                    "OriginalFilePath": filePath,
                    "DateAdded": str(dateAdded) if dateAdded else None,
                    "AgeHours": round(ageHours, 1)
                })

            LoggingService.LogInfo(f"Stale quality test detection completed - found {len(staleJobs)}, cleaned {cleanedCount}",
                                 "StuckJobDetectionService", "DetectAndCleanStaleQualityTestJobs")

            return {
                "Success": True,
                "Message": f"Stale detection completed - found {len(staleJobs)} stale jobs, cleaned {cleanedCount}",
                "StaleJobsFound": len(staleJobs),
                "StaleJobsCleaned": cleanedCount,
                "StaleJobs": staleJobs
            }

        except Exception as e:
            errorMsg = f"Exception during stale quality test job detection: {str(e)}"
            LoggingService.LogException(errorMsg, e, "StuckJobDetectionService", "DetectAndCleanStaleQualityTestJobs")
            return {
                "Success": False,
                "ErrorMessage": errorMsg,
                "StaleJobsFound": 0,
                "StaleJobsCleaned": 0,
                "StaleJobs": []
            }

    def DetectAndCleanStuckQualityTestJobs(self) -> Dict[str, Any]:
        """Detect and clean up stuck quality test jobs where FFmpeg VMAF processes have died."""
        try:
            LoggingService.LogFunctionEntry("DetectAndCleanStuckQualityTestJobs", "StuckJobDetectionService")

            # First, detect and clean stale pending jobs (never started)
            staleResult = self.DetectAndCleanStaleQualityTestJobs()

            # Get all running quality test jobs
            # For quality test jobs, we need to get them differently since there's no status filter method
            qualityTestQueue = self.DatabaseManager.GetQualityTestQueue()
            activeQualityJobs = self.DatabaseManager.GetActiveJobsByService("QualityTest")

            # Filter quality test jobs that are actually running (have active jobs)
            runningJobs = []
            for activeJob in activeQualityJobs:
                queueId = activeJob.get('QueueId')
                if queueId:
                    # Find the corresponding queue item
                    for queueItem in qualityTestQueue:
                        if queueItem['Id'] == queueId:
                            runningJobs.append(queueItem)
                            break

            if not runningJobs:
                LoggingService.LogInfo("Stuck quality test job detection: No running quality test jobs found",
                                     "StuckJobDetectionService", "DetectAndCleanStuckQualityTestJobs")
                return {
                    "Success": True,
                    "Message": "No running quality test jobs to check",
                    "StuckJobsFound": 0,
                    "JobsCleaned": 0
                }

            LoggingService.LogInfo(f"Stuck quality test job detection started - checking {len(runningJobs)} running jobs",
                                 "StuckJobDetectionService", "DetectAndCleanStuckQualityTestJobs")

            stuckJobs = []
            cleanedJobs = []

            for job in runningJobs:
                try:
                    # Check if this quality test job is stuck
                    isStuck, reason = self.IsQualityTestJobStuck(job)

                    if isStuck:
                        LoggingService.LogWarning(f"Stuck quality test job detected: Job ID {job['Id']}, File: {job.get('OriginalFilePath', 'Unknown')}, Reason: {reason}",
                                                "StuckJobDetectionService", "DetectAndCleanStuckQualityTestJobs")

                        stuckJobs.append({
                            "JobId": job['Id'],
                            "OriginalFilePath": job.get('OriginalFilePath', 'Unknown'),
                            "Reason": reason
                        })

                        # Clean up the stuck quality test job
                        cleanupResult = self.CleanupStuckQualityTestJob(job['Id'], reason)
                        if cleanupResult.get("Success", False):
                            cleanedJobs.append(job['Id'])
                            LoggingService.LogInfo(f"Cleaned up stuck quality test job: Job ID {job['Id']}",
                                                 "StuckJobDetectionService", "DetectAndCleanStuckQualityTestJobs")
                        else:
                            LoggingService.LogError(f"Failed to clean up stuck quality test job: Job ID {job['Id']}, Error: {cleanupResult.get('ErrorMessage', 'Unknown error')}",
                                                   "StuckJobDetectionService", "DetectAndCleanStuckQualityTestJobs")
                    else:
                        LoggingService.LogInfo(f"Quality test job {job['Id']} is healthy - process still running",
                                             "StuckJobDetectionService", "DetectAndCleanStuckQualityTestJobs")

                except Exception as e:
                    LoggingService.LogException(f"Error checking quality test job {job['Id']} for stuck status", e,
                                             "StuckJobDetectionService", "DetectAndCleanStuckQualityTestJobs")

            # Log summary
            LoggingService.LogInfo(f"Stuck quality test job detection completed - found {len(stuckJobs)} stuck jobs, cleaned {len(cleanedJobs)} jobs",
                                 "StuckJobDetectionService", "DetectAndCleanStuckQualityTestJobs")

            staleJobsFound = staleResult.get("StaleJobsFound", 0)
            staleJobsCleaned = staleResult.get("StaleJobsCleaned", 0)

            return {
                "Success": True,
                "Message": f"Quality test detection completed - found {len(stuckJobs)} stuck jobs, cleaned {len(cleanedJobs)} jobs, found {staleJobsFound} stale pending jobs, cleaned {staleJobsCleaned}",
                "StuckJobsFound": len(stuckJobs),
                "JobsCleaned": len(cleanedJobs),
                "StuckJobs": stuckJobs,
                "CleanedJobs": cleanedJobs,
                "StaleJobsFound": staleJobsFound,
                "StaleJobsCleaned": staleJobsCleaned,
                "StaleJobs": staleResult.get("StaleJobs", [])
            }

        except Exception as e:
            errorMsg = f"Exception during stuck quality test job detection: {str(e)}"
            LoggingService.LogException(errorMsg, e, "StuckJobDetectionService", "DetectAndCleanStuckQualityTestJobs")
            return {
                "Success": False,
                "ErrorMessage": errorMsg,
                "StuckJobsFound": 0,
                "JobsCleaned": 0,
                "StaleJobsFound": 0,
                "StaleJobsCleaned": 0
            }

    def IsQualityTestJobStuck(self, Job) -> tuple[bool, str]:
        """Check if a specific quality test job is stuck by verifying if the FFmpeg process is still alive."""
        try:
            # Get active job record for this quality test job
            activeJobs = self.DatabaseManager.GetActiveJobsByService("QualityTest")

            # Find the active job for this queue item
            relevantActiveJob = None
            for activeJob in activeJobs:
                if activeJob.get('QueueId') == Job['Id']:
                    relevantActiveJob = activeJob
                    break

            if not relevantActiveJob:
                # No active job record found - this could be stuck
                return True, "No ActiveJob record found for running quality test job"

            processId = relevantActiveJob.get('ProcessId')
            if not processId:
                # No process ID recorded yet - might be stuck
                return True, "No ProcessId recorded in ActiveJob"

            # Check if the process is still alive
            isAlive = self.IsProcessAlive(processId)

            if not isAlive:
                return True, f"FFmpeg VMAF process {processId} not found (process died)"
            else:
                return False, "Process is alive and running"

        except Exception as e:
            LoggingService.LogException(f"Error checking if quality test job {Job['Id']} is stuck", e,
                                     "StuckJobDetectionService", "IsQualityTestJobStuck")
            # If we can't determine, assume it's not stuck to be safe
            return False, f"Error checking process status: {str(e)}"

    def CleanupStuckQualityTestJob(self, QueueId: int, Reason: str) -> Dict[str, Any]:
        """Clean up a stuck quality test job by resetting its status and cleaning up related records."""
        try:
            LoggingService.LogFunctionEntry("CleanupStuckQualityTestJob", "StuckJobDetectionService", QueueId, Reason)

            # Get job details for logging
            jobDetails = self.DatabaseManager.GetQualityTestJob(QueueId)
            if not jobDetails:
                return {
                    "Success": False,
                    "ErrorMessage": f"QualityTestingQueue job {QueueId} not found"
                }

            # Start database transaction for atomic cleanup
            self.DatabaseManager.DatabaseService.BeginTransaction()

            try:
                # 1. Delete the stuck job from QualityTestingQueue (no Status column exists)
                queueDeleteQuery = """
                DELETE FROM QualityTestingQueue
                WHERE Id = %s
                """
                queueAffected = self.DatabaseManager.DatabaseService.ExecuteNonQuery(queueDeleteQuery, (QueueId,))

                # 2. Update QualityTestResults to mark as failed (using TranscodeAttemptId from QualityTestingQueue)
                # First get the TranscodeAttemptId for this queue item
                attemptIdQuery = "SELECT TranscodeAttemptId FROM QualityTestingQueue WHERE Id = %s"
                attemptResult = self.DatabaseManager.DatabaseService.ExecuteQuery(attemptIdQuery, (QueueId,))
                resultsAffected = 0

                if attemptResult:
                    transcodeAttemptId = attemptResult[0][0]
                    resultsUpdateQuery = """
                    UPDATE QualityTestResults
                    SET VMAFScore = 0.0, PassesThreshold = FALSE, ErrorMessage = %s, Status = 'Failed'
                    WHERE TranscodeAttemptId = %s AND Status = 'Running'
                    """
                    resultsAffected = self.DatabaseManager.DatabaseService.ExecuteNonQuery(
                        resultsUpdateQuery,
                        (f"FFmpeg VMAF process died unexpectedly - cleaned by StuckJobDetectionService: {Reason}", transcodeAttemptId)
                    )

                # 3. Delete QualityTestProgress records (using TranscodeAttemptId)
                progressAffected = 0
                if attemptResult:
                    transcodeAttemptId = attemptResult[0][0]
                    progressDeleteQuery = """
                    DELETE FROM QualityTestProgress
                    WHERE TranscodeAttemptId = %s
                    """
                    progressAffected = self.DatabaseManager.DatabaseService.ExecuteNonQuery(progressDeleteQuery, (transcodeAttemptId,))

                # 4. Complete ActiveJobs records for this service
                activeJobUpdateQuery = """
                UPDATE ActiveJobs
                SET Status = 'Failed', UpdatedAt = NOW()
                WHERE ServiceName = 'QualityTest' AND QueueId = %s
                """
                activeJobAffected = self.DatabaseManager.DatabaseService.ExecuteNonQuery(
                    activeJobUpdateQuery,
                    (QueueId,)
                )

                # Commit transaction
                self.DatabaseManager.DatabaseService.CommitTransaction()

                # Log cleanup details
                LoggingService.LogInfo(f"Cleaned up stuck quality test job {QueueId}: Queue={queueAffected}, Results={resultsAffected}, Progress={progressAffected}, ActiveJobs={activeJobAffected}",
                                     "StuckJobDetectionService", "CleanupStuckQualityTestJob")

                return {
                    "Success": True,
                    "Message": f"Successfully cleaned up stuck quality test job {QueueId}",
                    "QueueAffected": queueAffected,
                    "ResultsAffected": resultsAffected,
                    "ProgressAffected": progressAffected,
                    "ActiveJobsAffected": activeJobAffected
                }

            except Exception as e:
                # Rollback transaction on error
                self.DatabaseManager.DatabaseService.RollbackTransaction()
                raise e

        except Exception as e:
            errorMsg = f"Exception cleaning up stuck quality test job {QueueId}: {str(e)}"
            LoggingService.LogException(errorMsg, e, "StuckJobDetectionService", "CleanupStuckQualityTestJob")
            return {
                "Success": False,
                "ErrorMessage": errorMsg
            }

    def DetectAndCleanStuckScanJobs(self) -> Dict[str, Any]:
        """Detect and reset ScanJobs rows stuck in Status='Running' with stale LastUpdated.

        A scan is stuck if either:
          - LastUpdated is older than StuckScanThresholdMin (default 15) -- the
            scan thread is dead but no one cleared the row, OR
          - WorkerName is set and that worker's heartbeat is stale (WorkerService
            crashed mid-scan).

        Stuck rows are flipped to Status='Failed' with an ErrorMessage explaining
        the cleanup. The next continuous-scan tick (or manual scan) is then free
        to claim the rootfolder again -- the per-rootfolder duplicate guard
        (`IsScanRunningForRootFolder`) only blocks Pending/Running rows.

        Owns FileScanning.feature.md criterion 18 stuck-scan side and the
        [BUG] entry in memory/KNOWN-ISSUES.md.
        """
        try:
            LoggingService.LogFunctionEntry("DetectAndCleanStuckScanJobs", "StuckJobDetectionService")

            thresholdMin = self._GetStuckScanThresholdMin()

            # Pull all running scans -- typically a handful, so per-row work is fine.
            query = (
                "SELECT Id, JobId, StorageRootId, RelativePath, WorkerName, LastUpdated, StartTime "
                "FROM ScanJobs "
                "WHERE Status = 'Running'"
            )
            runningRows = self.DatabaseManager.DatabaseService.ExecuteQuery(query)

            if not runningRows:
                LoggingService.LogInfo("Stuck scan detection: no running scans",
                                     "StuckJobDetectionService", "DetectAndCleanStuckScanJobs")
                return {"Success": True, "StuckScansFound": 0, "ScansCleaned": 0}

            stuckIds = []
            cleanedIds = []
            now = datetime.now(timezone.utc)

            for row in runningRows:
                scanId = row.get('Id') or row.get('id')
                jobId = row.get('JobId') or row.get('jobid')
                from Core.Path.Path import Path as _PathSJD, PathError as _PESJD
                from Core.Path.PathStorageRoots import GetPrefixMap as _GPMSJD
                _SidSJD = row.get('StorageRootId') or row.get('storagerootid')
                _RelSJD = row.get('RelativePath') or row.get('relativepath')
                try:
                    rootFolderPath = _PathSJD(_SidSJD, _RelSJD or '').CanonicalDisplay(_GPMSJD()) if _SidSJD is not None else ''
                except _PESJD:
                    rootFolderPath = ''
                workerName = row.get('WorkerName') or row.get('workername')
                lastUpdated = row.get('LastUpdated') or row.get('lastupdated')

                isStuck = False
                reason = None

                # Tier 1: worker heartbeat staleness (if scan is owned by a known worker)
                if workerName:
                    workerOffline, workerReason = self._IsWorkerOffline(workerName)
                    if workerOffline:
                        isStuck = True
                        reason = f"Owning worker '{workerName}' is offline: {workerReason}"

                # Tier 2: LastUpdated staleness
                if not isStuck and lastUpdated:
                    minutesSinceUpdate = (now - AsAwareUtc(lastUpdated)).total_seconds() / 60.0
                    if minutesSinceUpdate >= thresholdMin:
                        isStuck = True
                        reason = (
                            f"ScanJobs.LastUpdated stale -- {minutesSinceUpdate:.1f} min ago "
                            f"(threshold: {thresholdMin}min)"
                        )

                if not isStuck:
                    continue

                LoggingService.LogWarning(
                    f"Stuck scan detected: ScanJobs.Id={scanId}, RootFolder='{rootFolderPath}', "
                    f"Worker='{workerName}', JobId={jobId}, Reason={reason}",
                    "StuckJobDetectionService", "DetectAndCleanStuckScanJobs"
                )
                stuckIds.append(scanId)

                # Flip to Failed so the next scan tick can re-claim the rootfolder.
                # The per-rootfolder duplicate guard only blocks Pending/Running.
                cleanupQuery = """
                    UPDATE ScanJobs
                    SET Status = 'Failed',
                        EndTime = NOW(),
                        ErrorMessage = %s
                    WHERE Id = %s AND Status = 'Running'
                """
                cleanupMessage = f"Stuck scan cleaned by StuckJobDetectionService: {reason}"
                affected = self.DatabaseManager.DatabaseService.ExecuteNonQuery(
                    cleanupQuery, (cleanupMessage, scanId)
                )
                if affected > 0:
                    cleanedIds.append(scanId)
                    LoggingService.LogInfo(
                        f"Stuck scan {scanId} flipped to Failed",
                        "StuckJobDetectionService", "DetectAndCleanStuckScanJobs"
                    )

            LoggingService.LogInfo(
                f"Stuck scan detection completed - found {len(stuckIds)}, cleaned {len(cleanedIds)}",
                "StuckJobDetectionService", "DetectAndCleanStuckScanJobs"
            )
            return {
                "Success": True,
                "StuckScansFound": len(stuckIds),
                "ScansCleaned": len(cleanedIds),
                "StuckScans": stuckIds,
                "CleanedScans": cleanedIds
            }

        except Exception as e:
            errorMsg = f"Exception during stuck scan detection: {str(e)}"
            LoggingService.LogException(errorMsg, e, "StuckJobDetectionService", "DetectAndCleanStuckScanJobs")
            return {"Success": False, "ErrorMessage": errorMsg, "StuckScansFound": 0, "ScansCleaned": 0}

    def DetectAndCleanAllStuckJobs(self) -> Dict[str, Any]:
        """Detect and clean stuck jobs for both transcode and quality test."""
        try:
            LoggingService.LogFunctionEntry("DetectAndCleanAllStuckJobs", "StuckJobDetectionService")

            # Detect and clean transcode jobs
            transcodeResult = self.DetectAndCleanStuckTranscodeJobs()

            # Detect and clean quality test jobs
            qualityResult = self.DetectAndCleanStuckQualityTestJobs()

            # Combine results
            totalStuckFound = transcodeResult.get("StuckJobsFound", 0) + qualityResult.get("StuckJobsFound", 0)
            totalJobsCleaned = transcodeResult.get("JobsCleaned", 0) + qualityResult.get("JobsCleaned", 0)

            LoggingService.LogInfo(f"Combined stuck job detection completed - found {totalStuckFound} stuck jobs total, cleaned {totalJobsCleaned} jobs total",
                                 "StuckJobDetectionService", "DetectAndCleanAllStuckJobs")

            return {
                "Success": True,
                "Message": f"Combined detection completed - found {totalStuckFound} stuck jobs, cleaned {totalJobsCleaned} jobs",
                "TotalStuckJobsFound": totalStuckFound,
                "TotalJobsCleaned": totalJobsCleaned,
                "TranscodeResult": transcodeResult,
                "QualityTestResult": qualityResult
            }

        except Exception as e:
            errorMsg = f"Exception during combined stuck job detection: {str(e)}"
            LoggingService.LogException(errorMsg, e, "StuckJobDetectionService", "DetectAndCleanAllStuckJobs")
            return {
                "Success": False,
                "ErrorMessage": errorMsg,
                "TotalStuckJobsFound": 0,
                "TotalJobsCleaned": 0
            }

    def FindOrphanedFFmpegProcesses(self) -> Dict[str, Any]:
        """
        Find FFmpeg processes running on the system that aren't tracked in ActiveJobs.
        Returns list of orphaned FFmpeg processes with their command lines.
        """
        try:
            LoggingService.LogFunctionEntry("FindOrphanedFFmpegProcesses", "StuckJobDetectionService")

            # Get all running FFmpeg processes
            ffmpegProcesses = self.ProcessManagementService.FindFFmpegProcesses()

            if not ffmpegProcesses:
                LoggingService.LogInfo("No FFmpeg processes found on system", "StuckJobDetectionService", "FindOrphanedFFmpegProcesses")
                return {
                    "Success": True,
                    "Message": "No FFmpeg processes found",
                    "OrphanedProcesses": [],
                    "TotalFFmpegProcesses": 0,
                    "OrphanedCount": 0
                }

            # Get all tracked PIDs from ActiveJobs
            trackedPids = self.DatabaseManager.GetAllActiveJobProcessIds()

            # Find orphaned processes (FFmpeg running but not tracked)
            orphanedProcesses = []
            for process in ffmpegProcesses:
                if process['Pid'] not in trackedPids:
                    # Analyze command line to get more info
                    cmdlineInfo = self.AnalyzeFFmpegCommandLine(process['Cmdline'])

                    orphanedProcesses.append({
                        "Pid": process['Pid'],
                        "Name": process['Name'],
                        "Cmdline": process['Cmdline'],
                        "InputFile": cmdlineInfo.get('InputFile'),
                        "OutputFile": cmdlineInfo.get('OutputFile'),
                        "OperationType": cmdlineInfo.get('OperationType'),
                        "IsTranscode": cmdlineInfo.get('IsTranscode', False),
                        "IsVMAF": cmdlineInfo.get('IsVMAF', False)
                    })

            LoggingService.LogInfo(f"Found {len(ffmpegProcesses)} FFmpeg processes, {len(orphanedProcesses)} orphaned",
                                 "StuckJobDetectionService", "FindOrphanedFFmpegProcesses")

            return {
                "Success": True,
                "Message": f"Found {len(ffmpegProcesses)} FFmpeg processes, {len(orphanedProcesses)} orphaned",
                "OrphanedProcesses": orphanedProcesses,
                "TotalFFmpegProcesses": len(ffmpegProcesses),
                "OrphanedCount": len(orphanedProcesses)
            }

        except Exception as e:
            errorMsg = f"Exception finding orphaned FFmpeg processes: {str(e)}"
            LoggingService.LogException(errorMsg, e, "StuckJobDetectionService", "FindOrphanedFFmpegProcesses")
            return {
                "Success": False,
                "ErrorMessage": errorMsg,
                "OrphanedProcesses": [],
                "TotalFFmpegProcesses": 0,
                "OrphanedCount": 0
            }

    def AnalyzeFFmpegCommandLine(self, CmdLine: str) -> Dict[str, Any]:
        """
        Parse FFmpeg command line to extract:
        - Input file path
        - Output file path
        - Operation type (transcode vs VMAF)
        Returns dict with parsed info
        """
        try:
            if not CmdLine:
                return {
                    "InputFile": None,
                    "OutputFile": None,
                    "OperationType": "Unknown",
                    "IsTranscode": False,
                    "IsVMAF": False
                }

            # Normalize path separators for Windows
            cmdline = CmdLine.replace('\\', '/')

            # Extract input file (-i parameter)
            inputFile = None
            inputMatch = re.search(r'-i\s+["\']?([^"\'\s]+)["\']?', cmdline)
            if inputMatch:
                inputFile = inputMatch.group(1)

            # Extract output file (usually the last argument)
            outputFile = None
            # Split command line and get the last argument that looks like a file path
            parts = cmdline.split()
            for part in reversed(parts):
                if (part.endswith(('.mp4', '.mkv', '.avi', '.mov', '.m4v', '.webm')) and
                    not part.startswith('-') and
                    ('/' in part or '\\' in part)):
                    outputFile = part
                    break

            # Determine operation type
            isVMAF = 'vmaf' in cmdline.lower() or 'libvmaf' in cmdline.lower()
            isTranscode = not isVMAF and (outputFile is not None or 'transcode' in cmdline.lower())

            operationType = "VMAF" if isVMAF else ("Transcode" if isTranscode else "Unknown")

            return {
                "InputFile": inputFile,
                "OutputFile": outputFile,
                "OperationType": operationType,
                "IsTranscode": isTranscode,
                "IsVMAF": isVMAF
            }

        except Exception as e:
            LoggingService.LogException(f"Error analyzing FFmpeg command line: {CmdLine}", e,
                                      "StuckJobDetectionService", "AnalyzeFFmpegCommandLine")
            return {
                "InputFile": None,
                "OutputFile": None,
                "OperationType": "Unknown",
                "IsTranscode": False,
                "IsVMAF": False
            }

    def CorrelateFFmpegWithJobs(self) -> Dict[str, Any]:
        """
        Correlate running FFmpeg processes with database jobs.
        Returns:
        - Orphaned processes (FFmpeg running, no job)
        - Stuck jobs (Job Running, no FFmpeg)
        - Healthy jobs (Job Running, FFmpeg found)
        """
        try:
            LoggingService.LogFunctionEntry("CorrelateFFmpegWithJobs", "StuckJobDetectionService")

            # Get all running FFmpeg processes
            ffmpegProcesses = self.ProcessManagementService.FindFFmpegProcesses()

            # Get all running jobs
            runningTranscodeJobs = self.DatabaseManager.GetTranscodeQueueItemsByStatus("Running")
            # For quality test jobs, we need to get them differently since there's no status filter method
            qualityTestQueue = self.DatabaseManager.GetQualityTestQueue()
            activeQualityJobs = self.DatabaseManager.GetActiveJobsByService("QualityTest")

            # Filter quality test jobs that are actually running (have active jobs)
            runningQualityJobs = []
            for activeJob in activeQualityJobs:
                queueId = activeJob.get('QueueId')
                if queueId:
                    # Find the corresponding queue item
                    for queueItem in qualityTestQueue:
                        if queueItem['Id'] == queueId:
                            runningQualityJobs.append(queueItem)
                            break

            # Get tracked PIDs
            trackedPids = self.DatabaseManager.GetAllActiveJobProcessIds()

            # Categorize results
            orphanedProcesses = []
            stuckJobs = []
            healthyJobs = []

            # Find orphaned FFmpeg processes
            for process in ffmpegProcesses:
                if process['Pid'] not in trackedPids:
                    cmdlineInfo = self.AnalyzeFFmpegCommandLine(process['Cmdline'])
                    orphanedProcesses.append({
                        "Pid": process['Pid'],
                        "Cmdline": process['Cmdline'],
                        "InputFile": cmdlineInfo.get('InputFile'),
                        "OutputFile": cmdlineInfo.get('OutputFile'),
                        "OperationType": cmdlineInfo.get('OperationType')
                    })

            # Check transcode jobs
            for job in runningTranscodeJobs:
                isStuck, reason = self.IsJobStuck(job)
                if isStuck:
                    stuckJobs.append({
                        "JobId": job.Id,
                        "JobType": "Transcode",
                        "FileName": job.FileName,
                        "FilePath": job.FilePath,
                        "Reason": reason
                    })
                else:
                    healthyJobs.append({
                        "JobId": job.Id,
                        "JobType": "Transcode",
                        "FileName": job.FileName,
                        "FilePath": job.FilePath,
                        "Status": "Healthy"
                    })

            # Check quality test jobs
            for job in runningQualityJobs:
                isStuck, reason = self.IsQualityTestJobStuck(job)
                if isStuck:
                    stuckJobs.append({
                        "JobId": job['Id'],
                        "JobType": "QualityTest",
                        "OriginalFilePath": job.get('OriginalFilePath', 'Unknown'),
                        "Reason": reason
                    })
                else:
                    healthyJobs.append({
                        "JobId": job['Id'],
                        "JobType": "QualityTest",
                        "OriginalFilePath": job.get('OriginalFilePath', 'Unknown'),
                        "Status": "Healthy"
                    })

            LoggingService.LogInfo(f"Correlation complete: {len(orphanedProcesses)} orphaned processes, {len(stuckJobs)} stuck jobs, {len(healthyJobs)} healthy jobs",
                                 "StuckJobDetectionService", "CorrelateFFmpegWithJobs")

            return {
                "Success": True,
                "Message": f"Correlation complete: {len(orphanedProcesses)} orphaned, {len(stuckJobs)} stuck, {len(healthyJobs)} healthy",
                "OrphanedProcesses": orphanedProcesses,
                "StuckJobs": stuckJobs,
                "HealthyJobs": healthyJobs,
                "OrphanedCount": len(orphanedProcesses),
                "StuckCount": len(stuckJobs),
                "HealthyCount": len(healthyJobs)
            }

        except Exception as e:
            errorMsg = f"Exception correlating FFmpeg with jobs: {str(e)}"
            LoggingService.LogException(errorMsg, e, "StuckJobDetectionService", "CorrelateFFmpegWithJobs")
            return {
                "Success": False,
                "ErrorMessage": errorMsg,
                "OrphanedProcesses": [],
                "StuckJobs": [],
                "HealthyJobs": [],
                "OrphanedCount": 0,
                "StuckCount": 0,
                "HealthyCount": 0
            }

    def DetectWithOrphanedProcessCheck(self) -> Dict[str, Any]:
        """
        Enhanced detection that includes orphaned process check.
        Combines existing stuck job detection with FFmpeg process correlation.
        """
        try:
            LoggingService.LogFunctionEntry("DetectWithOrphanedProcessCheck", "StuckJobDetectionService")

            # Run existing stuck job detection
            stuckJobResult = self.DetectAndCleanAllStuckJobs()

            # Run FFmpeg correlation
            correlationResult = self.CorrelateFFmpegWithJobs()

            # Combine results
            totalStuckFound = stuckJobResult.get("TotalStuckJobsFound", 0)
            totalJobsCleaned = stuckJobResult.get("TotalJobsCleaned", 0)
            orphanedCount = correlationResult.get("OrphanedCount", 0)

            LoggingService.LogInfo(f"Enhanced detection complete: {totalStuckFound} stuck jobs found/cleaned, {orphanedCount} orphaned FFmpeg processes",
                                 "StuckJobDetectionService", "DetectWithOrphanedProcessCheck")

            return {
                "Success": True,
                "Message": f"Enhanced detection complete: {totalStuckFound} stuck jobs, {orphanedCount} orphaned processes",
                "StuckJobResult": stuckJobResult,
                "CorrelationResult": correlationResult,
                "TotalStuckJobsFound": totalStuckFound,
                "TotalJobsCleaned": totalJobsCleaned,
                "OrphanedProcesses": correlationResult.get("OrphanedProcesses", []),
                "OrphanedCount": orphanedCount
            }

        except Exception as e:
            errorMsg = f"Exception during enhanced detection: {str(e)}"
            LoggingService.LogException(errorMsg, e, "StuckJobDetectionService", "DetectWithOrphanedProcessCheck")
            return {
                "Success": False,
                "ErrorMessage": errorMsg,
                "TotalStuckJobsFound": 0,
                "TotalJobsCleaned": 0,
                "OrphanedCount": 0
            }

    def KillOrphanedFFmpegProcesses(self, OrphanedProcesses: List[int]) -> Dict[str, Any]:
        """
        Kill specified orphaned FFmpeg processes.
        Logs all actions comprehensively.
        """
        try:
            LoggingService.LogFunctionEntry("KillOrphanedFFmpegProcesses", "StuckJobDetectionService", len(OrphanedProcesses))

            if not OrphanedProcesses:
                return {
                    "Success": True,
                    "Message": "No orphaned processes to kill",
                    "ProcessesKilled": 0
                }

            killedCount = 0
            failedKills = []

            for pid in OrphanedProcesses:
                try:
                    if self.ProcessManagementService.KillProcess(pid, Graceful=True):
                        killedCount += 1
                        LoggingService.LogInfo(f"Successfully killed orphaned FFmpeg process {pid}",
                                             "StuckJobDetectionService", "KillOrphanedFFmpegProcesses")
                    else:
                        failedKills.append(pid)
                        LoggingService.LogWarning(f"Failed to kill orphaned FFmpeg process {pid}",
                                                "StuckJobDetectionService", "KillOrphanedFFmpegProcesses")

                except Exception as e:
                    failedKills.append(pid)
                    LoggingService.LogException(f"Error killing orphaned FFmpeg process {pid}", e,
                                             "StuckJobDetectionService", "KillOrphanedFFmpegProcesses")

            LoggingService.LogInfo(f"Killed {killedCount} orphaned FFmpeg processes, {len(failedKills)} failed",
                                 "StuckJobDetectionService", "KillOrphanedFFmpegProcesses")

            return {
                "Success": True,
                "Message": f"Killed {killedCount} orphaned processes, {len(failedKills)} failed",
                "ProcessesKilled": killedCount,
                "FailedKills": failedKills
            }

        except Exception as e:
            errorMsg = f"Exception killing orphaned FFmpeg processes: {str(e)}"
            LoggingService.LogException(errorMsg, e, "StuckJobDetectionService", "KillOrphanedFFmpegProcesses")
            return {
                "Success": False,
                "ErrorMessage": errorMsg,
                "ProcessesKilled": 0
            }

    def RecoverFromOrphanedState(self) -> Dict[str, Any]:
        """
        Complete recovery workflow:
        1. Find orphaned FFmpeg processes
        2. Find stuck jobs
        3. Kill orphaned processes
        4. Reset stuck jobs
        5. Log comprehensive report
        """
        try:
            LoggingService.LogFunctionEntry("RecoverFromOrphanedState", "StuckJobDetectionService")

            # Step 1: Find orphaned FFmpeg processes
            orphanedResult = self.FindOrphanedFFmpegProcesses()
            orphanedProcesses = orphanedResult.get("OrphanedProcesses", [])

            # Step 2: Run enhanced detection (finds stuck jobs)
            detectionResult = self.DetectWithOrphanedProcessCheck()

            # Step 3: Kill orphaned processes
            killedCount = 0
            if orphanedProcesses:
                pidsToKill = [p["Pid"] for p in orphanedProcesses]
                killResult = self.KillOrphanedFFmpegProcesses(pidsToKill)
                killedCount = killResult.get("ProcessesKilled", 0)

            # Step 4: Results are already handled by DetectWithOrphanedProcessCheck

            totalStuckFound = detectionResult.get("TotalStuckJobsFound", 0)
            totalJobsCleaned = detectionResult.get("TotalJobsCleaned", 0)

            LoggingService.LogInfo(f"Recovery complete: {killedCount} orphaned processes killed, {totalStuckFound} stuck jobs found, {totalJobsCleaned} jobs cleaned",
                                 "StuckJobDetectionService", "RecoverFromOrphanedState")

            return {
                "Success": True,
                "Message": f"Recovery complete: {killedCount} orphaned processes killed, {totalStuckFound} stuck jobs found, {totalJobsCleaned} jobs cleaned",
                "OrphanedProcessesFound": len(orphanedProcesses),
                "OrphanedProcessesKilled": killedCount,
                "StuckJobsFound": totalStuckFound,
                "JobsCleaned": totalJobsCleaned,
                "OrphanedResult": orphanedResult,
                "DetectionResult": detectionResult
            }

        except Exception as e:
            errorMsg = f"Exception during orphaned state recovery: {str(e)}"
            LoggingService.LogException(errorMsg, e, "StuckJobDetectionService", "RecoverFromOrphanedState")
            return {
                "Success": False,
                "ErrorMessage": errorMsg,
                "OrphanedProcessesFound": 0,
                "OrphanedProcessesKilled": 0,
                "StuckJobsFound": 0,
                "JobsCleaned": 0
            }
