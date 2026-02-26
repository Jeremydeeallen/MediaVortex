"""
StuckJobDetectionService
Detects and cleans up stuck transcode jobs where FFmpeg processes have died but database status remains "Running".
"""

import psutil
import re
from typing import Dict, Any, List, Optional
from datetime import datetime
from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService
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
    
    # If no progress update for this many minutes, consider the job frozen (even if FFmpeg process is alive)
    FROZEN_PROGRESS_THRESHOLD_MINUTES = 5

    def IsJobStuck(self, Job) -> tuple[bool, str]:
        """Check if a specific job is stuck by verifying if the FFmpeg process is still alive and making progress."""
        try:
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

            processId = relevantActiveJob.get('ProcessId')
            if not processId:
                # No process ID recorded yet - might be stuck
                return True, "No ProcessId recorded in ActiveJob"

            # Check if the tracked process is still alive and is actually FFmpeg
            isAlive = self.IsProcessAlive(processId)

            if not isAlive:
                return True, f"FFmpeg process {processId} not found or is no longer FFmpeg (process died or PID reused)"

            # Secondary check: verify there are actually FFmpeg processes on the system
            ffmpegProcesses = self.ProcessManagementService.FindFFmpegProcesses()
            if not ffmpegProcesses:
                return True, f"No FFmpeg processes running on system but job status is Running (PID {processId} may have been reused)"

            # Progress stagnation check: process is alive but may be frozen
            isFrozen, frozenReason = self._IsJobFrozen(Job)
            if isFrozen:
                return True, frozenReason

            return False, "Process is alive and making progress"

        except Exception as e:
            LoggingService.LogException(f"Error checking if job {Job.Id} is stuck", e,
                                     "StuckJobDetectionService", "IsJobStuck")
            # If we can't determine, assume it's not stuck to be safe
            return False, f"Error checking process status: {str(e)}"

    def _IsJobFrozen(self, Job) -> tuple[bool, str]:
        """Check if a job's FFmpeg process is alive but not making progress (frozen/hung)."""
        try:
            # Get the latest TranscodeProgress record for this job's file
            query = """
                SELECT tp.LastProgressUpdate, tp.ProgressPercent, tp.CurrentFPS
                FROM TranscodeProgress tp
                INNER JOIN TranscodeAttempts ta ON tp.TranscodeAttemptId = ta.Id
                WHERE LOWER(ta.FilePath) = LOWER(%s) AND ta.Success IS NULL
                ORDER BY tp.LastProgressUpdate DESC
                LIMIT 1
            """
            rows = self.DatabaseManager.DatabaseService.ExecuteQuery(query, (Job.FilePath,))

            if not rows:
                # No progress records yet - job may still be starting up, not frozen
                return False, "No progress records found (job may be starting)"

            row = rows[0]
            lastUpdateValue = row['LastProgressUpdate']
            progressPercent = row['ProgressPercent']
            currentFPS = row['CurrentFPS']

            if not lastUpdateValue:
                return False, "No LastProgressUpdate timestamp available"

            # Parse the timestamp and check staleness
            # PostgreSQL returns datetime objects directly, but handle string format as fallback
            if isinstance(lastUpdateValue, str):
                lastUpdate = datetime.strptime(lastUpdateValue, "%Y-%m-%d %H:%M:%S")
            else:
                lastUpdate = lastUpdateValue
            minutesSinceUpdate = (datetime.now() - lastUpdate).total_seconds() / 60.0

            if minutesSinceUpdate >= self.FROZEN_PROGRESS_THRESHOLD_MINUTES:
                return True, (
                    f"FFmpeg process is alive but frozen - no progress update for {minutesSinceUpdate:.1f} minutes "
                    f"(threshold: {self.FROZEN_PROGRESS_THRESHOLD_MINUTES}min). "
                    f"Last progress: {progressPercent:.1f}%, FPS: {currentFPS}"
                )

            return False, f"Progress updated {minutesSinceUpdate:.1f} minutes ago"

        except Exception as e:
            LoggingService.LogException(f"Error checking if job {Job.Id} is frozen", e,
                                     "StuckJobDetectionService", "_IsJobFrozen")
            return False, f"Error checking progress stagnation: {str(e)}"
    
    def IsProcessAlive(self, ProcessId: int) -> bool:
        """Check if a process with the given ID is still alive and is actually an FFmpeg process."""
        try:
            if not ProcessId or ProcessId <= 0:
                return False

            # Verify the process exists AND is actually FFmpeg (PIDs get reused by the OS)
            process = psutil.Process(ProcessId)
            return process.is_running() and 'ffmpeg' in process.name().lower()

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return False
        except Exception as e:
            LoggingService.LogException(f"Error checking if process {ProcessId} is alive", e,
                                      "StuckJobDetectionService", "IsProcessAlive")
            return False
    
    def CleanupStuckJob(self, QueueId: int, Reason: str) -> Dict[str, Any]:
        """Clean up a stuck job by resetting its status and cleaning up related records."""
        try:
            LoggingService.LogFunctionEntry("CleanupStuckJob", "StuckJobDetectionService", QueueId, Reason)
            
            # Get job details for logging
            jobDetails = self.DatabaseManager.GetTranscodeQueueItemById(QueueId)
            if not jobDetails:
                return {
                    "Success": False,
                    "ErrorMessage": f"TranscodeQueue job {QueueId} not found"
                }
            
            # Start database transaction for atomic cleanup
            self.DatabaseManager.DatabaseService.BeginTransaction()
            
            try:
                # 1. Reset TranscodeQueue status to Pending
                queueUpdateQuery = """
                UPDATE TranscodeQueue 
                SET Status = 'Pending', DateStarted = NULL 
                WHERE Id = %s
                """
                queueAffected = self.DatabaseManager.DatabaseService.ExecuteNonQuery(queueUpdateQuery, (QueueId,))

                # 2. Update TranscodeAttempts to mark as failed
                attemptUpdateQuery = """
                UPDATE TranscodeAttempts
                SET Success = FALSE, ErrorMessage = %s
                WHERE LOWER(FilePath) = LOWER(%s) AND Success IS NULL
                """
                attemptAffected = self.DatabaseManager.DatabaseService.ExecuteNonQuery(
                    attemptUpdateQuery, 
                    (f"FFmpeg process died unexpectedly - cleaned by StuckJobDetectionService: {Reason}", jobDetails.FilePath)
                )
                
                # 3. Delete TranscodeProgress records
                progressDeleteQuery = """
                DELETE FROM TranscodeProgress 
                WHERE TranscodeAttemptId IN (
                    SELECT Id FROM TranscodeAttempts 
                    WHERE LOWER(FilePath) = LOWER(%s) AND Success = FALSE
                )
                """
                progressAffected = self.DatabaseManager.DatabaseService.ExecuteNonQuery(progressDeleteQuery, (jobDetails.FilePath,))
                
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
                
                # Commit transaction
                self.DatabaseManager.DatabaseService.CommitTransaction()
                
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
                # Rollback transaction on error
                self.DatabaseManager.DatabaseService.RollbackTransaction()
                raise e
                
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
    
    def DetectAndCleanStuckQualityTestJobs(self) -> Dict[str, Any]:
        """Detect and clean up stuck quality test jobs where FFmpeg VMAF processes have died."""
        try:
            LoggingService.LogFunctionEntry("DetectAndCleanStuckQualityTestJobs", "StuckJobDetectionService")
            
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
            
            return {
                "Success": True,
                "Message": f"Quality test detection completed - found {len(stuckJobs)} stuck jobs, cleaned {len(cleanedJobs)} jobs",
                "StuckJobsFound": len(stuckJobs),
                "JobsCleaned": len(cleanedJobs),
                "StuckJobs": stuckJobs,
                "CleanedJobs": cleanedJobs
            }
            
        except Exception as e:
            errorMsg = f"Exception during stuck quality test job detection: {str(e)}"
            LoggingService.LogException(errorMsg, e, "StuckJobDetectionService", "DetectAndCleanStuckQualityTestJobs")
            return {
                "Success": False,
                "ErrorMessage": errorMsg,
                "StuckJobsFound": 0,
                "JobsCleaned": 0
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

