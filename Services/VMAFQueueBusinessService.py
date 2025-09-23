import os
import shutil
import threading
from typing import Optional, Dict, Any, List
from datetime import datetime
from Models.VMAFQueueModel import VMAFQueueModel
from Models.VMAFProgressModel import VMAFProgressModel
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
        self.ProcessingThread = None
        self.StopEvent = threading.Event()
    
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
            
            # Automatically start VMAF processing if not already running
            if not self.IsRunning:
                LoggingService.LogInfo(f"Auto-starting VMAF processing for {VMAFQueueItem.FileName}", 
                                     "VMAFQueueBusinessService", "AddToVMAFQueue")
                startResult = self.StartVMAFProcessing()
                if not startResult.get("Success", False):
                    LoggingService.LogError(f"Failed to auto-start VMAF processing: {startResult.get('ErrorMessage', 'Unknown error')}", 
                                          "VMAFQueueBusinessService", "AddToVMAFQueue")
            
            return {
                "Success": True,
                "VMAFQueueId": VMAFQueueId,
                "Message": f"Added {VMAFQueueItem.FileName} to VMAF queue",
                "AutoStarted": not self.IsRunning
            }
            
        except Exception as e:
            errorMsg = f"Exception adding to VMAF queue: {str(e)}"
            LoggingService.LogException(errorMsg, e, "VMAFQueueBusinessService", "AddToVMAFQueue")
            return {"Success": False, "ErrorMessage": errorMsg}
    
    def StartVMAFProcessing(self, MaxConcurrentJobs: int = 1) -> Dict[str, Any]:
        """Start processing VMAF queue asynchronously."""
        try:
            LoggingService.LogFunctionEntry("StartVMAFProcessing", "VMAFQueueBusinessService", MaxConcurrentJobs)
            
            if self.IsRunning:
                LoggingService.LogWarning("VMAF processing is already running", "VMAFQueueBusinessService", "StartVMAFProcessing")
                return {"Success": False, "ErrorMessage": "VMAF processing is already running"}
            
            # Reset stop event and set running flag
            self.StopEvent.clear()
            self.IsRunning = True
            
            LoggingService.LogInfo("Starting VMAF processing in background thread", "VMAFQueueBusinessService", "StartVMAFProcessing")
            
            # Start processing queue in background thread
            self.ProcessingThread = threading.Thread(
                target=self._ProcessVMAFQueueThread,
                args=(MaxConcurrentJobs,),
                daemon=True
            )
            self.ProcessingThread.start()
            
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
            
            # Signal stop event
            self.StopEvent.set()
            self.IsRunning = False
            
            # Mark current job as cancelled if running
            if self.CurrentVMAFJob:
                self.CurrentVMAFJob.Status = "Cancelled"
                self.DatabaseManager.SaveVMAFQueueItem(self.CurrentVMAFJob)
                LoggingService.LogInfo(f"Cancelled current VMAF job: {self.CurrentVMAFJob.FileName}", 
                                     "VMAFQueueBusinessService", "StopVMAFProcessing")
                self.CurrentVMAFJob = None
            
            LoggingService.LogInfo("VMAF processing stop requested", "VMAFQueueBusinessService", "StopVMAFProcessing")
            return {"Success": True, "Message": "VMAF processing stopped"}
            
        except Exception as e:
            errorMsg = f"Exception stopping VMAF processing: {str(e)}"
            LoggingService.LogException(errorMsg, e, "VMAFQueueBusinessService", "StopVMAFProcessing")
            return {"Success": False, "ErrorMessage": errorMsg}
    
    def _ProcessVMAFQueueThread(self, MaxConcurrentJobs: int = 1):
        """Background thread method for processing VMAF queue."""
        try:
            LoggingService.LogInfo("VMAF processing thread started", "VMAFQueueBusinessService", "_ProcessVMAFQueueThread")
            self.ProcessVMAFQueue(MaxConcurrentJobs)
        except Exception as e:
            LoggingService.LogException("Exception in VMAF processing thread", e, "VMAFQueueBusinessService", "_ProcessVMAFQueueThread")
        finally:
            self.IsRunning = False
            LoggingService.LogInfo("VMAF processing thread completed", "VMAFQueueBusinessService", "_ProcessVMAFQueueThread")
    
    def ProcessVMAFQueue(self, MaxConcurrentJobs: int = 1):
        """Process items from the VMAF queue."""
        try:
            LoggingService.LogFunctionEntry("ProcessVMAFQueue", "VMAFQueueBusinessService", MaxConcurrentJobs)
            
            while self.IsRunning and not self.StopEvent.is_set():
                # Get next VMAF job
                nextJob = self.GetNextVMAFJob()
                if not nextJob:
                    LoggingService.LogInfo("No VMAF jobs available for processing", "VMAFQueueBusinessService", "ProcessVMAFQueue")
                    break
                
                # Check if stop was requested
                if self.StopEvent.is_set():
                    LoggingService.LogInfo("VMAF processing stop requested", "VMAFQueueBusinessService", "ProcessVMAFQueue")
                    break
                
                # Process the VMAF job
                self.CurrentVMAFJob = nextJob
                result = self.ProcessVMAFJob(nextJob)
                
                if not result.get("Success", False):
                    LoggingService.LogError(f"Failed to process VMAF job {nextJob.Id}: {result.get('ErrorMessage', 'Unknown error')}", 
                                          "VMAFQueueBusinessService", "ProcessVMAFQueue")
                
                self.CurrentVMAFJob = None
                
                # Small delay between jobs (check stop event during sleep)
                import time
                for _ in range(10):  # 1 second total, check every 100ms
                    if self.StopEvent.is_set():
                        break
                    time.sleep(0.1)
            
            LoggingService.LogInfo("VMAF queue processing completed", "VMAFQueueBusinessService", "ProcessVMAFQueue")
            
        except Exception as e:
            LoggingService.LogException("Exception processing VMAF queue", e, "VMAFQueueBusinessService", "ProcessVMAFQueue")
            self.IsRunning = False
    
    def ProcessVMAFJob(self, VMAFQueueItem: VMAFQueueModel) -> Dict[str, Any]:
        """Process a single VMAF quality analysis job."""
        VMAFProgressItem = None
        try:
            LoggingService.LogFunctionEntry("ProcessVMAFJob", "VMAFQueueBusinessService", 
                                          VMAFQueueItem.Id, VMAFQueueItem.FileName)
            
            # Mark job as running immediately
            VMAFQueueItem.MarkAsRunning()
            self.DatabaseManager.SaveVMAFQueueItem(VMAFQueueItem)
            
            # Create VMAF progress tracking
            VMAFProgressItem = VMAFProgressModel()
            VMAFProgressItem.VMAFQueueId = VMAFQueueItem.Id
            VMAFProgressItem.TranscodeAttemptId = VMAFQueueItem.TranscodeAttemptId
            VMAFProgressItem.MarkAsRunning("Initializing VMAF analysis")
            self.DatabaseManager.SaveVMAFProgress(VMAFProgressItem)
            
            # Perform VMAF analysis
            LoggingService.LogInfo(f"Starting VMAF analysis for {VMAFQueueItem.FileName}", 
                                 "VMAFQueueBusinessService", "ProcessVMAFJob")
            
            # Create progress callback to update VMAFProgress table
            def vmaf_progress_callback(progress_data):
                try:
                    if VMAFProgressItem and 'ProgressPercent' in progress_data:
                        progress_percent = int(progress_data['ProgressPercent'])
                        current_step = f"Analyzing frame {progress_data.get('frame', 0)}"
                        eta = progress_data.get('ETA', 'Unknown')
                        
                        VMAFProgressItem.UpdateProgress(progress_percent, current_step, eta)
                        self.DatabaseManager.SaveVMAFProgress(VMAFProgressItem)
                        
                        LoggingService.LogInfo(f"VMAF Analysis Progress: {progress_data}", 
                                             "VMAFQueueBusinessService", "ProcessVMAFJob")
                except Exception as e:
                    LoggingService.LogException("Exception updating VMAF progress", e, 
                                              "VMAFQueueBusinessService", "ProcessVMAFJob")
            
            VMAFResult = self.FFmpegComparisonService.CreateVMAFComparison(
                VMAFQueueItem.OriginalFilePath,
                VMAFQueueItem.TranscodedFilePath,
                ProgressCallback=vmaf_progress_callback
            )
            
            if VMAFResult.Success:
                # Update progress to completed
                if VMAFProgressItem:
                    VMAFProgressItem.MarkAsCompleted()
                    self.DatabaseManager.SaveVMAFProgress(VMAFProgressItem)
                
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
                
                # Handle file management based on VMAF score
                fileManagementResult = self._HandleFileManagement(VMAFQueueItem, VMAFResult.OverallVMAFScore)
                
                # Remove completed item from queue
                self.DatabaseManager.DeleteVMAFQueueItem(VMAFQueueItem.Id)
                
                return {
                    "Success": True,
                    "VMAFQueueId": VMAFQueueItem.Id,
                    "VMAFScore": VMAFResult.OverallVMAFScore,
                    "PassesThreshold": VMAFQueueItem.PassesQualityThreshold(),
                    "Status": "completed",
                    "FileManagement": fileManagementResult
                }
            else:
                # Update progress to failed
                if VMAFProgressItem:
                    errorMsg = VMAFResult.ErrorMessage or "VMAF analysis failed"
                    VMAFProgressItem.MarkAsFailed(errorMsg)
                    self.DatabaseManager.SaveVMAFProgress(VMAFProgressItem)
                
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
            
            # Update progress to failed
            if VMAFProgressItem:
                VMAFProgressItem.MarkAsFailed(errorMsg)
                self.DatabaseManager.SaveVMAFProgress(VMAFProgressItem)
            
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
            
            # Check for running jobs in VMAFProgress table (more reliable than VMAFQueue)
            runningProgressJobs = self.DatabaseManager.GetVMAFProgressByStatus("Running")
            isRunning = len(runningProgressJobs) > 0
            
            status = {
                "Success": True,
                "IsRunning": isRunning,
                "CurrentVMAFJob": None,
                "QueueStatistics": queueStats
            }
            
            # Get current running VMAF job from VMAFProgress table
            if isRunning and runningProgressJobs:
                runningProgress = runningProgressJobs[0]  # Get the first running job
                
                # Get the corresponding VMAFQueue item
                vmafQueueItem = self.DatabaseManager.GetVMAFQueueItemById(runningProgress.VMAFQueueId)
                if vmafQueueItem:
                    status["CurrentVMAFJob"] = {
                        "Id": vmafQueueItem.Id,
                        "FileName": vmafQueueItem.FileName,
                        "Status": "Running",  # Force to Running since we found it in VMAFProgress
                        "DateStarted": vmafQueueItem.DateStarted.isoformat() if vmafQueueItem.DateStarted and hasattr(vmafQueueItem.DateStarted, 'isoformat') else vmafQueueItem.DateStarted,
                        "TranscodeAttemptId": vmafQueueItem.TranscodeAttemptId,
                        "OriginalFilePath": vmafQueueItem.OriginalFilePath,
                        "TranscodedFilePath": vmafQueueItem.TranscodedFilePath
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
    
    def _HandleFileManagement(self, VMAFQueueItem: VMAFQueueModel, VMAFScore: float) -> Dict[str, Any]:
        """Handle file management operations after successful VMAF analysis."""
        try:
            LoggingService.LogFunctionEntry("_HandleFileManagement", "VMAFQueueBusinessService", 
                                          f"VMAFScore: {VMAFScore:.2f}, File: {VMAFQueueItem.FileName}")
            
            # Handle file management based on VMAF score
            if VMAFScore <= 90.0:
                LoggingService.LogInfo(f"VMAF score {VMAFScore:.2f} <= 90, deleting transcoded file and keeping original for {VMAFQueueItem.FileName}", 
                                     "VMAFQueueBusinessService", "_HandleFileManagement")
                return self._HandleLowQualityFileManagement(VMAFQueueItem, VMAFScore)
            
            LoggingService.LogInfo(f"VMAF score {VMAFScore:.2f} > 90, proceeding with file management for {VMAFQueueItem.FileName}", 
                                 "VMAFQueueBusinessService", "_HandleFileManagement")
            
            originalFilePath = VMAFQueueItem.OriginalFilePath
            transcodedFilePath = VMAFQueueItem.TranscodedFilePath
            
            # Validate file paths
            if not os.path.exists(originalFilePath):
                errorMsg = f"Original file not found: {originalFilePath}"
                LoggingService.LogError(errorMsg, "VMAFQueueBusinessService", "_HandleFileManagement")
                return {"Success": False, "ErrorMessage": errorMsg}
            
            if not os.path.exists(transcodedFilePath):
                errorMsg = f"Transcoded file not found: {transcodedFilePath}"
                LoggingService.LogError(errorMsg, "VMAFQueueBusinessService", "_HandleFileManagement")
                return {"Success": False, "ErrorMessage": errorMsg}
            
            # Step 1: Delete the original file on T: drive
            originalDeleted = False
            try:
                os.remove(originalFilePath)
                originalDeleted = True
                LoggingService.LogInfo(f"Successfully deleted original file: {originalFilePath}", 
                                     "VMAFQueueBusinessService", "_HandleFileManagement")
            except Exception as e:
                errorMsg = f"Failed to delete original file {originalFilePath}: {str(e)}"
                LoggingService.LogError(errorMsg, "VMAFQueueBusinessService", "_HandleFileManagement")
                return {"Success": False, "ErrorMessage": errorMsg}
            
            # Step 2: Move transcoded file from C:\MediaVortex to T:\
            transcodedMoved = False
            try:
                # Extract the directory from original file path (T: drive location)
                originalDir = os.path.dirname(originalFilePath)
                transcodedFileName = os.path.basename(transcodedFilePath)
                newTranscodedPath = os.path.join(originalDir, transcodedFileName)
                
                # Move the file (use shutil.move for cross-drive operations)
                shutil.move(transcodedFilePath, newTranscodedPath)
                transcodedMoved = True
                
                LoggingService.LogInfo(f"Successfully moved transcoded file from {transcodedFilePath} to {newTranscodedPath}", 
                                     "VMAFQueueBusinessService", "_HandleFileManagement")
                
                # Step 3: Clean up the copied source file from C:\MediaVortex\Source\
                sourceCopyPath = self._GetSourceCopyPath(originalFilePath)
                sourceCopyDeleted = False
                if os.path.exists(sourceCopyPath):
                    try:
                        os.remove(sourceCopyPath)
                        sourceCopyDeleted = True
                        LoggingService.LogInfo(f"Successfully deleted source copy file: {sourceCopyPath}", 
                                             "VMAFQueueBusinessService", "_HandleFileManagement")
                    except Exception as e:
                        LoggingService.LogWarning(f"Failed to delete source copy file {sourceCopyPath}: {str(e)}", 
                                                "VMAFQueueBusinessService", "_HandleFileManagement")
                
                # Update the transcoded file path in the database
                VMAFQueueItem.TranscodedFilePath = newTranscodedPath
                self.DatabaseManager.SaveVMAFQueueItem(VMAFQueueItem)
                
            except Exception as e:
                errorMsg = f"Failed to move transcoded file from {transcodedFilePath} to T: drive: {str(e)}"
                LoggingService.LogError(errorMsg, "VMAFQueueBusinessService", "_HandleFileManagement")
                return {"Success": False, "ErrorMessage": errorMsg}
            
            LoggingService.LogInfo(f"File management completed successfully for {VMAFQueueItem.FileName} (VMAF: {VMAFScore:.2f})", 
                                 "VMAFQueueBusinessService", "_HandleFileManagement")
            
            return {
                "Success": True,
                "Action": "completed",
                "VMAFScore": VMAFScore,
                "OriginalFileDeleted": originalDeleted,
                "TranscodedFileMoved": transcodedMoved,
                "SourceCopyDeleted": sourceCopyDeleted if 'sourceCopyDeleted' in locals() else False,
                "NewTranscodedPath": newTranscodedPath if transcodedMoved else None
            }
            
        except Exception as e:
            errorMsg = f"Exception in file management: {str(e)}"
            LoggingService.LogException(errorMsg, e, "VMAFQueueBusinessService", "_HandleFileManagement")
            return {"Success": False, "ErrorMessage": errorMsg}
    
    def _HandleLowQualityFileManagement(self, VMAFQueueItem: VMAFQueueModel, VMAFScore: float) -> Dict[str, Any]:
        """Handle file management for low quality VMAF scores (≤ 90)."""
        try:
            LoggingService.LogFunctionEntry("_HandleLowQualityFileManagement", "VMAFQueueBusinessService", 
                                          f"VMAFScore: {VMAFScore:.2f}, File: {VMAFQueueItem.FileName}")
            
            transcodedFilePath = VMAFQueueItem.TranscodedFilePath
            
            # Validate transcoded file path
            if not os.path.exists(transcodedFilePath):
                errorMsg = f"Transcoded file not found: {transcodedFilePath}"
                LoggingService.LogError(errorMsg, "VMAFQueueBusinessService", "_HandleLowQualityFileManagement")
                return {"Success": False, "ErrorMessage": errorMsg}
            
            # Delete the transcoded file from C:\MediaVortex\
            transcodedDeleted = False
            try:
                os.remove(transcodedFilePath)
                transcodedDeleted = True
                LoggingService.LogInfo(f"Successfully deleted low-quality transcoded file: {transcodedFilePath}", 
                                     "VMAFQueueBusinessService", "_HandleLowQualityFileManagement")
            except Exception as e:
                errorMsg = f"Failed to delete transcoded file {transcodedFilePath}: {str(e)}"
                LoggingService.LogError(errorMsg, "VMAFQueueBusinessService", "_HandleLowQualityFileManagement")
                return {"Success": False, "ErrorMessage": errorMsg}
            
            # Also clean up the source copy from C:\MediaVortex\Source\
            sourceCopyPath = self._GetSourceCopyPath(VMAFQueueItem.OriginalFilePath)
            sourceCopyDeleted = False
            if os.path.exists(sourceCopyPath):
                try:
                    os.remove(sourceCopyPath)
                    sourceCopyDeleted = True
                    LoggingService.LogInfo(f"Successfully deleted source copy file: {sourceCopyPath}", 
                                         "VMAFQueueBusinessService", "_HandleLowQualityFileManagement")
                except Exception as e:
                    LoggingService.LogWarning(f"Failed to delete source copy file {sourceCopyPath}: {str(e)}", 
                                            "VMAFQueueBusinessService", "_HandleLowQualityFileManagement")
            
            LoggingService.LogInfo(f"Low-quality file management completed for {VMAFQueueItem.FileName} (VMAF: {VMAFScore:.2f})", 
                                 "VMAFQueueBusinessService", "_HandleLowQualityFileManagement")
            
            return {
                "Success": True,
                "Action": "low_quality_cleanup",
                "VMAFScore": VMAFScore,
                "TranscodedFileDeleted": transcodedDeleted,
                "SourceCopyDeleted": sourceCopyDeleted,
                "OriginalFileKept": True
            }
            
        except Exception as e:
            errorMsg = f"Exception in low-quality file management: {str(e)}"
            LoggingService.LogException(errorMsg, e, "VMAFQueueBusinessService", "_HandleLowQualityFileManagement")
            return {"Success": False, "ErrorMessage": errorMsg}
    
    def _GetSourceCopyPath(self, OriginalFilePath: str) -> str:
        """Get the path where the source file was copied for transcoding."""
        try:
            # Extract filename from original path (T:\)
            fileName = os.path.basename(OriginalFilePath)
            # Construct the source copy path in C:\MediaVortex\Source\
            sourceCopyPath = os.path.join("C:\\MediaVortex\\Source", fileName)
            return sourceCopyPath
        except Exception as e:
            LoggingService.LogException("Error constructing source copy path", e, "VMAFQueueBusinessService", "_GetSourceCopyPath")
            return ""
