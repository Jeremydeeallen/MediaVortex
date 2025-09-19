import os
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
from Models.TranscodeQueueModel import TranscodeQueueModel
from Models.TranscodeAttemptModel import TranscodeAttemptModel
from Models.TranscodeFileModel import TranscodeFileModel
from Models.ProfileThresholdModel import ProfileThresholdModel
from Repositories.DatabaseManager import DatabaseManager
from Services.HandBrakeService import HandBrakeService
from Services.QueueManagementBusinessService import QueueManagementBusinessService
from Services.LoggingService import LoggingService


class TranscodingBusinessService:
    """Orchestrates the transcoding process, coordinates between HandBrakeService and QueueManagementBusinessService."""
    
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None, 
                 HandBrakeServiceInstance: HandBrakeService = None,
                 QueueManagementServiceInstance: QueueManagementBusinessService = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.HandBrakeService = HandBrakeServiceInstance or HandBrakeService()
        self.QueueManagementService = QueueManagementServiceInstance or QueueManagementBusinessService(self.DatabaseManager)
        self.IsRunning = False
        self.CurrentJob = None
    
    def StartTranscoding(self, MaxConcurrentJobs: int = 1) -> Dict[str, Any]:
        """Start the transcoding process."""
        try:
            LoggingService.LogFunctionEntry("StartTranscoding", "TranscodingBusinessService", MaxConcurrentJobs)
            
            if self.IsRunning:
                LoggingService.LogWarning("Transcoding is already running", "TranscodingBusinessService", "StartTranscoding")
                return {"Success": False, "ErrorMessage": "Transcoding is already running"}
            
            # Check HandBrake availability
            if not self.HandBrakeService.CheckAvailability():
                errorMsg = "HandBrake is not available"
                LoggingService.LogError(errorMsg, "TranscodingBusinessService", "StartTranscoding")
                return {"Success": False, "ErrorMessage": errorMsg}
            
            self.IsRunning = True
            LoggingService.LogInfo("Starting transcoding process", "TranscodingBusinessService", "StartTranscoding")
            
            # Start processing jobs
            self.ProcessTranscodingQueue(MaxConcurrentJobs)
            
            return {"Success": True, "Message": "Transcoding process started"}
            
        except Exception as e:
            self.IsRunning = False
            errorMsg = f"Exception starting transcoding: {str(e)}"
            LoggingService.LogException(errorMsg, e, "TranscodingBusinessService", "StartTranscoding")
            return {"Success": False, "ErrorMessage": errorMsg}
    
    def StopTranscoding(self) -> Dict[str, Any]:
        """Stop the transcoding process."""
        try:
            LoggingService.LogFunctionEntry("StopTranscoding", "TranscodingBusinessService")
            
            if not self.IsRunning:
                LoggingService.LogWarning("Transcoding is not running", "TranscodingBusinessService", "StopTranscoding")
                return {"Success": False, "ErrorMessage": "Transcoding is not running"}
            
            self.IsRunning = False
            
            # Mark current job as cancelled if running
            if self.CurrentJob:
                self.CurrentJob.Status = "Cancelled"
                self.DatabaseManager.SaveTranscodeQueueItem(self.CurrentJob)
                LoggingService.LogInfo(f"Cancelled current job: {self.CurrentJob.FileName}", "TranscodingBusinessService", "StopTranscoding")
                self.CurrentJob = None
            
            LoggingService.LogInfo("Transcoding process stopped", "TranscodingBusinessService", "StopTranscoding")
            return {"Success": True, "Message": "Transcoding process stopped"}
            
        except Exception as e:
            errorMsg = f"Exception stopping transcoding: {str(e)}"
            LoggingService.LogException(errorMsg, e, "TranscodingBusinessService", "StopTranscoding")
            return {"Success": False, "ErrorMessage": errorMsg}
    
    def ProcessTranscodingQueue(self, MaxConcurrentJobs: int = 1):
        """Process jobs from the transcoding queue."""
        try:
            LoggingService.LogFunctionEntry("ProcessTranscodingQueue", "TranscodingBusinessService", MaxConcurrentJobs)
            
            while self.IsRunning:
                # Check if queue is empty and populate if needed (only when transcoding is running)
                queueStats = self.QueueManagementService.GetQueueStatistics()
                if queueStats.get("QueueSize", 0) == 0:
                    LoggingService.LogInfo("Queue is empty, attempting to populate from MediaFiles", "TranscodingBusinessService", "ProcessTranscodingQueue")
                    populateResult = self.QueueManagementService.PopulateQueueFromMediaFiles(MaxItems=10)
                    if populateResult.get("ItemsAdded", 0) > 0:
                        friendlyMessage = populateResult.get("Message", f"Populated queue with {populateResult['ItemsAdded']} new items")
                        LoggingService.LogInfo(friendlyMessage, "TranscodingBusinessService", "ProcessTranscodingQueue")
                    else:
                        friendlyMessage = populateResult.get("Message", "No new items to add to queue")
                        LoggingService.LogInfo(friendlyMessage, "TranscodingBusinessService", "ProcessTranscodingQueue")
                        break
                
                # Get next job
                nextJob = self.QueueManagementService.GetNextJob()
                if not nextJob:
                    LoggingService.LogInfo("No jobs available for processing", "TranscodingBusinessService", "ProcessTranscodingQueue")
                    break
                
                # Process the job
                self.CurrentJob = nextJob
                result = self.ProcessTranscodingJob(nextJob)
                
                if not result.get("Success", False):
                    LoggingService.LogError(f"Failed to process job {nextJob.Id}: {result.get('ErrorMessage', 'Unknown error')}", "TranscodingBusinessService", "ProcessTranscodingQueue")
                
                self.CurrentJob = None
                
                # Small delay between jobs
                time.sleep(1)
            
            LoggingService.LogInfo("Transcoding queue processing completed", "TranscodingBusinessService", "ProcessTranscodingQueue")
            
        except Exception as e:
            LoggingService.LogException("Exception processing transcoding queue", e, "TranscodingBusinessService", "ProcessTranscodingQueue")
            self.IsRunning = False
    
    def ProcessTranscodingJob(self, QueueItem: TranscodeQueueModel) -> Dict[str, Any]:
        """Process a single transcoding job."""
        try:
            LoggingService.LogFunctionEntry("ProcessTranscodingJob", "TranscodingBusinessService", QueueItem.Id, QueueItem.FileName)
            
            # Update job status to running
            QueueItem.Status = "Running"
            QueueItem.DateStarted = datetime.now()
            self.DatabaseManager.SaveTranscodeQueueItem(QueueItem)
            
            # Get or create transcode file record
            transcodeFile = self.DatabaseManager.GetTranscodeFileByFilePath(QueueItem.FilePath)
            if not transcodeFile:
                transcodeFile = TranscodeFileModel(
                    FilePath=QueueItem.FilePath,
                    AllQualitiesFailed=False,
                    SuccessfullyTranscoded=False,
                    FirstAttemptDate=datetime.now(),
                    LastAttemptDate=datetime.now(),
                    TotalAttempts=0
                )
                self.DatabaseManager.SaveTranscodeFile(transcodeFile)
            
            # Get profile threshold for this file
            profileThreshold = self.GetProfileThresholdForFile(QueueItem)
            if not profileThreshold:
                errorMsg = f"No profile threshold found for {QueueItem.FileName}"
                LoggingService.LogError(errorMsg, "TranscodingBusinessService", "ProcessTranscodingJob")
                return self.HandleJobFailure(QueueItem, transcodeFile, errorMsg)
            
            # Generate output file path
            outputFilePath = self.GenerateOutputFilePath(QueueItem.FilePath)
            
            # Create transcoding attempt record
            attempt = TranscodeAttemptModel(
                FilePath=QueueItem.FilePath,
                AttemptDate=datetime.now(),
                Quality=20,  # Default quality
                OldSizeBytes=QueueItem.SizeBytes,
                HandbrakeSettings=f"Quality: 20, VideoBitrate: {profileThreshold.VideoBitrateKbps}, AudioBitrate: {profileThreshold.AudioBitrateKbps}",
                AudioBitrateKbps=profileThreshold.AudioBitrateKbps,
                VideoBitrateKbps=profileThreshold.VideoBitrateKbps,
                ProfileName=f"Profile_{profileThreshold.ProfileId}"
            )
            
            # Perform transcoding
            LoggingService.LogInfo(f"Starting transcoding: {QueueItem.FileName} -> {os.path.basename(outputFilePath)}", "TranscodingBusinessService", "ProcessTranscodingJob")
            
            startTime = time.time()
            transcodeResult = self.HandBrakeService.TranscodeFile(
                InputFile=QueueItem.FilePath,
                OutputFile=outputFilePath,
                Quality=20,
                VideoBitrate=profileThreshold.VideoBitrateKbps,
                AudioBitrate=profileThreshold.AudioBitrateKbps
            )
            endTime = time.time()
            
            attempt.TranscodeDurationSeconds = endTime - startTime
            
            if transcodeResult.get("Success", False):
                # Transcoding successful
                if os.path.exists(outputFilePath):
                    newSizeBytes = os.path.getsize(outputFilePath)
                    attempt.NewSizeBytes = newSizeBytes
                    attempt.Success = True
                    attempt.CalculateSizeReduction()
                    
                    # Update transcode file record
                    transcodeFile.SuccessfullyTranscoded = True
                    transcodeFile.SuccessDate = datetime.now()
                    transcodeFile.FinalQuality = 20
                    transcodeFile.FinalSizeBytes = newSizeBytes
                    transcodeFile.FinalFilePath = outputFilePath
                    transcodeFile.TotalAttempts += 1
                    transcodeFile.LastAttemptDate = datetime.now()
                    
                    # Update queue item
                    QueueItem.Status = "Completed"
                    
                    LoggingService.LogInfo(f"Transcoding completed successfully: {QueueItem.FileName} ({attempt.SizeReductionPercent:.1f}% reduction)", "TranscodingBusinessService", "ProcessTranscodingJob")
                else:
                    errorMsg = "Transcoding appeared successful but output file was not created"
                    LoggingService.LogError(errorMsg, "TranscodingBusinessService", "ProcessTranscodingJob")
                    return self.HandleJobFailure(QueueItem, transcodeFile, errorMsg, attempt)
            else:
                # Transcoding failed
                errorMsg = transcodeResult.get("ErrorMessage", "Unknown transcoding error")
                LoggingService.LogError(f"Transcoding failed for {QueueItem.FileName}: {errorMsg}", "TranscodingBusinessService", "ProcessTranscodingJob")
                return self.HandleJobFailure(QueueItem, transcodeFile, errorMsg, attempt)
            
            # Save attempt record
            attemptId = self.DatabaseManager.SaveTranscodeAttempt(attempt)
            attempt.Id = attemptId
            
            # Save updated records
            self.DatabaseManager.SaveTranscodeFile(transcodeFile)
            self.DatabaseManager.SaveTranscodeQueueItem(QueueItem)
            
            result = {
                "Success": True,
                "QueueItemId": QueueItem.Id,
                "AttemptId": attemptId,
                "OutputFile": outputFilePath,
                "SizeReductionPercent": attempt.SizeReductionPercent,
                "Duration": attempt.TranscodeDurationSeconds
            }
            
            return result
            
        except Exception as e:
            errorMsg = f"Exception processing transcoding job: {str(e)}"
            LoggingService.LogException(errorMsg, e, "TranscodingBusinessService", "ProcessTranscodingJob")
            return self.HandleJobFailure(QueueItem, transcodeFile, errorMsg)
    
    def HandleJobFailure(self, QueueItem: TranscodeQueueModel, TranscodeFile: TranscodeFileModel, 
                        ErrorMessage: str, Attempt: TranscodeAttemptModel = None) -> Dict[str, Any]:
        """Handle a failed transcoding job."""
        try:
            LoggingService.LogFunctionEntry("HandleJobFailure", "TranscodingBusinessService", QueueItem.Id, ErrorMessage)
            
            # Create attempt record if not provided
            if not Attempt:
                Attempt = TranscodeAttemptModel(
                    FilePath=QueueItem.FilePath,
                    AttemptDate=datetime.now(),
                    Quality=20,
                    OldSizeBytes=QueueItem.SizeBytes,
                    Success=False,
                    ErrorMessage=ErrorMessage
                )
            else:
                Attempt.Success = False
                Attempt.ErrorMessage = ErrorMessage
            
            # Save attempt record
            attemptId = self.DatabaseManager.SaveTranscodeAttempt(Attempt)
            Attempt.Id = attemptId
            
            # Update transcode file record
            TranscodeFile.TotalAttempts += 1
            TranscodeFile.LastAttemptDate = datetime.now()
            
            # Check if we should mark as all qualities failed
            if TranscodeFile.TotalAttempts >= 3:  # Configurable threshold
                TranscodeFile.AllQualitiesFailed = True
                QueueItem.Status = "Failed"
                LoggingService.LogWarning(f"Marking {QueueItem.FileName} as all qualities failed after {TranscodeFile.TotalAttempts} attempts", "TranscodingBusinessService", "HandleJobFailure")
            else:
                QueueItem.Status = "Pending"  # Retry later
                LoggingService.LogInfo(f"Job {QueueItem.FileName} will be retried (attempt {TranscodeFile.TotalAttempts})", "TranscodingBusinessService", "HandleJobFailure")
            
            # Save updated records
            self.DatabaseManager.SaveTranscodeFile(TranscodeFile)
            self.DatabaseManager.SaveTranscodeQueueItem(QueueItem)
            
            result = {
                "Success": False,
                "ErrorMessage": ErrorMessage,
                "QueueItemId": QueueItem.Id,
                "AttemptId": attemptId,
                "WillRetry": QueueItem.Status == "Pending"
            }
            
            return result
            
        except Exception as e:
            LoggingService.LogException("Exception handling job failure", e, "TranscodingBusinessService", "HandleJobFailure")
            return {"Success": False, "ErrorMessage": f"Exception handling failure: {str(e)}"}
    
    def GetProfileThresholdForFile(self, QueueItem: TranscodeQueueModel) -> Optional[ProfileThresholdModel]:
        """Get the profile threshold for a queue item."""
        try:
            LoggingService.LogFunctionEntry("GetProfileThresholdForFile", "TranscodingBusinessService", QueueItem.FileName)
            
            # Get media file to determine resolution
            mediaFiles = self.DatabaseManager.GetAllMediaFiles()
            mediaFile = next((mf for mf in mediaFiles if mf.FilePath == QueueItem.FilePath), None)
            
            if not mediaFile:
                LoggingService.LogWarning(f"Media file not found for {QueueItem.FileName}", "TranscodingBusinessService", "GetProfileThresholdForFile")
                return None
            
            # Get profile thresholds
            profileThresholds = self.DatabaseManager.GetAllProfileThresholds()
            
            # Find matching threshold
            matchingThresholds = [pt for pt in profileThresholds if pt.Resolution == mediaFile.Resolution]
            
            if matchingThresholds:
                # Use the first matching threshold (could be enhanced with better selection logic)
                threshold = matchingThresholds[0]
                LoggingService.LogInfo(f"Found profile threshold {threshold.ProfileId} for {QueueItem.FileName}", "TranscodingBusinessService", "GetProfileThresholdForFile")
                return threshold
            
            LoggingService.LogWarning(f"No profile threshold found for resolution {mediaFile.Resolution}", "TranscodingBusinessService", "GetProfileThresholdForFile")
            return None
            
        except Exception as e:
            LoggingService.LogException("Exception getting profile threshold", e, "TranscodingBusinessService", "GetProfileThresholdForFile")
            return None
    
    def GenerateOutputFilePath(self, InputFilePath: str) -> str:
        """Generate output file path for transcoded file."""
        try:
            LoggingService.LogFunctionEntry("GenerateOutputFilePath", "TranscodingBusinessService", InputFilePath)
            
            # Get directory and filename
            directory = os.path.dirname(InputFilePath)
            filename = os.path.basename(InputFilePath)
            name, ext = os.path.splitext(filename)
            
            # Create output directory (add _transcoded suffix)
            outputDir = os.path.join(directory, "_transcoded")
            os.makedirs(outputDir, exist_ok=True)
            
            # Generate output filename
            outputFilename = f"{name}_transcoded.mp4"
            outputFilePath = os.path.join(outputDir, outputFilename)
            
            LoggingService.LogInfo(f"Generated output path: {outputFilePath}", "TranscodingBusinessService", "GenerateOutputFilePath")
            return outputFilePath
            
        except Exception as e:
            LoggingService.LogException("Exception generating output file path", e, "TranscodingBusinessService", "GenerateOutputFilePath")
            return ""
    
    def GetTranscodingStatus(self) -> Dict[str, Any]:
        """Get current transcoding status."""
        try:
            LoggingService.LogFunctionEntry("GetTranscodingStatus", "TranscodingBusinessService")
            
            status = {
                "IsRunning": self.IsRunning,
                "CurrentJob": None,
                "QueueStatistics": self.QueueManagementService.GetQueueStatistics(),
                "HandBrakeAvailable": self.HandBrakeService.CheckAvailability()
            }
            
            if self.CurrentJob:
                status["CurrentJob"] = {
                    "Id": self.CurrentJob.Id,
                    "FileName": self.CurrentJob.FileName,
                    "Status": self.CurrentJob.Status,
                    "DateStarted": self.CurrentJob.DateStarted.isoformat() if self.CurrentJob.DateStarted else None
                }
            
            return status
            
        except Exception as e:
            LoggingService.LogException("Exception getting transcoding status", e, "TranscodingBusinessService", "GetTranscodingStatus")
            return {"IsRunning": False, "Error": str(e)}
    
    def PopulateQueueOnly(self, MaxItems: int = 100) -> Dict[str, Any]:
        """Populate the queue without starting transcoding."""
        try:
            LoggingService.LogFunctionEntry("PopulateQueueOnly", "TranscodingBusinessService", MaxItems)
            
            # Use the QueueManagementService to populate the queue
            result = self.QueueManagementService.PopulateQueueFromMediaFiles(MaxItems)
            
            friendlyMessage = result.get("Message", f"Queue populated with {result.get('ItemsAdded', 0)} items (transcoding not started)")
            LoggingService.LogInfo(friendlyMessage, "TranscodingBusinessService", "PopulateQueueOnly")
            return result
            
        except Exception as e:
            errorMsg = f"Exception populating queue: {str(e)}"
            LoggingService.LogException(errorMsg, e, "TranscodingBusinessService", "PopulateQueueOnly")
            return {"Success": False, "ErrorMessage": errorMsg}
    
    def GetTranscodingHistory(self, Limit: int = 100) -> List[Dict[str, Any]]:
        """Get transcoding history."""
        try:
            LoggingService.LogFunctionEntry("GetTranscodingHistory", "TranscodingBusinessService", Limit)
            
            # Get recent transcoding attempts
            attempts = self.DatabaseManager.GetAllTranscodeAttempts()
            
            # Sort by date and limit
            attempts.sort(key=lambda x: x.AttemptDate or datetime.min, reverse=True)
            recentAttempts = attempts[:Limit]
            
            history = []
            for attempt in recentAttempts:
                historyItem = {
                    "Id": attempt.Id,
                    "FilePath": attempt.FilePath,
                    "FileName": os.path.basename(attempt.FilePath),
                    "AttemptDate": attempt.AttemptDate.isoformat() if attempt.AttemptDate else None,
                    "Success": attempt.Success,
                    "Quality": attempt.Quality,
                    "SizeReductionPercent": attempt.SizeReductionPercent,
                    "Duration": attempt.TranscodeDurationSeconds,
                    "ErrorMessage": attempt.ErrorMessage,
                    "ProfileName": attempt.ProfileName
                }
                history.append(historyItem)
            
            LoggingService.LogInfo(f"Retrieved {len(history)} transcoding history items", "TranscodingBusinessService", "GetTranscodingHistory")
            return history
            
        except Exception as e:
            LoggingService.LogException("Exception getting transcoding history", e, "TranscodingBusinessService", "GetTranscodingHistory")
            return []
