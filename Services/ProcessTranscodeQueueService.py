from typing import Dict, Any, Optional, Callable
from datetime import datetime
import threading
import time
from Models.TranscodeQueueModel import TranscodeQueueModel
from Models.MediaFileModel import MediaFileModel
from Models.TranscodeAttemptModel import TranscodeAttemptModel
from Repositories.DatabaseManager import DatabaseManager
from Services.TranscodingFileManagerService import TranscodingFileManagerService
from Services.CommandBuilderService import CommandBuilderService
from Services.VideoTranscodingService import VideoTranscodingService
from Services.TranscodingVMAFQueueService import TranscodingVMAFQueueService
from Services.LoggingService import LoggingService


class ProcessTranscodeQueueService:
    """Orchestrates the complete transcoding queue processing workflow using MVVM architecture."""
    
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None,
                 FileManagerInstance: TranscodingFileManagerService = None,
                 CommandBuilderInstance: CommandBuilderService = None,
                 VideoTranscodingInstance: VideoTranscodingService = None,
                 VMAFQueueInstance: TranscodingVMAFQueueService = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.FileManager = FileManagerInstance or TranscodingFileManagerService()
        self.CommandBuilder = CommandBuilderInstance or CommandBuilderService()
        self.VideoTranscoding = VideoTranscodingInstance or VideoTranscodingService()
        self.VMAFQueue = VMAFQueueInstance or TranscodingVMAFQueueService()
        
        # Processing state
        self.IsProcessing = False
        self.MaxConcurrentJobs = 1
        self.ActiveJobs = []
        self.ProcessingThread = None
        self.StopRequested = False
        
    def Run(self, MaxConcurrentJobs: int = 1) -> Dict[str, Any]:
        """Start processing the transcoding queue with specified concurrent jobs."""
        try:
            LoggingService.LogFunctionEntry("Run", "ProcessTranscodeQueueService", MaxConcurrentJobs)
            
            if self.IsProcessing:
                return {
                    "Success": False,
                    "ErrorMessage": "Transcoding is already in progress"
                }
            
            # Validate parameters
            if not isinstance(MaxConcurrentJobs, int) or MaxConcurrentJobs < 1 or MaxConcurrentJobs > 5:
                return {
                    "Success": False,
                    "ErrorMessage": "MaxConcurrentJobs must be an integer between 1 and 5"
                }
            
            self.MaxConcurrentJobs = MaxConcurrentJobs
            self.StopRequested = False
            self.IsProcessing = True
            
            # Start processing in background thread
            self.ProcessingThread = threading.Thread(target=self.ProcessQueueLoop, daemon=True)
            self.ProcessingThread.start()
            
            LoggingService.LogInfo(f"Started transcoding queue processing with {MaxConcurrentJobs} concurrent jobs", 
                                 "ProcessTranscodeQueueService", "Run")
            
            return {
                "Success": True,
                "Message": f"Started transcoding with {MaxConcurrentJobs} concurrent jobs",
                "MaxConcurrentJobs": MaxConcurrentJobs
            }
            
        except Exception as e:
            self.IsProcessing = False
            errorMsg = f"Exception starting transcoding: {str(e)}"
            LoggingService.LogException(errorMsg, e, "ProcessTranscodeQueueService", "Run")
            return {
                "Success": False,
                "ErrorMessage": errorMsg
            }
    
    def Stop(self) -> Dict[str, Any]:
        """Stop processing the transcoding queue."""
        try:
            LoggingService.LogFunctionEntry("Stop", "ProcessTranscodeQueueService")
            
            if not self.IsProcessing:
                return {
                    "Success": True,
                    "Message": "Transcoding is not currently running"
                }
            
            self.StopRequested = True
            
            # Wait for processing to stop
            if self.ProcessingThread and self.ProcessingThread.is_alive():
                self.ProcessingThread.join(timeout=10)
            
            self.IsProcessing = False
            self.ActiveJobs.clear()
            
            LoggingService.LogInfo("Stopped transcoding queue processing", "ProcessTranscodeQueueService", "Stop")
            
            return {
                "Success": True,
                "Message": "Transcoding stopped successfully"
            }
            
        except Exception as e:
            errorMsg = f"Exception stopping transcoding: {str(e)}"
            LoggingService.LogException(errorMsg, e, "ProcessTranscodeQueueService", "Stop")
            return {
                "Success": False,
                "ErrorMessage": errorMsg
            }
    
    def GetStatus(self) -> Dict[str, Any]:
        """Get current transcoding status and progress."""
        try:
            # Get current progress from database
            currentProgress = self.DatabaseManager.GetCurrentTranscodeProgress()
            
            return {
                "Success": True,
                "IsTranscoding": self.IsProcessing,
                "MaxConcurrentJobs": self.MaxConcurrentJobs,
                "ActiveJobsCount": len(self.ActiveJobs),
                "CurrentProgress": currentProgress,
                "Timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            errorMsg = f"Exception getting transcoding status: {str(e)}"
            LoggingService.LogException(errorMsg, e, "ProcessTranscodeQueueService", "GetStatus")
            return {
                "Success": False,
                "ErrorMessage": errorMsg
            }
    
    def ProcessQueueLoop(self):
        """Main processing loop that runs in background thread."""
        try:
            LoggingService.LogInfo("Starting transcoding queue processing loop", "ProcessTranscodeQueueService", "ProcessQueueLoop")
            
            while not self.StopRequested:
                # Check if we can start more jobs
                if len(self.ActiveJobs) < self.MaxConcurrentJobs:
                    # Try to get next job
                    job = self.GetNextJob()
                    if job:
                        # Start processing job in separate thread
                        jobThread = threading.Thread(
                            target=self.ProcessJob, 
                            args=(job,), 
                            daemon=True
                        )
                        jobThread.start()
                        self.ActiveJobs.append(jobThread)
                    else:
                        # No more jobs, wait a bit
                        time.sleep(2)
                else:
                    # All slots full, wait a bit
                    time.sleep(1)
                
                # Clean up completed threads
                self.ActiveJobs = [thread for thread in self.ActiveJobs if thread.is_alive()]
            
            # Wait for all active jobs to complete
            for thread in self.ActiveJobs:
                if thread.is_alive():
                    thread.join(timeout=30)
            
            LoggingService.LogInfo("Transcoding queue processing loop completed", "ProcessTranscodeQueueService", "ProcessQueueLoop")
            
        except Exception as e:
            LoggingService.LogException("Exception in processing loop", e, "ProcessTranscodeQueueService", "ProcessQueueLoop")
        finally:
            self.IsProcessing = False
    
    def GetNextJob(self) -> Optional[TranscodeQueueModel]:
        """Get the next pending job from the queue."""
        try:
            return self.DatabaseManager.GetNextPendingTranscodeJob()
        except Exception as e:
            LoggingService.LogException("Exception getting next job", e, "ProcessTranscodeQueueService", "GetNextJob")
            return None
    
    def ProcessJob(self, Job: TranscodeQueueModel):
        """Process a single transcoding job through the complete workflow."""
        try:
            LoggingService.LogInfo(f"Starting job processing for job ID: {Job.Id}", "ProcessTranscodeQueueService", "ProcessJob")
            
            # Step a: Get MediaFile data
            MediaFile = self.GetMediaFileData(Job)
            if not MediaFile:
                self.HandleJobFailure(Job, "Failed to get media file data")
                return
            
            # Step b: Setup directories and copy file
            if not self.SetupFilePreparation(Job, MediaFile):
                self.HandleJobFailure(Job, "Failed to setup file preparation")
                return
            
            # Step c: Get transcoding settings
            TranscodingSettings = self.GetTranscodingSettings(Job, MediaFile)
            if not TranscodingSettings:
                self.HandleJobFailure(Job, "Failed to get transcoding settings")
                return
            
            # Step d: Build transcoding command
            TranscodeCommand = self.BuildTranscodeCommand(Job, MediaFile, TranscodingSettings)
            if not TranscodeCommand:
                self.HandleJobFailure(Job, "Failed to build transcoding command")
                return
            
            # Step e: Create transcode attempt record for progress tracking
            TranscodeAttemptId = self.CreateTranscodeAttempt(Job, MediaFile, TranscodingSettings, TranscodeCommand)
            if not TranscodeAttemptId:
                self.HandleJobFailure(Job, "Failed to create transcode attempt record")
                return
            
            # Step f: Execute transcoding
            TranscodeResult = self.ExecuteTranscoding(Job, TranscodeCommand, TranscodeAttemptId)
            if not TranscodeResult.get("Success", False):
                self.HandleJobFailure(Job, f"Transcoding failed: {TranscodeResult.get('ErrorMessage', 'Unknown error')}", TranscodeAttemptId)
                return
            
            # Step g: Handle transcoding result
            self.HandleTranscodingResult(Job, TranscodeResult, TranscodeAttemptId)
            
            # Step g: Cleanup or continue
            self.CleanupOrContinue(Job)
            
            LoggingService.LogInfo(f"Completed job processing for job ID: {Job.Id}", "ProcessTranscodeQueueService", "ProcessJob")
            
        except Exception as e:
            LoggingService.LogException(f"Exception processing job {Job.Id}", e, "ProcessTranscodeQueueService", "ProcessJob")
            self.HandleJobFailure(Job, f"Exception during processing: {str(e)}")
    
    def GetMediaFileData(self, Job: TranscodeQueueModel) -> Optional[MediaFileModel]:
        """Get MediaFile data by FilePath to retrieve source resolution."""
        try:
            return self.DatabaseManager.GetMediaFileByPath(Job.FilePath)
        except Exception as e:
            LoggingService.LogException("Exception getting media file data", e, "ProcessTranscodeQueueService", "GetMediaFileData")
            return None
    
    def SetupFilePreparation(self, Job: TranscodeQueueModel, MediaFile: MediaFileModel) -> bool:
        """Setup transcoding directories and copy source file."""
        try:
            # Setup directories
            if not self.FileManager.SetupTranscodingDirectories():
                return False
            
            # Copy file to source directory
            SourcePath = Job.FilePath
            DestinationPath = f"C:\\MediaVortex\\Source\\{MediaFile.FileName}"
            
            return self.FileManager.CopyFile(SourcePath, DestinationPath)
            
        except Exception as e:
            LoggingService.LogException("Exception in file preparation", e, "ProcessTranscodeQueueService", "SetupFilePreparation")
            return False
    
    def GetTranscodingSettings(self, Job: TranscodeQueueModel, MediaFile: MediaFileModel) -> Optional[Dict[str, Any]]:
        """Get transcoding settings including profile, codec flags, and parameters."""
        try:
            # Get profile settings for target resolution
            ProfileSettings = self.DatabaseManager.GetProfileSettingsForTargetResolution(
                MediaFile.AssignedProfile, MediaFile.Resolution
            )
            if not ProfileSettings:
                return None
            
            # Get codec flags
            CodecFlags = self.DatabaseManager.GetCodecFlagsByCodecName(ProfileSettings.get('Codec'))
            if not CodecFlags:
                return None
            
            # Get codec parameters
            CodecParameters = self.DatabaseManager.GetCodecParametersByCodecFlagsId(CodecFlags['Id'])
            if not CodecParameters:
                return None
            
            return {
                'ProfileSettings': ProfileSettings,
                'CodecFlags': CodecFlags,
                'CodecParameters': CodecParameters,
                'SourceResolution': MediaFile.Resolution
            }
            
        except Exception as e:
            LoggingService.LogException("Exception getting transcoding settings", e, "ProcessTranscodeQueueService", "GetTranscodingSettings")
            return None
    
    def BuildTranscodeCommand(self, Job: TranscodeQueueModel, MediaFile: MediaFileModel, 
                              TranscodingSettings: Dict[str, Any]) -> Optional[str]:
        """Build the complete transcoding command."""
        try:
            return self.CommandBuilder.BuildCommand(Job, MediaFile, TranscodingSettings)
        except Exception as e:
            LoggingService.LogException("Exception building transcode command", e, "ProcessTranscodeQueueService", "BuildTranscodeCommand")
            return None
    
    def CreateTranscodeAttempt(self, Job: TranscodeQueueModel, MediaFile: MediaFileModel, 
                              TranscodingSettings: Dict[str, Any], TranscodeCommand: str) -> Optional[int]:
        """Create a transcode attempt record for progress tracking."""
        try:
            ProfileSettings = TranscodingSettings.get('ProfileSettings', {})
            CodecFlags = TranscodingSettings.get('CodecFlags', {})
            
            # Create attempt record
            Attempt = TranscodeAttemptModel(
                FilePath=Job.FilePath,
                AttemptDate=datetime.now(),
                Quality=ProfileSettings.get('Quality', 0),
                OldSizeBytes=Job.SizeBytes,
                NewSizeBytes=0,  # Will be updated after transcoding
                Success=False,  # Will be updated after transcoding
                SizeReductionBytes=0,  # Will be calculated after transcoding
                SizeReductionPercent=0.0,  # Will be calculated after transcoding
                ErrorMessage=None,
                TranscodeDurationSeconds=0.0,  # Will be updated after transcoding
                FfpmpegCommand=TranscodeCommand,
                AudioBitrateKbps=ProfileSettings.get('AudioBitrateKbps'),
                VideoBitrateKbps=ProfileSettings.get('VideoBitrateKbps'),
                ProfileName=MediaFile.AssignedProfile,
                VMAF=None  # Will be set after VMAF analysis
            )
            
            return self.DatabaseManager.SaveTranscodeAttempt(Attempt)
            
        except Exception as e:
            LoggingService.LogException("Exception creating transcode attempt", e, "ProcessTranscodeQueueService", "CreateTranscodeAttempt")
            return None
    
    def ExecuteTranscoding(self, Job: TranscodeQueueModel, TranscodeCommand: str, TranscodeAttemptId: int) -> Dict[str, Any]:
        """Execute the transcoding command with progress tracking."""
        try:
            # Create progress callback
            def ProgressCallback(ProgressData: Dict[str, Any]):
                self.DatabaseManager.SaveTranscodeProgress(
                    TranscodeAttemptId,
                    ProgressData.get('CurrentPhase', 'Transcoding'),
                    ProgressData.get('ProgressPercent', 0),
                    ProgressData.get('CurrentFrame', 0),
                    ProgressData.get('CurrentFPS', 0),
                    ProgressData.get('CurrentBitrate', 0),
                    ProgressData.get('CurrentTime', ''),
                    ProgressData.get('CurrentSpeed', ''),
                    ProgressData.get('ETA', ''),
                    ProgressData.get('TotalFrames', 0),
                    ProgressData.get('AverageFPS', 0)
                )
            
            return self.VideoTranscoding.TranscodeVideo(TranscodeAttemptId, TranscodeCommand, ProgressCallback)
            
        except Exception as e:
            LoggingService.LogException("Exception executing transcoding", e, "ProcessTranscodeQueueService", "ExecuteTranscoding")
            return {
                "Success": False,
                "ErrorMessage": f"Exception during transcoding: {str(e)}"
            }
    
    def HandleTranscodingResult(self, Job: TranscodeQueueModel, TranscodeResult: Dict[str, Any], TranscodeAttemptId: int):
        """Handle transcoding results - success or failure processing."""
        try:
            if TranscodeResult.get("Success", False):
                # Update attempt record with success details
                self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                    'Success': True,
                    'TranscodeDurationSeconds': TranscodeResult.get('Duration', 0.0),
                    'NewSizeBytes': TranscodeResult.get('NewSizeBytes', 0),
                    'SizeReductionBytes': TranscodeResult.get('SizeReductionBytes', 0),
                    'SizeReductionPercent': TranscodeResult.get('SizeReductionPercent', 0.0)
                })
                
                # Add to VMAF queue for quality assessment
                self.VMAFQueue.AddToQueue(TranscodeAttemptId, TranscodeResult.get('OutputFilePath'))
                
                # Delete job from queue (successful completion)
                self.DatabaseManager.DeleteTranscodeQueueItem(Job.Id)
                
                LoggingService.LogInfo(f"Job {Job.Id} completed successfully and removed from queue", "ProcessTranscodeQueueService", "HandleTranscodingResult")
            else:
                # Handle failure
                self.HandleJobFailure(Job, TranscodeResult.get('ErrorMessage', 'Unknown error'), TranscodeAttemptId)
                
        except Exception as e:
            LoggingService.LogException("Exception handling transcoding result", e, "ProcessTranscodeQueueService", "HandleTranscodingResult")
    
    def HandleJobFailure(self, Job: TranscodeQueueModel, ErrorMessage: str, TranscodeAttemptId: int = None):
        """Handle job failure by updating attempt record and removing from queue."""
        try:
            if TranscodeAttemptId:
                # Update existing attempt record with failure details
                self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                    'Success': False,
                    'ErrorMessage': ErrorMessage
                })
            else:
                # Create new attempt record for investigation (fallback case)
                Attempt = TranscodeAttemptModel(
                    FilePath=Job.FilePath,
                    AttemptDate=datetime.now(),
                    Quality=0,  # Will be set properly when we have profile info
                    OldSizeBytes=Job.SizeBytes,
                    NewSizeBytes=0,
                    Success=False,
                    SizeReductionBytes=0,
                    SizeReductionPercent=0.0,
                    ErrorMessage=ErrorMessage,
                    TranscodeDurationSeconds=0.0,
                    FfpmpegCommand=None,
                    AudioBitrateKbps=None,
                    VideoBitrateKbps=None,
                    ProfileName=None,  # Will be set when we have profile info
                    VMAF=None
                )
                self.DatabaseManager.SaveTranscodeAttempt(Attempt)
            
            # Delete job from queue (failed completion)
            self.DatabaseManager.DeleteTranscodeQueueItem(Job.Id)
            
            LoggingService.LogError(f"Job {Job.Id} failed and removed from queue: {ErrorMessage}", "ProcessTranscodeQueueService", "HandleJobFailure")
            
        except Exception as e:
            LoggingService.LogException("Exception handling job failure", e, "ProcessTranscodeQueueService", "HandleJobFailure")
    
    def CleanupOrContinue(self, Job: TranscodeQueueModel):
        """Determine next action after job completion."""
        try:
            # For now, just log completion
            # The main loop will continue processing other jobs
            LoggingService.LogInfo(f"Job {Job.Id} cleanup completed", "ProcessTranscodeQueueService", "CleanupOrContinue")
            
        except Exception as e:
            LoggingService.LogException("Exception in cleanup", e, "ProcessTranscodeQueueService", "CleanupOrContinue")
