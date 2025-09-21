import os
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
from Models.TranscodeQueueModel import TranscodeQueueModel
from Models.TranscodeAttemptModel import TranscodeAttemptModel
from Models.TranscodeFileModel import TranscodeFileModel
from Models.ProfileThresholdModel import ProfileThresholdModel
from Repositories.DatabaseManager import DatabaseManager
from Services.FFmpegTranscodingService import FFmpegTranscodingService
from Services.FilenameResolutionService import FilenameResolutionService
from Services.FFmpegComparisonService import FFmpegComparisonService
from Services.QueueManagementBusinessService import QueueManagementBusinessService
from Services.LoggingService import LoggingService
from Services.FileManagerService import FileManagerService


class TranscodingBusinessService:
    """Orchestrates the transcoding process, coordinates between FFmpegService and QueueManagementBusinessService."""
    
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None, 
                 FFmpegServiceInstance: FFmpegTranscodingService = None,
                 QueueManagementServiceInstance: QueueManagementBusinessService = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.FFmpegService = FFmpegServiceInstance or FFmpegTranscodingService()
        self.FilenameService = FilenameResolutionService()
        self.QualityService = FFmpegComparisonService()
        self.QueueManagementService = QueueManagementServiceInstance or QueueManagementBusinessService(self.DatabaseManager)
        self.FileManager = FileManagerService()
        self.IsRunning = False
        self.CurrentJob = None
        self.QualityThreshold = 90.0
    
    def StartTranscoding(self, MaxConcurrentJobs: int = 1) -> Dict[str, Any]:
        """Start the transcoding process."""
        try:
            LoggingService.LogFunctionEntry("StartTranscoding", "TranscodingBusinessService", MaxConcurrentJobs)
            
            if self.IsRunning:
                LoggingService.LogWarning("Transcoding is already running", "TranscodingBusinessService", "StartTranscoding")
                return {"Success": False, "ErrorMessage": "Transcoding is already running"}
            
            # Check FFmpeg availability
            if not self.FFmpegService.CheckAvailability():
                errorMsg = "FFmpeg is not available"
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
                    LoggingService.LogInfo("Queue is empty, stopping transcoding (auto-population disabled for testing)", "TranscodingBusinessService", "ProcessTranscodingQueue")
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
            
            # Validate file exists on disk before starting transcoding (lazy cleanup)
            if not self.FileManager.ValidateFileExists(QueueItem.FilePath):
                errorMsg = f"Source file no longer exists: {QueueItem.FileName} at {QueueItem.FilePath}"
                LoggingService.LogWarning(errorMsg, "TranscodingBusinessService", "ProcessTranscodingJob")
                
                # Mark job as failed and remove from queue
                QueueItem.Status = "Failed"
                QueueItem.ErrorMessage = errorMsg
                QueueItem.DateCompleted = datetime.now()
                self.DatabaseManager.SaveTranscodeQueueItem(QueueItem)
                
                # Clean up the media file record since it doesn't exist
                try:
                    mediaFile = self.DatabaseManager.GetMediaFileByPath(QueueItem.FilePath)
                    if mediaFile:
                        self.DatabaseManager.DeleteMediaFile(mediaFile.Id)
                        LoggingService.LogInfo(f"Cleaned up missing media file from database: {QueueItem.FileName}", "TranscodingBusinessService", "ProcessTranscodingJob")
                except Exception as cleanupError:
                    LoggingService.LogException("Error cleaning up missing media file from database", cleanupError, "TranscodingBusinessService", "ProcessTranscodingJob")
                
                return {"Success": False, "ErrorMessage": errorMsg}
            
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
            
            # Get quality settings for this file from MediaFiles table
            qualitySettings = self.GetQualitySettingsForFile(QueueItem)
            if not qualitySettings:
                errorMsg = f"Failed to retrieve quality settings from ProfileThresholds for {QueueItem.FileName}. Check that ProfileThresholds table has all required settings for the assigned profile and resolution."
                LoggingService.LogError(errorMsg, "TranscodingBusinessService", "ProcessTranscodingJob")
                return self.HandleJobFailure(QueueItem, transcodeFile, errorMsg)
            
            # Validate quality settings before starting transcoding
            validationResult = self.ValidateQualitySettings(qualitySettings, QueueItem.FileName)
            if not validationResult.get("Success", False):
                errorMsg = f"Quality settings validation failed for {QueueItem.FileName}: {validationResult.get('ErrorMessage', 'Unknown validation error')}"
                LoggingService.LogError(errorMsg, "TranscodingBusinessService", "ProcessTranscodingJob")
                return self.HandleJobFailure(QueueItem, transcodeFile, errorMsg)
            
            # Use the integrated transcoding workflow
            workflowResult = self.ProcessTranscodingWorkflow(QueueItem, qualitySettings)
            
            if workflowResult.get("Success", False):
                # Workflow completed successfully
                transcodeAttempt = workflowResult.get("TranscodeAttempt")
                outputFilePath = workflowResult.get("OutputFilePath")
                vmafScore = workflowResult.get("VMAFScore", 0)
                
                # Update transcode file record
                transcodeFile.SuccessfullyTranscoded = True
                transcodeFile.SuccessDate = datetime.now()
                transcodeFile.FinalQuality = qualitySettings.get("VideoBitrateKbps", 2000)
                transcodeFile.FinalSizeBytes = transcodeAttempt.NewSizeBytes if transcodeAttempt else 0
                transcodeFile.FinalFilePath = outputFilePath
                transcodeFile.TotalAttempts += 1
                transcodeFile.LastAttemptDate = datetime.now()
                
                # Update queue item
                QueueItem.Status = "Completed"
                
                
                # Save updated records
                self.DatabaseManager.SaveTranscodeFile(transcodeFile)
                self.DatabaseManager.SaveTranscodeQueueItem(QueueItem)
                
                result = {
                    "Success": True,
                    "QueueItemId": QueueItem.Id,
                    "AttemptId": transcodeAttempt.Id if transcodeAttempt else None,
                    "OutputFile": outputFilePath,
                    "VMAFScore": vmafScore,
                    "Status": "completed"
                }
                
                return result
            else:
                # Workflow failed
                errorMsg = workflowResult.get("ErrorMessage", "Unknown workflow error")
                return self.HandleJobFailure(QueueItem, transcodeFile, errorMsg)
            
        except Exception as e:
            errorMsg = f"Exception processing transcoding job: {str(e)}"
            LoggingService.LogException(errorMsg, e, "TranscodingBusinessService", "ProcessTranscodingJob")
            return self.HandleJobFailure(QueueItem, transcodeFile, errorMsg)
    
    def HandleJobFailure(self, QueueItem: TranscodeQueueModel, TranscodeFile: TranscodeFileModel, 
                        ErrorMessage: str, Attempt: TranscodeAttemptModel = None) -> Dict[str, Any]:
        """Handle a failed transcoding job. For configuration errors, removes item from queue permanently."""
        try:
            LoggingService.LogFunctionEntry("HandleJobFailure", "TranscodingBusinessService", QueueItem.Id, ErrorMessage)
            
            # Determine if this is a configuration error that should not be retried
            isConfigurationError = any(keyword in ErrorMessage.lower() for keyword in [
                'missing required', 'no quality settings', 'no assignedprofile', 'no resolution', 
                'no codec', 'profilethresholds', 'configuration', 'settings'
            ])
            
            # Create attempt record if not provided
            if not Attempt:
                Attempt = TranscodeAttemptModel(
                    FilePath=QueueItem.FilePath,
                    AttemptDate=datetime.now(),
                    Quality=0,  # No quality for failed attempts
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
            
            # Handle configuration errors differently - remove from queue permanently
            if isConfigurationError:
                TranscodeFile.AllQualitiesFailed = True
                QueueItem.Status = "Failed"
                LoggingService.LogError(f"Configuration error for {QueueItem.FileName}: {ErrorMessage}. Removing from queue permanently.", "TranscodingBusinessService", "HandleJobFailure")
            else:
                # Check if we should mark as all qualities failed for non-configuration errors
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
                "WillRetry": QueueItem.Status == "Pending",
                "IsConfigurationError": isConfigurationError
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
    
    def ValidateQualitySettings(self, QualitySettings: Dict[str, Any], FileName: str) -> Dict[str, Any]:
        """Validate that all required quality settings are present and valid."""
        try:
            LoggingService.LogFunctionEntry("ValidateQualitySettings", "TranscodingBusinessService", FileName)
            
            # Required settings that must be present
            required_settings = ['VideoBitrateKbps', 'AudioBitrateKbps', 'TargetResolution', 'Codec', 'Quality']
            missing_settings = []
            invalid_settings = []
            
            # Check for missing settings
            for setting in required_settings:
                if setting not in QualitySettings or QualitySettings[setting] is None:
                    missing_settings.append(setting)
            
            if missing_settings:
                error_msg = f"Missing required quality settings: {', '.join(missing_settings)}"
                LoggingService.LogError(error_msg, "TranscodingBusinessService", "ValidateQualitySettings")
                return {"Success": False, "ErrorMessage": error_msg}
            
            # Validate VideoBitrateKbps
            videoBitrate = QualitySettings['VideoBitrateKbps']
            if not isinstance(videoBitrate, (int, float)) or videoBitrate <= 0:
                invalid_settings.append(f"VideoBitrateKbps must be a positive number, got: {videoBitrate}")
            elif videoBitrate < 100:
                invalid_settings.append(f"VideoBitrateKbps too low: {videoBitrate}k (minimum 100k)")
            elif videoBitrate > 50000:
                invalid_settings.append(f"VideoBitrateKbps too high: {videoBitrate}k (maximum 50000k)")
            
            # Validate AudioBitrateKbps
            audioBitrate = QualitySettings['AudioBitrateKbps']
            if not isinstance(audioBitrate, (int, float)) or audioBitrate <= 0:
                invalid_settings.append(f"AudioBitrateKbps must be a positive number, got: {audioBitrate}")
            elif audioBitrate < 32:
                invalid_settings.append(f"AudioBitrateKbps too low: {audioBitrate}k (minimum 32k)")
            elif audioBitrate > 512:
                invalid_settings.append(f"AudioBitrateKbps too high: {audioBitrate}k (maximum 512k)")
            
            # Validate TargetResolution
            targetResolution = QualitySettings['TargetResolution']
            validResolutions = ['360p', '480p', '720p', '1080p', '2160p', 'original']
            if targetResolution not in validResolutions:
                invalid_settings.append(f"TargetResolution must be one of {validResolutions}, got: {targetResolution}")
            
            # Validate Codec
            codec = QualitySettings['Codec']
            validCodecs = ['libx264', 'libx265', 'libvpx', 'libvpx-vp9', 'libaom-av1']
            if codec not in validCodecs:
                invalid_settings.append(f"Codec must be one of {validCodecs}, got: {codec}")
            
            # Validate Quality (CRF)
            quality = QualitySettings['Quality']
            if not isinstance(quality, (int, float)):
                invalid_settings.append(f"Quality must be a number, got: {quality}")
            elif quality < 0:
                invalid_settings.append(f"Quality too low: {quality} (minimum 0)")
            elif quality > 51:
                invalid_settings.append(f"Quality too high: {quality} (maximum 51)")
            
            if invalid_settings:
                error_msg = f"Invalid quality settings: {'; '.join(invalid_settings)}"
                LoggingService.LogError(error_msg, "TranscodingBusinessService", "ValidateQualitySettings")
                return {"Success": False, "ErrorMessage": error_msg}
            
            LoggingService.LogInfo(f"Quality settings validation passed for {FileName}", "TranscodingBusinessService", "ValidateQualitySettings")
            return {"Success": True, "Message": "Quality settings validation passed"}
            
        except Exception as e:
            error_msg = f"Exception during quality settings validation: {str(e)}"
            LoggingService.LogException(error_msg, e, "TranscodingBusinessService", "ValidateQualitySettings")
            return {"Success": False, "ErrorMessage": error_msg}
    
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
            
            # Get queue statistics
            queueStats = self.QueueManagementService.GetQueueStatistics()
            isRunning = queueStats.get("RunningJobs", 0) > 0
            
            status = {
                "IsRunning": isRunning,
                "IsTranscoding": isRunning,  # Add this for UI compatibility
                "CurrentJob": None,
                "QueueStatistics": queueStats,
                "FFmpegAvailable": self.FFmpegService.CheckAvailability()
            }
            
            # Get current running job from database
            if isRunning:
                currentJob = self._GetCurrentRunningJob()
                if currentJob:
                    # Get the latest transcoding attempt for this job
                    latestAttempt = self._GetLatestTranscodeAttempt(currentJob.FilePath)
                    progressInfo = None
                    
                    if latestAttempt:
                        # Get progress information from TranscodeProgress table
                        progressInfo = self.DatabaseManager.GetLatestTranscodeProgress(latestAttempt.Id)
                    
                    status["CurrentJob"] = {
                        "Id": currentJob.Id,
                        "FileName": currentJob.FileName,
                        "Status": currentJob.Status,
                        "DateStarted": currentJob.DateStarted if currentJob.DateStarted else None,
                        "FilePath": currentJob.FilePath,
                        "Progress": progressInfo
                    }
            
            return status
            
        except Exception as e:
            LoggingService.LogException("Exception getting transcoding status", e, "TranscodingBusinessService", "GetTranscodingStatus")
            return {"IsRunning": False, "IsTranscoding": False, "Error": str(e)}

    def _GetCurrentRunningJob(self) -> Optional[TranscodeQueueModel]:
        """Get the currently running job from the database."""
        try:
            # Get the first running job from the queue
            runningJobs = self.DatabaseManager.GetTranscodeQueueItemsByStatus("Running")
            if runningJobs:
                return runningJobs[0]  # Return the first running job
            return None
        except Exception as e:
            LoggingService.LogException("Exception getting current running job", e, "TranscodingBusinessService", "_GetCurrentRunningJob")
            return None
    
    def _GetLatestTranscodeAttempt(self, FilePath: str) -> Optional[TranscodeAttemptModel]:
        """Get the latest transcoding attempt for a file."""
        try:
            attempts = self.DatabaseManager.GetTranscodeAttemptsByFilePath(FilePath)
            if attempts:
                # Return the most recent attempt (assuming they're ordered by date)
                return attempts[0]
            return None
        except Exception as e:
            LoggingService.LogException("Exception getting latest transcode attempt", e, "TranscodingBusinessService", "_GetLatestTranscodeAttempt")
            return None
    
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
    
    def ProcessTranscodingWorkflow(self, QueueItem: TranscodeQueueModel, QualitySettings: Dict[str, Any]) -> Dict[str, Any]:
        """Process complete transcoding workflow with quality scoring."""
        try:
            fileName = os.path.basename(QueueItem.FilePath)
            LoggingService.LogInfo(f"Transcode {fileName} started", "TranscodingBusinessService", "ProcessTranscodingWorkflow")
            
            # Setup transcoding directories
            directoryResult = self.FileManager.SetupTranscodingDirectories()
            if not directoryResult.get('Success', False):
                LoggingService.LogError(f"Failed to setup transcoding directories for {fileName}", "TranscodingBusinessService", "ProcessTranscodingWorkflow")
                return {
                    'Success': False,
                    'Status': 'failed',
                    'ErrorMessage': 'Failed to setup transcoding directories'
                }
            
            # Copy file to c:\MediaVortex\Source for processing
            sourceFilePath = os.path.join(directoryResult['MediaVortexSourceDir'], os.path.basename(QueueItem.FilePath))
            LoggingService.LogInfo(f"File copy {fileName} to {sourceFilePath} started", "TranscodingBusinessService", "ProcessTranscodingWorkflow")
            copyResult = self.FileManager.CopyFile(QueueItem.FilePath, sourceFilePath)
            if not copyResult.get('Success', False):
                LoggingService.LogError(f"File copy {fileName} failed: {copyResult.get('ErrorMessage', 'Unknown error')}", "TranscodingBusinessService", "ProcessTranscodingWorkflow")
                return {
                    'Success': False,
                    'Status': 'failed',
                    'ErrorMessage': f'Failed to copy file to source directory: {copyResult.get("ErrorMessage", "Unknown error")}'
                }
            LoggingService.LogInfo(f"File copy {fileName} complete", "TranscodingBusinessService", "ProcessTranscodingWorkflow")
            
            # Generate output file path in c:\MediaVortex\<filename>
            outputFilePath = self.FilenameService.GenerateOutputFilePath(
                sourceFilePath,
                directoryResult['MediaVortexTempDir'],
                QualitySettings.get('TargetResolution', '720p')
            )
            
            # Generate FFmpeg command(s) to store in attempt
            useMultiPass = QualitySettings.get('UseMultiPass', False)
            
            if useMultiPass:
                # Build both Pass 1 and Pass 2 commands for multi-pass encoding
                pass1Args = self.FFmpegService.BuildFFmpegMultiPassCommand(sourceFilePath, outputFilePath, QualitySettings, pass_number=1)
                pass2Args = self.FFmpegService.BuildFFmpegMultiPassCommand(sourceFilePath, outputFilePath, QualitySettings, pass_number=2)
                
                if pass1Args and pass2Args:
                    pass1Command = ' '.join(pass1Args)
                    pass2Command = ' '.join(pass2Args)
                    ffmpegCommand = f"PASS 1: {pass1Command}\nPASS 2: {pass2Command}"
                    LoggingService.LogInfo(f"Built multi-pass commands for {fileName}", "TranscodingBusinessService", "ProcessTranscodingWorkflow")
                else:
                    ffmpegCommand = "Failed to build multi-pass commands"
                    LoggingService.LogError(f"Failed to build multi-pass commands for {fileName}", "TranscodingBusinessService", "ProcessTranscodingWorkflow")
            else:
                # Build single-pass command
                ffmpegArgs = self.FFmpegService.BuildFFmpegCommand(sourceFilePath, outputFilePath, QualitySettings)
                ffmpegCommand = ' '.join(ffmpegArgs) if ffmpegArgs else None
            
            # Create initial TranscodeAttempt record with basic info including FFmpeg command
            initialAttempt = TranscodeAttemptModel(
                FilePath=QueueItem.FilePath,
                AttemptDate=datetime.now(),
                Quality=QualitySettings.get('Quality', 0),
                OldSizeBytes=os.path.getsize(QueueItem.FilePath) if os.path.exists(QueueItem.FilePath) else 0,
                AudioBitrateKbps=QualitySettings.get('AudioBitrateKbps'),
                VideoBitrateKbps=QualitySettings.get('VideoBitrateKbps'),
                ProfileName=QualitySettings.get('ProfileName'),
                FfpmpegCommand=ffmpegCommand,
                Success=False  # Will be updated after transcode
            )
            
            # Save initial attempt to database
            attemptId = self.DatabaseManager.SaveTranscodeAttempt(initialAttempt)
            initialAttempt.Id = attemptId  # Set the ID for subsequent updates
            LoggingService.LogInfo(f"Created initial TranscodeAttempt record with ID: {attemptId} for {fileName}", "TranscodingBusinessService", "ProcessTranscodingWorkflow")
            
            # Transcode video from source file with progress monitoring
            LoggingService.LogInfo(f"Starting transcode {fileName} with quality settings: {QualitySettings}", "TranscodingBusinessService", "ProcessTranscodingWorkflow")
            
            # Check if multi-pass encoding should be used (default: False for now)
            useMultiPass = QualitySettings.get('UseMultiPass', False)
            
            if useMultiPass:
                self._UpdateProgressPhase(initialAttempt.Id, "Multi-Pass Transcoding", f"Starting two-pass transcode of {fileName}")
            else:
                self._UpdateProgressPhase(initialAttempt.Id, "Transcoding", f"Starting single-pass transcode of {fileName}")
            
            # Create progress callback to update database
            def progress_callback(progress_data):
                LoggingService.LogInfo(f"PROGRESS CALLBACK CALLED with data: {progress_data}", "TranscodingBusinessService", "ProcessTranscodingWorkflow")
                try:
                    self._UpdateTranscodeProgress(initialAttempt.Id, progress_data)
                    LoggingService.LogInfo("PROGRESS CALLBACK COMPLETED SUCCESSFULLY", "TranscodingBusinessService", "ProcessTranscodingWorkflow")
                except Exception as e:
                    LoggingService.LogException("Exception in progress callback", e, "TranscodingBusinessService", "ProcessTranscodingWorkflow")
            
            transcodeResult = self.FFmpegService.TranscodeVideo(
                sourceFilePath,
                outputFilePath,
                QualitySettings,
                progress_callback,
                useMultiPass
            )
            
            
            if not transcodeResult.get('Success', False):
                # Transcode failed - update attempt with error
                initialAttempt.Success = False
                initialAttempt.ErrorMessage = transcodeResult.get('ErrorMessage', 'Transcoding failed')
                self.DatabaseManager.SaveTranscodeAttempt(initialAttempt)
                
                # Store FFmpeg output for debugging failed transcodes
                FFmpegOutput = transcodeResult.get('AllOutput', '')
                if FFmpegOutput:
                    if useMultiPass:
                        # For multi-pass failures, store output for the failed phase
                        self._UpdateFFmpegOutput(initialAttempt.Id, "Pass 2: Encoding", FFmpegOutput)
                    else:
                        # For single-pass failures, store output for the transcoding phase
                        self._UpdateFFmpegOutput(initialAttempt.Id, "Transcoding", FFmpegOutput)
                
                self._UpdateProgressPhase(initialAttempt.Id, "Failed", f"Transcode failed: {transcodeResult.get('ErrorMessage', 'Transcoding failed')}")
                LoggingService.LogError(f"Transcode {fileName} failed: {transcodeResult.get('ErrorMessage', 'Transcoding failed')}", "TranscodingBusinessService", "ProcessTranscodingWorkflow")
                return {
                    'Success': False,
                    'Status': 'failed',
                    'ErrorMessage': transcodeResult.get('ErrorMessage', 'Transcoding failed'),
                    'TranscodeAttemptId': attemptId
                }
            
            # Transcode succeeded - update attempt with transcoding results
            initialAttempt.Success = True
            initialAttempt.NewSizeBytes = os.path.getsize(outputFilePath) if os.path.exists(outputFilePath) else 0
            initialAttempt.TranscodeDurationSeconds = transcodeResult.get('Duration', 0.0)
            initialAttempt.CalculateSizeReduction()
            self.DatabaseManager.SaveTranscodeAttempt(initialAttempt)
            
            # Store FFmpeg output in progress table
            FFmpegOutput = transcodeResult.get('AllOutput', '')
            if FFmpegOutput:
                if useMultiPass:
                    # For multi-pass, we need to store output for each phase
                    # The output contains both passes, so we'll store it for the final phase
                    self._UpdateFFmpegOutput(initialAttempt.Id, "Pass 2: Encoding", FFmpegOutput)
                else:
                    # For single-pass, store output for the transcoding phase
                    self._UpdateFFmpegOutput(initialAttempt.Id, "Transcoding", FFmpegOutput)
            
            LoggingService.LogInfo(f"Transcode {fileName} complete", "TranscodingBusinessService", "ProcessTranscodingWorkflow")
            self._UpdateProgressPhase(initialAttempt.Id, "Transcoding Complete", f"Transcode of {fileName} completed successfully")
            
            # Perform quality scoring
            LoggingService.LogInfo(f"Starting quality scoring for {fileName}", "TranscodingBusinessService", "ProcessTranscodingWorkflow")
            self._UpdateProgressPhase(initialAttempt.Id, "Testing Quality", f"Starting VMAF quality analysis for {fileName}")
            qualityResult = self.QualityService.CreateVMAFComparison(
                sourceFilePath,
                outputFilePath,
                os.path.join(directoryResult['MediaVortexTempDir'], "VMAFResults.json")
            )
            
            if not qualityResult.Success:
                # Quality scoring failed - update attempt with error
                initialAttempt.ErrorMessage = 'Quality scoring failed'
                self.DatabaseManager.SaveTranscodeAttempt(initialAttempt)
                self._UpdateProgressPhase(initialAttempt.Id, "Quality Test Failed", f"VMAF quality analysis failed for {fileName}")
                LoggingService.LogError(f"Quality scoring failed for {fileName}", "TranscodingBusinessService", "ProcessTranscodingWorkflow")
                return {
                    'Success': False,
                    'Status': 'failed',
                    'ErrorMessage': 'Quality scoring failed',
                    'TranscodeAttemptId': attemptId
                }
            
            # Quality scoring succeeded - update attempt with VMAF score
            initialAttempt.VMAF = qualityResult.VMAFScore
            self.DatabaseManager.SaveTranscodeAttempt(initialAttempt)
            
            LoggingService.LogInfo(f"Quality scoring complete for {fileName}: VMAF Score = {qualityResult.VMAFScore:.2f}", "TranscodingBusinessService", "ProcessTranscodingWorkflow")
            self._UpdateProgressPhase(initialAttempt.Id, "Quality Test Complete", f"VMAF score: {qualityResult.VMAFScore:.2f} for {fileName}")
            
            # Check quality threshold
            if qualityResult.VMAFScore >= self.QualityThreshold:
                LoggingService.LogInfo(f"Quality threshold passed for {fileName} (VMAF: {qualityResult.VMAFScore:.2f} >= {self.QualityThreshold})", "TranscodingBusinessService", "ProcessTranscodingWorkflow")
                self._UpdateProgressPhase(initialAttempt.Id, "Finalizing", f"Quality passed ({qualityResult.VMAFScore:.2f}), replacing original file")
                # Quality passed - process file replacement
                replacementResult = self.ProcessFileReplacement(
                    QueueItem.FilePath,  # Original file path
                    outputFilePath,      # Transcoded file path
                    initialAttempt,      # Use existing TranscodeAttempt
                    qualityResult.VMAFScore,
                    sourceFilePath      # Source file to clean up
                )
                
                if replacementResult.get('Success', False):
                    LoggingService.LogInfo(f"File replacement complete for {fileName}", "TranscodingBusinessService", "ProcessTranscodingWorkflow")
                    LoggingService.LogInfo(f"Transcode {fileName} completed successfully (VMAF: {qualityResult.VMAFScore:.2f})", "TranscodingBusinessService", "ProcessTranscodingWorkflow")
                    self._UpdateProgressPhase(initialAttempt.Id, "Completed", f"Transcode completed successfully (VMAF: {qualityResult.VMAFScore:.2f})")
                    return {
                        'Success': True,
                        'Status': 'completed',
                        'VMAFScore': qualityResult.VMAFScore,
                        'OutputFilePath': outputFilePath,
                        'TranscodeAttempt': replacementResult.get('TranscodeAttempt')
                    }
                else:
                    LoggingService.LogError(f"File replacement failed for {fileName}: {replacementResult.get('ErrorMessage', 'Unknown error')}", "TranscodingBusinessService", "ProcessTranscodingWorkflow")
                    self._UpdateProgressPhase(initialAttempt.Id, "Failed", f"File replacement failed: {replacementResult.get('ErrorMessage', 'Unknown error')}")
                    return replacementResult
            else:
                # Quality failed
                LoggingService.LogWarning(f"Quality threshold failed for {fileName} (VMAF: {qualityResult.VMAFScore:.2f} < {self.QualityThreshold})", "TranscodingBusinessService", "ProcessTranscodingWorkflow")
                self._UpdateProgressPhase(initialAttempt.Id, "Failed", f"Quality threshold failed (VMAF: {qualityResult.VMAFScore:.2f} < {self.QualityThreshold})")
                return {
                    'Success': False,
                    'Status': 'failed',
                    'VMAFScore': qualityResult.VMAFScore,
                    'ErrorMessage': f'Quality score {qualityResult.VMAFScore} below threshold {self.QualityThreshold}'
                }
                
        except Exception as e:
            LoggingService.LogException("Exception in transcoding workflow", e, "TranscodingBusinessService", "ProcessTranscodingWorkflow")
            return {
                'Success': False,
                'Status': 'failed',
                'ErrorMessage': f'Workflow exception: {str(e)}'
            }

    def _UpdateTranscodeProgress(self, AttemptId: int, ProgressData: Dict[str, Any], FFmpegOutput: str = "") -> None:
        """Update transcoding progress in the database."""
        try:
            # Extract progress information
            Frame = ProgressData.get('frame', 0)
            FPS = ProgressData.get('fps', 0)
            Bitrate = ProgressData.get('bitrate', '0kbits/s')
            Time = ProgressData.get('time', '00:00:00')
            Speed = ProgressData.get('speed', '0x')
            
            # Get FFmpeg output from progress data if available
            if 'FFmpegOutput' in ProgressData:
                FFmpegOutput = ProgressData['FFmpegOutput']
            
            # Calculate percentage based on frame count (more accurate than duration)
            ProgressPercent = 0
            TotalFrames = ProgressData.get('total_frames', 0)
            if TotalFrames > 0 and Frame > 0:
                ProgressPercent = min(95, int((Frame / TotalFrames) * 100))
            elif 'duration' in ProgressData and ProgressData['duration'] > 0:
                # Fallback to duration-based calculation if frame count not available
                CurrentTime = self._ParseTimeToSeconds(Time)
                ProgressPercent = min(95, int((CurrentTime / ProgressData['duration']) * 100))
            
            # Determine current phase based on progress data
            CurrentPhase = "Transcoding"
            if 'pass' in ProgressData:
                if ProgressData['pass'] == 1:
                    CurrentPhase = "Pass 1: Analysis"
                elif ProgressData['pass'] == 2:
                    CurrentPhase = "Pass 2: Encoding"
            
            # Log progress information
            LoggingService.LogInfo(f"Transcode progress (ID: {AttemptId}) - Phase: {CurrentPhase}, Progress: {ProgressPercent}%, Frame: {Frame}, FPS: {FPS}, Bitrate: {Bitrate}, Time: {Time}, Speed: {Speed}", "TranscodingBusinessService", "_UpdateTranscodeProgress")
            
            # Save progress to database
            LoggingService.LogInfo(f"WRITING TO DATABASE - AttemptId: {AttemptId}, Phase: {CurrentPhase}, Progress: {ProgressPercent}%", "TranscodingBusinessService", "_UpdateTranscodeProgress")
            Result = self.DatabaseManager.SaveTranscodeProgress(
                AttemptId,
                CurrentPhase,
                ProgressPercent,
                Frame,
                TotalFrames,  # TotalFrameCount
                FPS,
                Bitrate,
                Time,
                Speed,
                FFmpegOutput
            )
            LoggingService.LogInfo(f"DATABASE WRITE COMPLETED - Result: {Result}", "TranscodingBusinessService", "_UpdateTranscodeProgress")
            
        except Exception as e:
            LoggingService.LogException("Exception updating transcode progress", e, "TranscodingBusinessService", "_UpdateTranscodeProgress")
    
    def _UpdateFFmpegOutput(self, AttemptId: int, Phase: str, FFmpegOutput: str) -> None:
        """Update FFmpeg output for a specific phase of transcoding."""
        try:
            LoggingService.LogInfo(f"Updating FFmpeg output for attempt {AttemptId}, phase {Phase}", "TranscodingBusinessService", "_UpdateFFmpegOutput")
            
            # Get current progress for this phase
            CurrentProgress = self.DatabaseManager.GetTranscodeProgressByPhase(AttemptId, Phase)
            
            if CurrentProgress:
                # Update existing progress with FFmpeg output
                self.DatabaseManager.SaveTranscodeProgress(
                    AttemptId,
                    Phase,
                    CurrentProgress.get('ProgressPercent', 0),
                    CurrentProgress.get('CurrentFrame', 0),
                    CurrentProgress.get('TotalFrameCount', 0),  # TotalFrameCount
                    CurrentProgress.get('CurrentFPS', 0.0),
                    CurrentProgress.get('CurrentBitrate', '0kbits/s'),
                    CurrentProgress.get('CurrentTime', '00:00:00'),
                    CurrentProgress.get('CurrentSpeed', '0x'),
                    FFmpegOutput
                )
                LoggingService.LogInfo(f"Updated FFmpeg output for attempt {AttemptId}, phase {Phase}", "TranscodingBusinessService", "_UpdateFFmpegOutput")
            else:
                LoggingService.LogWarning(f"No progress record found for attempt {AttemptId}, phase {Phase}", "TranscodingBusinessService", "_UpdateFFmpegOutput")
                
        except Exception as e:
            LoggingService.LogException("Exception updating FFmpeg output", e, "TranscodingBusinessService", "_UpdateFFmpegOutput")
    
    def _UpdateProgressPhase(self, AttemptId: int, Phase: str, Message: str = None) -> None:
        """Update the current phase of the transcoding process."""
        try:
            if Message:
                LoggingService.LogInfo(f"Progress update (ID: {AttemptId}) - Phase: {Phase}, Message: {Message}", "TranscodingBusinessService", "_UpdateProgressPhase")
            else:
                LoggingService.LogInfo(f"Progress update (ID: {AttemptId}) - Phase: {Phase}", "TranscodingBusinessService", "_UpdateProgressPhase")
            
            # Note: We could add a ProgressPhase column to the TranscodeAttempts table if needed
            # For now, we'll just log the phase information for monitoring
            
        except Exception as e:
            LoggingService.LogException("Exception updating progress phase", e, "TranscodingBusinessService", "_UpdateProgressPhase")
    
    def _ParseTimeToSeconds(self, TimeStr: str) -> float:
        """Parse time string (HH:MM:SS.mmm) to seconds."""
        try:
            if not TimeStr or TimeStr == '00:00:00':
                return 0.0
            
            # Handle format like "00:01:23.45"
            parts = TimeStr.split(':')
            if len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = float(parts[2])
                return hours * 3600 + minutes * 60 + seconds
            return 0.0
        except:
            return 0.0
    
    def ProcessFileReplacement(self, OriginalFilePath: str, TranscodedFilePath: str, 
                              TranscodeAttempt: TranscodeAttemptModel, VMAFScore: float, 
                              SourceFilePath: str = None) -> Dict[str, Any]:
        """Process file replacement when quality score passes threshold."""
        try:
            LoggingService.LogFunctionEntry("ProcessFileReplacement", "TranscodingBusinessService")
            
            # Validate files exist
            if not self.FileManager.ValidateFileExists(OriginalFilePath):
                return {
                    'Success': False,
                    'Status': 'failed',
                    'ErrorMessage': 'Original file not found'
                }
            
            if not self.FileManager.ValidateFileExists(TranscodedFilePath):
                return {
                    'Success': False,
                    'Status': 'failed',
                    'ErrorMessage': 'Transcoded file not found'
                }
            
            # Create TranscodeAttempt if not provided
            if TranscodeAttempt is None:
                TranscodeAttempt = TranscodeAttemptModel(
                    FilePath=OriginalFilePath,
                    Success=True,
                    VMAF=VMAFScore
                )
                # Save new transcoding attempt to database
                self.DatabaseManager.SaveTranscodeAttempt(TranscodeAttempt)
            else:
                # Update existing attempt (already saved in ProcessTranscodingWorkflow)
                pass
            
            # Replace original file with transcoded file
            replaceResult = self.FileManager.ReplaceFile(OriginalFilePath, TranscodedFilePath)
            if not replaceResult.get('Success', False):
                return {
                    'Success': False,
                    'Status': 'failed',
                    'ErrorMessage': f'Failed to replace original file: {replaceResult.get("ErrorMessage", "Unknown error")}'
                }
            
            # Clean up source file if it exists
            if SourceFilePath and os.path.exists(SourceFilePath):
                try:
                    os.remove(SourceFilePath)
                    LoggingService.LogInfo(f"Cleaned up source file: {SourceFilePath}", "TranscodingBusinessService", "ProcessFileReplacement")
                except Exception as cleanupError:
                    LoggingService.LogWarning(f"Failed to clean up source file {SourceFilePath}: {str(cleanupError)}", "TranscodingBusinessService", "ProcessFileReplacement")
            
            return {
                'Success': True,
                'Status': 'completed',
                'VMAFScore': VMAFScore,
                'TranscodeAttempt': TranscodeAttempt
            }
            
        except Exception as e:
            LoggingService.LogException("Exception in file replacement", e, "TranscodingBusinessService", "ProcessFileReplacement")
            return {
                'Success': False,
                'Status': 'failed',
                'ErrorMessage': f'File replacement exception: {str(e)}'
            }
    
    def GetTranscodeStatus(self, JobId: str) -> Dict[str, Any]:
        """Get the status of a transcoding job."""
        try:
            LoggingService.LogFunctionEntry(f"GetTranscodeStatus({JobId})", "TranscodingBusinessService")
            
            # Query the database for job status
            attempt = self.DatabaseManager.GetTranscodeAttemptById(int(JobId))
            
            if not attempt:
                return {
                    'Success': False,
                    'JobId': JobId,
                    'ErrorMessage': 'Job not found'
                }
            
            # Get latest progress for this attempt
            progress = self.DatabaseManager.GetLatestTranscodeProgress(int(JobId))
            
            return {
                'Success': True,
                'JobId': JobId,
                'FilePath': attempt.SourceFilePath,
                'Status': 'completed' if attempt.Success else 'failed' if attempt.ErrorMessage else 'running',
                'ProgressPercent': progress.get('ProgressPercent', 0) if progress else 0,
                'StartTime': attempt.DateStarted.isoformat() if attempt.DateStarted else None,
                'ErrorMessage': attempt.ErrorMessage if attempt.ErrorMessage else None
            }
            
        except Exception as e:
            LoggingService.LogException("Exception getting transcoding status", e, "TranscodingBusinessService", "GetTranscodeStatus")
            return {
                'Success': False,
                'Error': f'Exception getting status: {str(e)}',
                'ErrorCode': 'INTERNAL_SERVER_ERROR',
                'Timestamp': datetime.now().isoformat()
            }
    
    def GetTranscodeQueue(self) -> Dict[str, Any]:
        """Get the current transcoding queue."""
        try:
            LoggingService.LogFunctionEntry("GetTranscodeQueue", "TranscodingBusinessService")
            
            # Get queue items from database
            queueItems = self.QueueManagementService.GetQueueItems()
            
            # Calculate total size
            totalSizeMB = sum(item.SizeMB for item in queueItems)
            
            return {
                'Success': True,
                'Message': 'Queue retrieved successfully',
                'QueueItems': [
                    {
                        'Id': item.Id,
                        'FilePath': item.FilePath,
                        'FileName': item.FileName,
                        'SizeMB': item.SizeMB,
                        'Status': item.Status.lower(),
                        'AssignedProfile': item.AssignedProfile,
                        'DateAdded': item.DateAdded.isoformat() if item.DateAdded else None
                    }
                    for item in queueItems
                ],
                'TotalItems': len(queueItems),
                'TotalSizeMB': totalSizeMB
            }
            
        except Exception as e:
            LoggingService.LogException("Exception getting transcoding queue", e, "TranscodingBusinessService", "GetTranscodeQueue")
            return {
                'Success': False,
                'Error': f'Exception getting queue: {str(e)}',
                'ErrorCode': 'INTERNAL_SERVER_ERROR',
                'Timestamp': datetime.now().isoformat()
            }
    
    def GetQualitySettingsForFile(self, QueueItem: TranscodeQueueModel) -> Optional[Dict[str, Any]]:
        """Get quality settings for a file from the MediaFiles table and ProfileThresholds. Fails if required settings are missing."""
        try:
            LoggingService.LogFunctionEntry("GetQualitySettingsForFile", "TranscodingBusinessService", QueueItem.FilePath)
            
            # Get media file record
            mediaFile = self.DatabaseManager.GetMediaFileByPath(QueueItem.FilePath)
            if not mediaFile:
                error_msg = f"No media file record found for: {QueueItem.FilePath}"
                LoggingService.LogError(error_msg, "TranscodingBusinessService", "GetQualitySettingsForFile")
                return None
            
            # Validate required media file properties
            if not mediaFile.AssignedProfile:
                error_msg = f"No AssignedProfile found for media file: {QueueItem.FileName}"
                LoggingService.LogError(error_msg, "TranscodingBusinessService", "GetQualitySettingsForFile")
                return None
            
            if not mediaFile.Resolution:
                error_msg = f"No Resolution found for media file: {QueueItem.FileName}"
                LoggingService.LogError(error_msg, "TranscodingBusinessService", "GetQualitySettingsForFile")
                return None
            
            # Get Quality from target resolution based on TranscodeDownTo setting
            profileQuality = self.DatabaseManager.GetProfileQualityForTargetResolution(mediaFile.AssignedProfile, mediaFile.Resolution)
            if profileQuality is None:
                error_msg = f"No Quality setting found in ProfileThresholds for Profile '{mediaFile.AssignedProfile}' and Resolution '{mediaFile.Resolution}'"
                LoggingService.LogError(error_msg, "TranscodingBusinessService", "GetQualitySettingsForFile")
                return None
            
            LoggingService.LogInfo(f"Retrieved Quality {profileQuality} from Profile {mediaFile.AssignedProfile} for target resolution", "TranscodingBusinessService", "GetQualitySettingsForFile")
            
            # Get all settings from ProfileThresholds for target resolution
            profileSettings = self.DatabaseManager.GetProfileSettingsForTargetResolution(mediaFile.AssignedProfile, mediaFile.Resolution)
            if not profileSettings:
                error_msg = f"No ProfileSettings found in ProfileThresholds for Profile '{mediaFile.AssignedProfile}' and Resolution '{mediaFile.Resolution}'"
                LoggingService.LogError(error_msg, "TranscodingBusinessService", "GetQualitySettingsForFile")
                return None
            
            # Extract required settings - NO DEFAULTS ALLOWED
            profileVideoBitrate = profileSettings.get('VideoBitrateKbps')
            profileAudioBitrate = profileSettings.get('AudioBitrateKbps')
            targetResolution = profileSettings.get('TargetResolution')
            
            # Validate all required settings are present
            missing_settings = []
            if profileVideoBitrate is None:
                missing_settings.append('VideoBitrateKbps')
            if profileAudioBitrate is None:
                missing_settings.append('AudioBitrateKbps')
            if not targetResolution:
                missing_settings.append('TargetResolution')
            if not profileSettings.get('Codec'):
                missing_settings.append('Codec')
            
            if missing_settings:
                error_msg = f"Missing required settings in ProfileThresholds for Profile '{mediaFile.AssignedProfile}' and Target Resolution '{targetResolution}': {', '.join(missing_settings)}"
                LoggingService.LogError(error_msg, "TranscodingBusinessService", "GetQualitySettingsForFile")
                return None
            
            # Get codec from profile settings - ALL transcoding settings must come from profiles
            codec = profileSettings.get('Codec')
            if not codec:
                error_msg = f"No Codec found in ProfileThresholds for Profile '{mediaFile.AssignedProfile}' and Target Resolution '{targetResolution}'"
                LoggingService.LogError(error_msg, "TranscodingBusinessService", "GetQualitySettingsForFile")
                return None
            
            # Build quality settings - all validated to exist
            qualitySettings = {
                'VideoBitrateKbps': profileVideoBitrate,
                'AudioBitrateKbps': profileAudioBitrate,
                'TargetResolution': targetResolution,
                'Codec': codec,
                'Quality': profileQuality
            }
            
            LoggingService.LogInfo(f"Retrieved quality settings for {QueueItem.FileName}: {qualitySettings}", "TranscodingBusinessService", "GetQualitySettingsForFile")
            return qualitySettings
            
        except Exception as e:
            LoggingService.LogException("Exception getting quality settings", e, "TranscodingBusinessService", "GetQualitySettingsForFile")
            return None
