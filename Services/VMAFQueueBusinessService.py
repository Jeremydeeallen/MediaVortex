import os
from typing import Optional, Dict, Any, List
from datetime import datetime
from Models.VMAFQueueModel import VMAFQueueModel
from Models.TranscodeAttemptModel import TranscodeAttemptModel
from Repositories.DatabaseManager import DatabaseManager
from Services.FFmpegComparisonService import FFmpegComparisonService
from Services.LoggingService import LoggingService


class VMAFQueueBusinessService:
    """Business service for managing VMAF quality analysis queue operations."""
    
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None, 
                 FFmpegComparisonServiceInstance: FFmpegComparisonService = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.FFmpegComparisonService = FFmpegComparisonServiceInstance or FFmpegComparisonService()
        self.IsRunning = False
        self.CurrentVMAFJob = None
    
    def AddToVMAFQueue(self, TranscodeAttemptId: int, OriginalFilePath: str, 
                      TranscodedFilePath: str, QualityThreshold: float = 90.0) -> Dict[str, Any]:
        """Add a transcoded file to the VMAF queue for quality analysis."""
        try:
            LoggingService.LogFunctionEntry("AddToVMAFQueue", "VMAFQueueBusinessService", 
                                          f"AttemptId: {TranscodeAttemptId}, File: {os.path.basename(OriginalFilePath)}")
            
            # Create VMAF queue item
            VMAFQueueItem = VMAFQueueModel()
            VMAFQueueItem.TranscodeAttemptId = TranscodeAttemptId
            VMAFQueueItem.OriginalFilePath = OriginalFilePath
            VMAFQueueItem.TranscodedFilePath = TranscodedFilePath
            VMAFQueueItem.FileName = os.path.basename(OriginalFilePath)
            VMAFQueueItem.QualityThreshold = QualityThreshold
            VMAFQueueItem.DateAdded = datetime.now()
            
            # Save to database
            VMAFQueueId = self.DatabaseManager.SaveVMAFQueueItem(VMAFQueueItem)
            VMAFQueueItem.Id = VMAFQueueId
            
            LoggingService.LogInfo(f"Added {VMAFQueueItem.FileName} to VMAF queue with ID {VMAFQueueId}", 
                                 "VMAFQueueBusinessService", "AddToVMAFQueue")
            
            return {
                "Success": True,
                "VMAFQueueId": VMAFQueueId,
                "Message": f"Added {VMAFQueueItem.FileName} to VMAF queue"
            }
            
        except Exception as e:
            errorMsg = f"Exception adding to VMAF queue: {str(e)}"
            LoggingService.LogException(errorMsg, e, "VMAFQueueBusinessService", "AddToVMAFQueue")
            return {"Success": False, "ErrorMessage": errorMsg}
    
    def StartVMAFProcessing(self, MaxConcurrentJobs: int = 1) -> Dict[str, Any]:
        """Start processing VMAF queue."""
        try:
            LoggingService.LogFunctionEntry("StartVMAFProcessing", "VMAFQueueBusinessService", MaxConcurrentJobs)
            
            if self.IsRunning:
                LoggingService.LogWarning("VMAF processing is already running", "VMAFQueueBusinessService", "StartVMAFProcessing")
                return {"Success": False, "ErrorMessage": "VMAF processing is already running"}
            
            self.IsRunning = True
            LoggingService.LogInfo("Starting VMAF processing", "VMAFQueueBusinessService", "StartVMAFProcessing")
            
            # Start processing queue
            self.ProcessVMAFQueue(MaxConcurrentJobs)
            
            return {"Success": True, "Message": "VMAF processing started"}
            
        except Exception as e:
            self.IsRunning = False
            errorMsg = f"Exception starting VMAF processing: {str(e)}"
            LoggingService.LogException(errorMsg, e, "VMAFQueueBusinessService", "StartVMAFProcessing")
            return {"Success": False, "ErrorMessage": errorMsg}
    
    def StopVMAFProcessing(self) -> Dict[str, Any]:
        """Stop VMAF processing."""
        try:
            LoggingService.LogFunctionEntry("StopVMAFProcessing", "VMAFQueueBusinessService")
            
            if not self.IsRunning:
                LoggingService.LogWarning("VMAF processing is not running", "VMAFQueueBusinessService", "StopVMAFProcessing")
                return {"Success": False, "ErrorMessage": "VMAF processing is not running"}
            
            self.IsRunning = False
            
            # Mark current job as cancelled if running
            if self.CurrentVMAFJob:
                self.CurrentVMAFJob.Status = "Cancelled"
                self.DatabaseManager.SaveVMAFQueueItem(self.CurrentVMAFJob)
                LoggingService.LogInfo(f"Cancelled current VMAF job: {self.CurrentVMAFJob.FileName}", 
                                     "VMAFQueueBusinessService", "StopVMAFProcessing")
                self.CurrentVMAFJob = None
            
            LoggingService.LogInfo("VMAF processing stopped", "VMAFQueueBusinessService", "StopVMAFProcessing")
            return {"Success": True, "Message": "VMAF processing stopped"}
            
        except Exception as e:
            errorMsg = f"Exception stopping VMAF processing: {str(e)}"
            LoggingService.LogException(errorMsg, e, "VMAFQueueBusinessService", "StopVMAFProcessing")
            return {"Success": False, "ErrorMessage": errorMsg}
    
    def ProcessVMAFQueue(self, MaxConcurrentJobs: int = 1):
        """Process items from the VMAF queue."""
        try:
            LoggingService.LogFunctionEntry("ProcessVMAFQueue", "VMAFQueueBusinessService", MaxConcurrentJobs)
            
            while self.IsRunning:
                # Get next VMAF job
                nextJob = self.GetNextVMAFJob()
                if not nextJob:
                    LoggingService.LogInfo("No VMAF jobs available for processing", "VMAFQueueBusinessService", "ProcessVMAFQueue")
                    break
                
                # Process the VMAF job
                self.CurrentVMAFJob = nextJob
                result = self.ProcessVMAFJob(nextJob)
                
                if not result.get("Success", False):
                    LoggingService.LogError(f"Failed to process VMAF job {nextJob.Id}: {result.get('ErrorMessage', 'Unknown error')}", 
                                          "VMAFQueueBusinessService", "ProcessVMAFQueue")
                
                self.CurrentVMAFJob = None
                
                # Small delay between jobs
                import time
                time.sleep(1)
            
            LoggingService.LogInfo("VMAF queue processing completed", "VMAFQueueBusinessService", "ProcessVMAFQueue")
            
        except Exception as e:
            LoggingService.LogException("Exception processing VMAF queue", e, "VMAFQueueBusinessService", "ProcessVMAFQueue")
            self.IsRunning = False
    
    def ProcessVMAFJob(self, VMAFQueueItem: VMAFQueueModel) -> Dict[str, Any]:
        """Process a single VMAF quality analysis job."""
        try:
            LoggingService.LogFunctionEntry("ProcessVMAFJob", "VMAFQueueBusinessService", 
                                          VMAFQueueItem.Id, VMAFQueueItem.FileName)
            
            # Mark job as running
            VMAFQueueItem.MarkAsRunning()
            self.DatabaseManager.SaveVMAFQueueItem(VMAFQueueItem)
            
            # Perform VMAF analysis
            LoggingService.LogInfo(f"Starting VMAF analysis for {VMAFQueueItem.FileName}", 
                                 "VMAFQueueBusinessService", "ProcessVMAFJob")
            
            VMAFResult = self.FFmpegComparisonService.CreateVMAFComparison(
                VMAFQueueItem.OriginalFilePath,
                VMAFQueueItem.TranscodedFilePath
            )
            
            if VMAFResult.Success:
                # VMAF analysis succeeded
                VMAFQueueItem.MarkAsCompleted(VMAFResult.OverallVMAFScore)
                self.DatabaseManager.SaveVMAFQueueItem(VMAFQueueItem)
                
                # Update the original TranscodeAttempt with VMAF score
                transcodeAttempt = self.DatabaseManager.GetTranscodeAttemptById(VMAFQueueItem.TranscodeAttemptId)
                if transcodeAttempt:
                    transcodeAttempt.VMAF = VMAFResult.OverallVMAFScore
                    self.DatabaseManager.SaveTranscodeAttempt(transcodeAttempt)
                
                LoggingService.LogInfo(f"VMAF analysis completed for {VMAFQueueItem.FileName}: Score = {VMAFResult.OverallVMAFScore:.2f}", 
                                     "VMAFQueueBusinessService", "ProcessVMAFJob")
                
                return {
                    "Success": True,
                    "VMAFQueueId": VMAFQueueItem.Id,
                    "VMAFScore": VMAFResult.OverallVMAFScore,
                    "PassesThreshold": VMAFQueueItem.PassesQualityThreshold(),
                    "Status": "completed"
                }
            else:
                # VMAF analysis failed
                errorMsg = VMAFResult.ErrorMessage or "VMAF analysis failed"
                VMAFQueueItem.MarkAsFailed(errorMsg)
                self.DatabaseManager.SaveVMAFQueueItem(VMAFQueueItem)
                
                LoggingService.LogError(f"VMAF analysis failed for {VMAFQueueItem.FileName}: {errorMsg}", 
                                      "VMAFQueueBusinessService", "ProcessVMAFJob")
                
                return {
                    "Success": False,
                    "VMAFQueueId": VMAFQueueItem.Id,
                    "ErrorMessage": errorMsg,
                    "CanRetry": VMAFQueueItem.CanRetry()
                }
            
        except Exception as e:
            errorMsg = f"Exception processing VMAF job: {str(e)}"
            LoggingService.LogException(errorMsg, e, "VMAFQueueBusinessService", "ProcessVMAFJob")
            
            # Mark job as failed
            VMAFQueueItem.MarkAsFailed(errorMsg)
            self.DatabaseManager.SaveVMAFQueueItem(VMAFQueueItem)
            
            return {"Success": False, "ErrorMessage": errorMsg}
    
    def GetNextVMAFJob(self) -> Optional[VMAFQueueModel]:
        """Get the next pending VMAF job from the queue."""
        try:
            # Get pending jobs ordered by priority and date added
            pendingJobs = self.DatabaseManager.GetVMAFQueueItemsByStatus("Pending")
            if pendingJobs:
                # Sort by priority (descending) then by date added (ascending)
                pendingJobs.sort(key=lambda x: (-x.Priority, x.DateAdded or datetime.min))
                return pendingJobs[0]
            return None
        except Exception as e:
            LoggingService.LogException("Exception getting next VMAF job", e, "VMAFQueueBusinessService", "GetNextVMAFJob")
            return None
    
    def GetVMAFQueueStatus(self) -> Dict[str, Any]:
        """Get current VMAF queue status."""
        try:
            LoggingService.LogFunctionEntry("GetVMAFQueueStatus", "VMAFQueueBusinessService")
            
            # Get queue statistics
            queueStats = self.GetVMAFQueueStatistics()
            isRunning = queueStats.get("RunningJobs", 0) > 0
            
            status = {
                "IsRunning": isRunning,
                "CurrentVMAFJob": None,
                "QueueStatistics": queueStats
            }
            
            # Get current running VMAF job
            if isRunning:
                currentJob = self.GetCurrentRunningVMAFJob()
                if currentJob:
                    status["CurrentVMAFJob"] = {
                        "Id": currentJob.Id,
                        "FileName": currentJob.FileName,
                        "Status": currentJob.Status,
                        "DateStarted": currentJob.DateStarted.isoformat() if currentJob.DateStarted else None,
                        "TranscodeAttemptId": currentJob.TranscodeAttemptId
                    }
            
            return status
            
        except Exception as e:
            LoggingService.LogException("Exception getting VMAF queue status", e, "VMAFQueueBusinessService", "GetVMAFQueueStatus")
            return {"IsRunning": False, "Error": str(e)}
    
    def GetCurrentRunningVMAFJob(self) -> Optional[VMAFQueueModel]:
        """Get the currently running VMAF job."""
        try:
            runningJobs = self.DatabaseManager.GetVMAFQueueItemsByStatus("Running")
            if runningJobs:
                return runningJobs[0]  # Return the first running job
            return None
        except Exception as e:
            LoggingService.LogException("Exception getting current running VMAF job", e, "VMAFQueueBusinessService", "GetCurrentRunningVMAFJob")
            return None
    
    def GetVMAFQueueStatistics(self) -> Dict[str, Any]:
        """Get VMAF queue statistics."""
        try:
            allJobs = self.DatabaseManager.GetAllVMAFQueueItems()
            
            totalJobs = len(allJobs)
            pendingJobs = len([job for job in allJobs if job.Status == "Pending"])
            runningJobs = len([job for job in allJobs if job.Status == "Running"])
            completedJobs = len([job for job in allJobs if job.Status == "Completed"])
            failedJobs = len([job for job in allJobs if job.Status == "Failed"])
            
            successRate = (completedJobs / totalJobs * 100) if totalJobs > 0 else 0
            
            return {
                "TotalJobs": totalJobs,
                "PendingJobs": pendingJobs,
                "RunningJobs": runningJobs,
                "CompletedJobs": completedJobs,
                "FailedJobs": failedJobs,
                "SuccessRate": successRate
            }
            
        except Exception as e:
            LoggingService.LogException("Exception getting VMAF queue statistics", e, "VMAFQueueBusinessService", "GetVMAFQueueStatistics")
            return {
                "TotalJobs": 0,
                "PendingJobs": 0,
                "RunningJobs": 0,
                "CompletedJobs": 0,
                "FailedJobs": 0,
                "SuccessRate": 0
            }
