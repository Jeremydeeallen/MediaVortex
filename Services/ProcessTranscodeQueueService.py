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
            self.ProcessingThread = threading.Thread(target=self._ProcessQueueLoop, daemon=True)
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
    
    def _ProcessQueueLoop(self):
        """Main processing loop that runs in background thread."""
        try:
            LoggingService.LogInfo("Starting transcoding queue processing loop", "ProcessTranscodeQueueService", "_ProcessQueueLoop")
            
            while not self.StopRequested:
                # Check if we can start more jobs
                if len(self.ActiveJobs) < self.MaxConcurrentJobs:
                    # Try to get next job
                    job = self._GetNextJob()
                    if job:
                        # Start processing job in separate thread
                        jobThread = threading.Thread(
                            target=self._ProcessJob, 
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
            
            LoggingService.LogInfo("Transcoding queue processing loop completed", "ProcessTranscodeQueueService", "_ProcessQueueLoop")
            
        except Exception as e:
            LoggingService.LogException("Exception in processing loop", e, "ProcessTranscodeQueueService", "_ProcessQueueLoop")
        finally:
            self.IsProcessing = False
    
    def _GetNextJob(self) -> Optional[TranscodeQueueModel]:
        """Get the next pending job from the queue."""
        try:
            return self.DatabaseManager.GetNextPendingTranscodeJob()
        except Exception as e:
            LoggingService.LogException("Exception getting next job", e, "ProcessTranscodeQueueService", "_GetNextJob")
            return None
    
    def _ProcessJob(self, Job: TranscodeQueueModel):
        """Process a single transcoding job through the complete workflow."""
        try:
            LoggingService.LogInfo(f"Starting job processing for job ID: {Job.Id}", "ProcessTranscodeQueueService", "_ProcessJob")
            
            # Step a: Get MediaFile data
            MediaFile = self._GetMediaFileData(Job)
            if not MediaFile:
                self._HandleJobFailure(Job, "Failed to get media file data")
                return
            
            # Step b: Setup directories and copy file
            if not self._SetupFilePreparation(Job, MediaFile):
                self._HandleJobFailure(Job, "Failed to setup file preparation")
                return
            
            # Step c: Get transcoding settings
            TranscodingSettings = self._GetTranscodingSettings(Job, MediaFile)
            if not TranscodingSettings:
                self._HandleJobFailure(Job, "Failed to get transcoding settings")
                return
            
            # Step d: Build transcoding command
            TranscodeCommand = self._BuildTranscodeCommand(Job, MediaFile, TranscodingSettings)
            if not TranscodeCommand:
                self._HandleJobFailure(Job, "Failed to build transcoding command")
                return
            
            # Step e: Execute transcoding
            TranscodeResult = self._ExecuteTranscoding(Job, TranscodeCommand)
            if not TranscodeResult.get("Success", False):
                self._HandleJobFailure(Job, f"Transcoding failed: {TranscodeResult.get('ErrorMessage', 'Unknown error')}")
                return
            
            # Step f: Handle transcoding result
            self._HandleTranscodingResult(Job, TranscodeResult)
            
            # Step g: Cleanup or continue
            self._CleanupOrContinue(Job)
            
            LoggingService.LogInfo(f"Completed job processing for job ID: {Job.Id}", "ProcessTranscodeQueueService", "_ProcessJob")
            
        except Exception as e:
            LoggingService.LogException(f"Exception processing job {Job.Id}", e, "ProcessTranscodeQueueService", "_ProcessJob")
            self._HandleJobFailure(Job, f"Exception during processing: {str(e)}")
    
    def _GetMediaFileData(self, Job: TranscodeQueueModel) -> Optional[MediaFileModel]:
        """Get MediaFile data by FilePath to retrieve source resolution."""
        try:
            return self.DatabaseManager.GetMediaFileByPath(Job.FilePath)
        except Exception as e:
            LoggingService.LogException("Exception getting media file data", e, "ProcessTranscodeQueueService", "_GetMediaFileData")
            return None
    
    def _SetupFilePreparation(self, Job: TranscodeQueueModel, MediaFile: MediaFileModel) -> bool:
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
            LoggingService.LogException("Exception in file preparation", e, "ProcessTranscodeQueueService", "_SetupFilePreparation")
            return False
    
    def _GetTranscodingSettings(self, Job: TranscodeQueueModel, MediaFile: MediaFileModel) -> Optional[Dict[str, Any]]:
        """Get transcoding settings including profile, codec flags, and parameters."""
        try:
            # Get profile settings for target resolution
            ProfileSettings = self.DatabaseManager.GetProfileSettingsForTargetResolution(
                Job.AssignedProfile, MediaFile.Resolution
            )
            if not ProfileSettings:
                return None
            
            # Get codec flags
            CodecFlags = self.DatabaseManager.GetCodecFlagsByCodecName(ProfileSettings.get('Codec'))
            if not CodecFlags:
                return None
            
            # Get codec parameters
            CodecParameters = self.DatabaseManager.GetCodecParametersByCodecFlagsId(CodecFlags.Id)
            if not CodecParameters:
                return None
            
            return {
                'ProfileSettings': ProfileSettings,
                'CodecFlags': CodecFlags,
                'CodecParameters': CodecParameters,
                'SourceResolution': MediaFile.Resolution
            }
            
        except Exception as e:
            LoggingService.LogException("Exception getting transcoding settings", e, "ProcessTranscodeQueueService", "_GetTranscodingSettings")
            return None
    
    def _BuildTranscodeCommand(self, Job: TranscodeQueueModel, MediaFile: MediaFileModel, 
                              TranscodingSettings: Dict[str, Any]) -> Optional[str]:
        """Build the complete transcoding command."""
        try:
            return self.CommandBuilder.BuildCommand(Job, MediaFile, TranscodingSettings)
        except Exception as e:
            LoggingService.LogException("Exception building transcode command", e, "ProcessTranscodeQueueService", "_BuildTranscodeCommand")
            return None
    
    def _ExecuteTranscoding(self, Job: TranscodeQueueModel, TranscodeCommand: str) -> Dict[str, Any]:
        """Execute the transcoding command with progress tracking."""
        try:
            # Create progress callback
            def ProgressCallback(ProgressData: Dict[str, Any]):
                self.DatabaseManager.SaveTranscodeProgress(
                    Job.Id,
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
            
            return self.VideoTranscoding.TranscodeVideo(Job.Id, TranscodeCommand, ProgressCallback)
            
        except Exception as e:
            LoggingService.LogException("Exception executing transcoding", e, "ProcessTranscodeQueueService", "_ExecuteTranscoding")
            return {
                "Success": False,
                "ErrorMessage": f"Exception during transcoding: {str(e)}"
            }
    
    def _HandleTranscodingResult(self, Job: TranscodeQueueModel, TranscodeResult: Dict[str, Any]):
        """Handle transcoding results - success or failure processing."""
        try:
            if TranscodeResult.get("Success", False):
                # Save attempt record
                Attempt = TranscodeAttemptModel(
                    JobId=Job.Id,
                    StartTime=TranscodeResult.get('StartTime'),
                    EndTime=TranscodeResult.get('EndTime'),
                    Duration=TranscodeResult.get('Duration'),
                    Success=True,
                    OutputFilePath=TranscodeResult.get('OutputFilePath'),
                    ErrorMessage=None
                )
                self.DatabaseManager.SaveTranscodeAttempt(Attempt)
                
                # Add to VMAF queue for quality assessment
                self.VMAFQueue.AddToQueue(Job.Id, TranscodeResult.get('OutputFilePath'))
                
                # Delete job from queue (successful completion)
                self.DatabaseManager.DeleteTranscodeQueueItem(Job.Id)
                
                LoggingService.LogInfo(f"Job {Job.Id} completed successfully and removed from queue", "ProcessTranscodeQueueService", "_HandleTranscodingResult")
            else:
                # Handle failure
                self._HandleJobFailure(Job, TranscodeResult.get('ErrorMessage', 'Unknown error'))
                
        except Exception as e:
            LoggingService.LogException("Exception handling transcoding result", e, "ProcessTranscodeQueueService", "_HandleTranscodingResult")
    
    def _HandleJobFailure(self, Job: TranscodeQueueModel, ErrorMessage: str):
        """Handle job failure by saving attempt record and removing from queue."""
        try:
            # Save attempt record for investigation
            Attempt = TranscodeAttemptModel(
                JobId=Job.Id,
                StartTime=datetime.now(),
                EndTime=datetime.now(),
                Duration=0,
                Success=False,
                OutputFilePath=None,
                ErrorMessage=ErrorMessage
            )
            self.DatabaseManager.SaveTranscodeAttempt(Attempt)
            
            # Delete job from queue (failed completion)
            self.DatabaseManager.DeleteTranscodeQueueItem(Job.Id)
            
            LoggingService.LogError(f"Job {Job.Id} failed and removed from queue: {ErrorMessage}", "ProcessTranscodeQueueService", "_HandleJobFailure")
            
        except Exception as e:
            LoggingService.LogException("Exception handling job failure", e, "ProcessTranscodeQueueService", "_HandleJobFailure")
    
    def _CleanupOrContinue(self, Job: TranscodeQueueModel):
        """Determine next action after job completion."""
        try:
            # For now, just log completion
            # The main loop will continue processing other jobs
            LoggingService.LogInfo(f"Job {Job.Id} cleanup completed", "ProcessTranscodeQueueService", "_CleanupOrContinue")
            
        except Exception as e:
            LoggingService.LogException("Exception in cleanup", e, "ProcessTranscodeQueueService", "_CleanupOrContinue")
