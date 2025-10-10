from typing import Dict, Any, Optional, Callable
from datetime import datetime
import threading
import time
import os
import re
from Models.TranscodeQueueModel import TranscodeQueueModel
from Models.MediaFileModel import MediaFileModel
from Models.TranscodeAttemptModel import TranscodeAttemptModel
from Models.TranscodeFileModel import TranscodeFileModel
from Repositories.DatabaseManager import DatabaseManager
from Services.TranscodingFileManagerService import TranscodingFileManagerService
from Services.CommandBuilderService import CommandBuilderService
from Services.VideoTranscodingService import VideoTranscodingService
from Services.QueueManagementService import QueueManagementService
from Services.ShouldQualityTestService import ShouldQualityTestService
from Services.LoggingService import LoggingService


class ProcessTranscodeQueueService:
    """Orchestrates the complete transcoding queue processing workflow using MVVM architecture."""
    
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None,
                 FileManagerInstance: TranscodingFileManagerService = None,
                 CommandBuilderInstance: CommandBuilderService = None,
                 VideoTranscodingInstance: VideoTranscodingService = None,
                 QueueManagementInstance: QueueManagementService = None,
                 ShouldQualityTestInstance: ShouldQualityTestService = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.FileManager = FileManagerInstance or TranscodingFileManagerService()
        self.CommandBuilder = CommandBuilderInstance or CommandBuilderService()
        self.VideoTranscoding = VideoTranscodingInstance or VideoTranscodingService()
        self.QueueManagement = QueueManagementInstance or QueueManagementService(DatabaseManagerInstance=self.DatabaseManager)
        self.ShouldQualityTest = ShouldQualityTestInstance or ShouldQualityTestService()
        
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
            
            # Stop any active video transcoding processes
            self.StopAllActiveTranscodingProcesses()
            
            # Reset running jobs to pending status using shared service
            resetResult = self.QueueManagement.ResetRunningJobsToPending("TranscodeQueue", "Transcoding cancelled by user stop request")
            if resetResult.get("Success", False):
                LoggingService.LogInfo(f"Queue reset completed: {resetResult.get('Message', '')}", 
                                     "ProcessTranscodeQueueService", "Stop")
            else:
                LoggingService.LogWarning(f"Queue reset failed: {resetResult.get('ErrorMessage', 'Unknown error')}", 
                                        "ProcessTranscodeQueueService", "Stop")
            
            # Clean up any stale progress data from database
            self.CleanupStaleProgressData()
            
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
            
            # Get current job info if transcoding is active
            currentJob = None
            if self.IsProcessing and currentProgress:
                # Get the current job from the queue
                currentJob = self.DatabaseManager.GetTranscodeQueueItemsByStatus("Running")
                if currentJob:
                    currentJob = currentJob[0]  # Get the first running job
            
            # More robust transcoding status check
            # Consider transcoding active only if:
            # 1. IsProcessing flag is True AND
            # 2. There are active threads AND
            # 3. There's current progress data AND
            # 4. There are actually jobs in the queue
            activeJobCount = len([thread for thread in self.ActiveJobs if thread.is_alive()])
            
            # Check if there are any pending jobs in the queue
            pendingJobs = self.DatabaseManager.GetTranscodeQueueItemsByStatus("Pending")
            runningJobs = self.DatabaseManager.GetTranscodeQueueItemsByStatus("Running")
            hasJobsInQueue = len(pendingJobs) > 0 or len(runningJobs) > 0
            
            isActuallyTranscoding = (self.IsProcessing and 
                                   activeJobCount > 0 and 
                                   currentProgress is not None and
                                   hasJobsInQueue)
            
            # If no jobs in queue but IsProcessing is True, clean up stale state
            if self.IsProcessing and not hasJobsInQueue:
                LoggingService.LogInfo("No jobs in queue but IsProcessing=True, cleaning up stale state", "ProcessTranscodeQueueService", "GetStatus")
                self.CleanupStaleProgressData()
                self.IsProcessing = False
                self.ActiveJobs.clear()
                isActuallyTranscoding = False
            
            return {
                "Success": True,
                "IsTranscoding": isActuallyTranscoding,
                "MaxConcurrentJobs": self.MaxConcurrentJobs,
                "ActiveJobsCount": activeJobCount,
                "CurrentJob": currentJob,
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
        ActiveJobId = None  # Initialize for error handling
        try:
            LoggingService.LogInfo(f"Starting job processing for job ID: {Job.Id}", "ProcessTranscodeQueueService", "ProcessJob")
            
            # CREATE ACTIVE JOB RECORD
            ActiveJobId = self.DatabaseManager.CreateActiveJob(
                ServiceName="TranscodeService",
                JobType="Transcode",
                QueueId=Job.Id,
                ProcessId=os.getpid(),
                ThreadId=threading.get_ident()
            )
            
            if ActiveJobId == 0:
                LoggingService.LogError(f"Failed to create active job for queue ID {Job.Id}", 
                                       "ProcessTranscodeQueueService", "ProcessJob")
                self.HandleJobFailure(Job, "Failed to create active job record", None, ActiveJobId)
                return
            
            # Update queue status to Running
            self.DatabaseManager.UpdateTranscodeQueueStatus(Job.Id, "Running")
            
            # Create transcode attempt record early for progress tracking
            TranscodeAttemptId = self.CreateTranscodeAttempt(Job, None, None, None)
            if not TranscodeAttemptId:
                self.HandleJobFailure(Job, "Failed to create transcode attempt record", None, ActiveJobId)
                return
            
            # Phase 1: Initializing
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Initializing", 0.0, "Job started, getting ready")
            
            # Phase 2: Loading Media Data
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Loading Media Data", 0.0, "Loading file metadata...")
            
            # Step a: Get MediaFile data
            MediaFile = self.GetMediaFileData(Job)
            if not MediaFile:
                self.HandleJobFailure(Job, "Failed to get media file data", TranscodeAttemptId, ActiveJobId)
                return
            
            # Archive original file details before transcoding
            self.ArchiveOriginalFileDetails(MediaFile, TranscodeAttemptId)
            
            # Phase 3: Loading Settings
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Loading Settings", 0.0, "Loading transcoding profile settings...")
            
            # Step c: Get transcoding settings
            TranscodingSettings = self.GetTranscodingSettings(Job, MediaFile)
            if not TranscodingSettings:
                self.HandleJobFailure(Job, "Failed to get transcoding settings", TranscodeAttemptId, ActiveJobId)
                return
            
            # Phase 4: Building Command
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Building Command", 0.0, "Building FFmpeg command...")
            
            # Step d: Build transcoding command
            TranscodeCommand = self.BuildTranscodeCommand(Job, MediaFile, TranscodingSettings)
            if not TranscodeCommand:
                self.HandleJobFailure(Job, "Failed to build transcoding command", TranscodeAttemptId, ActiveJobId)
                return
            
            # Phase 5: Preparing Files
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Preparing Files", 0.0, "Preparing files for transcoding...")
            
            # Step b: Setup directories and copy file
            if not self.SetupFilePreparation(Job, MediaFile, TranscodeAttemptId):
                self.HandleJobFailure(Job, "Failed to setup file preparation", TranscodeAttemptId, ActiveJobId)
                return
            
            # Update attempt record with complete information
            self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                'FilePath': Job.FilePath,
                'AttemptDate': datetime.now(),
                'Quality': TranscodingSettings.get('ProfileSettings', {}).get('Quality', 0),
                'OldSizeBytes': Job.SizeBytes,
                'NewSizeBytes': 0,
                'Success': False,
                'SizeReductionBytes': 0,
                'SizeReductionPercent': 0.0,
                'ErrorMessage': None,
                'TranscodeDurationSeconds': 0.0,
                'FfpmpegCommand': TranscodeCommand,
                'AudioBitrateKbps': TranscodingSettings.get('ProfileSettings', {}).get('AudioBitrateKbps'),
                'VideoBitrateKbps': TranscodingSettings.get('ProfileSettings', {}).get('VideoBitrateKbps'),
                'ProfileName': MediaFile.AssignedProfile,
                'VMAF': None
            })
            
            # Phase 6: Starting Transcode
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Starting Transcode", 0.0, "Starting video processing...")
            
            # Step f: Execute transcoding
            TranscodeResult = self.ExecuteTranscoding(Job, TranscodeCommand, TranscodeAttemptId, MediaFile, ActiveJobId)
            if not TranscodeResult.get("Success", False):
                self.HandleJobFailure(Job, f"Transcoding failed: {TranscodeResult.get('ErrorMessage', 'Unknown error')}", TranscodeAttemptId, ActiveJobId)
                return
            
            # Phase 7: Finalizing
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Finalizing", 0.0, "Processing results and cleanup...")
            
            # Step g: Handle transcoding result
            self.HandleTranscodingResult(Job, TranscodeResult, TranscodeAttemptId, ActiveJobId)
            
            # Step h: Cleanup or continue
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
    
    def SetupFilePreparation(self, Job: TranscodeQueueModel, MediaFile: MediaFileModel, TranscodeAttemptId: int) -> bool:
        """Setup transcoding directories and copy source file."""
        try:
            # Setup directories
            if not self.FileManager.SetupTranscodingDirectories():
                return False
            
            # Copy file to source directory
            SourcePath = Job.FilePath
            DestinationPath = f"C:\\MediaVortex\\Source\\{MediaFile.FileName}"
            
            # Copy the file
            CopyResult = self.FileManager.CopyFile(SourcePath, DestinationPath)
            if not CopyResult:
                return False
            
            # Create TemporaryFilePaths record after successful file copy
            TemporaryFilePathId = self.PrivateCreateTemporaryFilePathRecord(TranscodeAttemptId, SourcePath, DestinationPath)
            if not TemporaryFilePathId:
                LoggingService.LogWarning(f"Failed to create TemporaryFilePath record for TranscodeAttempt {TranscodeAttemptId}, but file copy succeeded", 
                                        "ProcessTranscodeQueueService", "SetupFilePreparation")
                # Don't fail the entire operation if TemporaryFilePath creation fails
            
            return True
            
        except Exception as e:
            LoggingService.LogException("Exception in file preparation", e, "ProcessTranscodeQueueService", "SetupFilePreparation")
            self.PrivateHandleFilePreparationFailure(TranscodeAttemptId, str(e))
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
    
    def CreateTranscodeAttempt(self, Job: TranscodeQueueModel, MediaFile: MediaFileModel = None, 
                              TranscodingSettings: Dict[str, Any] = None, TranscodeCommand: str = None) -> Optional[int]:
        """Create a transcode attempt record for progress tracking."""
        try:
            # Handle None parameters for early creation
            if TranscodingSettings is None:
                TranscodingSettings = {}
            if MediaFile is None:
                MediaFile = type('MockMediaFile', (), {'AssignedProfile': None})()
            
            ProfileSettings = TranscodingSettings.get('ProfileSettings', {})
            CodecFlags = TranscodingSettings.get('CodecFlags', {})
            
            # Create attempt record
            Attempt = TranscodeAttemptModel(
                FilePath=Job.FilePath,
                AttemptDate=datetime.now(),
                Quality=ProfileSettings.get('Quality', 0),
                OldSizeBytes=Job.SizeBytes,
                NewSizeBytes=0,  # Will be updated after transcoding
                Success=None,  # Will be updated after transcoding
                SizeReductionBytes=0,  # Will be calculated after transcoding
                SizeReductionPercent=0.0,  # Will be calculated after transcoding
                ErrorMessage=None,
                TranscodeDurationSeconds=0.0,  # Will be updated after transcoding
                FfpmpegCommand=TranscodeCommand,
                AudioBitrateKbps=ProfileSettings.get('AudioBitrateKbps'),
                VideoBitrateKbps=ProfileSettings.get('VideoBitrateKbps'),
                ProfileName=MediaFile.AssignedProfile if hasattr(MediaFile, 'AssignedProfile') else None,
                VMAF=None,  # Will be set after VMAF analysis
                QualityTestRequired=1,  # Default to 1 (required)
                QualityTestCompleted=0  # Default to 0 (not completed)
            )
            
            return self.DatabaseManager.SaveTranscodeAttempt(Attempt)
            
        except Exception as e:
            LoggingService.LogException("Exception creating transcode attempt", e, "ProcessTranscodeQueueService", "CreateTranscodeAttempt")
            return None
    
    def GetTotalFramesWithFallback(self, Job: TranscodeQueueModel, MediaFile: MediaFileModel = None) -> int:
        """Get TotalFrames using ffprobe fallback since MediaFile.TotalFrames is empty."""
        try:
            # We're here because MediaFile.TotalFrames is empty/0, so go straight to ffprobe
            LoggingService.LogInfo(f"MediaFile.TotalFrames is empty for {Job.FilePath}, attempting ffprobe fallback", 
                                 "ProcessTranscodeQueueService", "GetTotalFramesWithFallback")
            
            # Import FFmpegAnalysisService for fallback
            from Services.FFmpegAnalysisService import FFmpegAnalysisService
            
            AnalysisService = FFmpegAnalysisService()
            AnalysisResult = AnalysisService.AnalyzeMediaFile(Job.FilePath)
            
            if AnalysisResult.Success and AnalysisResult.TotalFrames and AnalysisResult.TotalFrames > 0:
                LoggingService.LogInfo(f"Successfully extracted TotalFrames via ffprobe: {AnalysisResult.TotalFrames} frames", 
                                     "ProcessTranscodeQueueService", "GetTotalFramesWithFallback")
                
                # Update MediaFile with the extracted TotalFrames for future use
                if MediaFile:
                    MediaFile.TotalFrames = AnalysisResult.TotalFrames
                    self.DatabaseManager.SaveMediaFile(MediaFile)
                    LoggingService.LogInfo(f"Updated MediaFile.TotalFrames to {AnalysisResult.TotalFrames} for future transcodes", 
                                         "ProcessTranscodeQueueService", "GetTotalFramesWithFallback")
                
                return AnalysisResult.TotalFrames
            else:
                LoggingService.LogWarning(f"Both MediaFile.TotalFrames and ffprobe failed to extract TotalFrames for {Job.FilePath}. " +
                                        f"MediaFile.TotalFrames: {MediaFile.TotalFrames if MediaFile else 'N/A'}, " +
                                        f"FFprobe result: {AnalysisResult.TotalFrames if AnalysisResult else 'Failed'}", 
                                        "ProcessTranscodeQueueService", "GetTotalFramesWithFallback")
                return 0
                
        except Exception as e:
            LoggingService.LogException("Exception getting TotalFrames with fallback", e, "ProcessTranscodeQueueService", "GetTotalFramesWithFallback")
            return 0

    def ExecuteTranscoding(self, Job: TranscodeQueueModel, TranscodeCommand: str, TranscodeAttemptId: int, MediaFile: MediaFileModel = None, ActiveJobId: int = None) -> Dict[str, Any]:
        """Execute the transcoding command with progress tracking."""
        try:
            # Get TotalFrames from MediaFile if available, otherwise use fallback
            TotalFramesFromMediaFile = MediaFile.TotalFrames if MediaFile and MediaFile.TotalFrames else 0
            
            # If MediaFile.TotalFrames is empty, try ffprobe fallback
            if TotalFramesFromMediaFile == 0:
                TotalFramesFromMediaFile = self.GetTotalFramesWithFallback(Job, MediaFile)
            
            # Create initial progress record with TotalFrames from MediaFile
            self.DatabaseManager.SaveTranscodeProgress(
                TranscodeAttemptId=TranscodeAttemptId,
                CurrentPhase="Transcoding",
                ProgressPercent=0.0,
                CurrentFrame=0,
                CurrentFPS=0.0,
                CurrentBitrate="0kbits/s",
                CurrentTime="00:00:00",
                CurrentSpeed="0x",
                ETA="Unknown",
                TotalFrames=TotalFramesFromMediaFile,
                AverageFPS=0.0
            )
            
            # Create progress callback for real-time updates
            def ProgressCallback(ProgressData: Dict[str, Any]):
                try:
                    # Save progress to database immediately for real-time updates
                    self.DatabaseManager.SaveTranscodeProgress(
                        TranscodeAttemptId=TranscodeAttemptId,
                        CurrentPhase=ProgressData.get('CurrentPhase', 'Transcoding'),
                        ProgressPercent=ProgressData.get('ProgressPercent', 0.0),
                        CurrentFrame=ProgressData.get('CurrentFrame', 0),
                        CurrentFPS=ProgressData.get('CurrentFPS', 0.0),
                        CurrentBitrate=f"{ProgressData.get('CurrentBitrate', 0)}kbits/s",
                        CurrentTime=ProgressData.get('CurrentTime', '00:00:00'),
                        CurrentSpeed=ProgressData.get('CurrentSpeed', '0x'),
                        ETA=ProgressData.get('ETA', 'Unknown'),
                        TotalFrames=ProgressData.get('TotalFrames', TotalFramesFromMediaFile),
                        AverageFPS=ProgressData.get('AverageFPS', 0.0)
                    )
                except Exception as e:
                    LoggingService.LogException("Exception in progress callback", e, "ProcessTranscodeQueueService", "ExecuteTranscoding")
            
            return self.VideoTranscoding.TranscodeVideo(TranscodeAttemptId, TranscodeCommand, ProgressCallback, TotalFramesFromMediaFile, ActiveJobId, self.DatabaseManager)
            
        except Exception as e:
            LoggingService.LogException("Exception executing transcoding", e, "ProcessTranscodeQueueService", "ExecuteTranscoding")
            return {
                "Success": False,
                "ErrorMessage": f"Exception during transcoding: {str(e)}"
            }
    
    def HandleTranscodingResult(self, Job: TranscodeQueueModel, TranscodeResult: Dict[str, Any], TranscodeAttemptId: int, ActiveJobId: int = None):
        """Handle transcoding results - success or failure processing."""
        try:
            if TranscodeResult.get("Success", False):
                # Calculate output file size
                NewSizeBytes = 0
                SizeReductionBytes = 0
                SizeReductionPercent = 0.0
                
                # Get output file path from the transcoding command
                OutputFilePath = self.GetOutputFilePathFromCommand(Job)
                LoggingService.LogInfo(f"Output file path: {OutputFilePath}", "ProcessTranscodeQueueService", "HandleTranscodingResult")
                
                if OutputFilePath and os.path.exists(OutputFilePath):
                    NewSizeBytes = os.path.getsize(OutputFilePath)
                    OldSizeBytes = Job.SizeBytes
                    if OldSizeBytes > 0:
                        SizeReductionBytes = OldSizeBytes - NewSizeBytes
                        SizeReductionPercent = (SizeReductionBytes / OldSizeBytes) * 100
                    LoggingService.LogInfo(f"File sizes - Original: {OldSizeBytes} bytes, Transcoded: {NewSizeBytes} bytes, Reduction: {SizeReductionPercent:.1f}%", 
                                         "ProcessTranscodeQueueService", "HandleTranscodingResult")
                else:
                    LoggingService.LogWarning(f"Output file not found: {OutputFilePath}", "ProcessTranscodeQueueService", "HandleTranscodingResult")
                
                # Update attempt record with success details
                self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                    'Success': True,
                    'TranscodeDurationSeconds': TranscodeResult.get('Duration', 0.0),
                    'NewSizeBytes': NewSizeBytes,
                    'SizeReductionBytes': SizeReductionBytes,
                    'SizeReductionPercent': SizeReductionPercent,
                    'QualityTestRequired': True  # Mark for quality testing
                })
                
                # Update TranscodeFiles record for overall file status
                self.UpdateTranscodeFileRecord(Job.FilePath, TranscodeAttemptId, True, OutputFilePath, NewSizeBytes)
                
                # Update TemporaryFilePaths record with LocalOutputPath
                UpdateResult = self.PrivateUpdateTemporaryFilePathRecord(TranscodeAttemptId, OutputFilePath)
                if not UpdateResult:
                    LoggingService.LogWarning(f"Failed to update TemporaryFilePath record for TranscodeAttempt {TranscodeAttemptId}, but transcoding succeeded", 
                                            "ProcessTranscodeQueueService", "HandleTranscodingResult")
                
                # Let ShouldQualityTest service handle the complete process
                QualityTestResult = self.ShouldQualityTest.ProcessTranscodedFile(TranscodeAttemptId, Job.FilePath, OutputFilePath)
                
                if QualityTestResult["Success"]:
                    if QualityTestResult["QualityTestJobId"]:
                        LoggingService.LogInfo(f"Quality test job {QualityTestResult['QualityTestJobId']} created for TranscodeAttempt {TranscodeAttemptId}: {QualityTestResult['Message']}", 
                                             "ProcessTranscodeQueueService", "HandleTranscodingResult")
                    else:
                        LoggingService.LogInfo(f"Quality test processing completed for TranscodeAttempt {TranscodeAttemptId}: {QualityTestResult['Message']}", 
                                             "ProcessTranscodeQueueService", "HandleTranscodingResult")
                else:
                    LoggingService.LogError(f"Quality test processing failed for TranscodeAttempt {TranscodeAttemptId}: {QualityTestResult['Message']}", 
                                          "ProcessTranscodeQueueService", "HandleTranscodingResult")
                
                # Delete job from queue (successful completion)
                self.DatabaseManager.DeleteTranscodeQueueItem(Job.Id)
                
                # Clean up progress data for completed job
                self.DatabaseManager.DeleteTranscodeProgress(TranscodeAttemptId)
                
                # Complete active job if it exists
                if ActiveJobId:
                    self.DatabaseManager.CompleteActiveJob(ActiveJobId, Success=True)
                    LoggingService.LogInfo(f"Completed active job {ActiveJobId} for queue ID {Job.Id}", 
                                          "ProcessTranscodeQueueService", "HandleTranscodingResult")
                
                # Mark processing as complete if no more active jobs
                activeJobCount = len([thread for thread in self.ActiveJobs if thread.is_alive()])
                if activeJobCount == 0:
                    self.IsProcessing = False
                
                LoggingService.LogInfo(f"Job {Job.Id} completed successfully and removed from queue", "ProcessTranscodeQueueService", "HandleTranscodingResult")
            else:
                # Handle failure
                self.HandleJobFailure(Job, TranscodeResult.get('ErrorMessage', 'Unknown error'), TranscodeAttemptId, ActiveJobId)
                
        except Exception as e:
            LoggingService.LogException("Exception handling transcoding result", e, "ProcessTranscodeQueueService", "HandleTranscodingResult")
    
    def HandleJobFailure(self, Job: TranscodeQueueModel, ErrorMessage: str, TranscodeAttemptId: int = None, ActiveJobId: int = None):
        """Handle job failure by updating attempt record and removing from queue."""
        try:
            if TranscodeAttemptId:
                # Update existing attempt record with failure details
                self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                    'Success': False,
                    'ErrorMessage': ErrorMessage
                })
                
                # Update TranscodeFiles record for overall file status (failure)
                self.UpdateTranscodeFileRecord(Job.FilePath, TranscodeAttemptId, False)
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
                AttemptId = self.DatabaseManager.SaveTranscodeAttempt(Attempt)
                
                # Update TranscodeFiles record for overall file status (failure)
                self.UpdateTranscodeFileRecord(Job.FilePath, AttemptId, False)
            
            # Delete job from queue (failed completion)
            self.DatabaseManager.DeleteTranscodeQueueItem(Job.Id)
            
            # Clean up progress data for failed job (if we have an attempt ID)
            if TranscodeAttemptId:
                self.DatabaseManager.DeleteTranscodeProgress(TranscodeAttemptId)
            
            # Mark processing as complete if no more active jobs
            activeJobCount = len([thread for thread in self.ActiveJobs if thread.is_alive()])
            if activeJobCount == 0:
                self.IsProcessing = False
            
            # Complete active job if it exists
            if ActiveJobId:
                self.DatabaseManager.CompleteActiveJob(ActiveJobId, Success=False, ErrorMessage=ErrorMessage)
                LoggingService.LogInfo(f"Completed failed active job {ActiveJobId}", 
                                      "ProcessTranscodeQueueService", "HandleJobFailure")
            
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
    
    def GetOutputFilePathFromCommand(self, Job: TranscodeQueueModel) -> Optional[str]:
        """Get output file path for a transcoding job."""
        try:
            # Extract filename from input path
            InputFileName = os.path.basename(Job.FilePath)
            
            # Get the MediaFile to determine source resolution
            MediaFile = self.DatabaseManager.GetMediaFileByPath(Job.FilePath)
            if not MediaFile:
                LoggingService.LogWarning(f"Could not get MediaFile for {Job.FilePath}", "ProcessTranscodeQueueService", "GetOutputFilePathFromCommand")
                return os.path.join("C:\\MediaVortex", InputFileName)
            
            # Get transcoding settings to determine target resolution
            TranscodingSettings = self.GetTranscodingSettings(Job, MediaFile)
            if not TranscodingSettings:
                LoggingService.LogWarning(f"Could not get transcoding settings for {Job.FilePath}", "ProcessTranscodeQueueService", "GetOutputFilePathFromCommand")
                return os.path.join("C:\\MediaVortex", InputFileName)
            
            # Generate output filename with target resolution and container type
            ProfileSettings = TranscodingSettings.get('ProfileSettings', {})
            SourceResolution = TranscodingSettings.get('SourceResolution', '')
            TargetResolution = ProfileSettings.get('TargetResolution', '')
            ContainerType = ProfileSettings.get('ContainerType', 'mp4')
            
            OutputFileName = self._GenerateOutputFileName(InputFileName, SourceResolution, TargetResolution, ContainerType)
            OutputFilePath = os.path.join("C:\\MediaVortex", OutputFileName)
            
            LoggingService.LogInfo(f"Calculated output path: {OutputFilePath}", "ProcessTranscodeQueueService", "GetOutputFilePathFromCommand")
            return OutputFilePath
            
        except Exception as e:
            LoggingService.LogException("Exception getting output file path", e, "ProcessTranscodeQueueService", "GetOutputFilePathFromCommand")
            return None
    
    def UpdateTranscodeFileRecord(self, FilePath: str, TranscodeAttemptId: int, IsSuccess: bool, 
                                 FinalFilePath: str = None, FinalSizeBytes: int = None):
        """Update or create TranscodeFiles record for overall file transcoding status."""
        try:
            LoggingService.LogFunctionEntry("UpdateTranscodeFileRecord", "ProcessTranscodeQueueService", 
                                          FilePath, TranscodeAttemptId, IsSuccess)
            
            # Get attempt details to extract quality and other info
            Attempt = self.DatabaseManager.GetTranscodeAttemptById(TranscodeAttemptId)
            if not Attempt:
                LoggingService.LogWarning(f"Could not retrieve attempt {TranscodeAttemptId} for TranscodeFiles update", 
                                        "ProcessTranscodeQueueService", "UpdateTranscodeFileRecord")
                return
            
            # Check if TranscodeFile record already exists
            ExistingTranscodeFile = self.DatabaseManager.GetTranscodeFileByFilePath(FilePath)
            
            if ExistingTranscodeFile:
                # Update existing record
                LoggingService.LogInfo(f"Updating existing TranscodeFile record for {FilePath}", 
                                     "ProcessTranscodeQueueService", "UpdateTranscodeFileRecord")
                
                if IsSuccess:
                    # Success case - update with final details
                    self.DatabaseManager.UpdateTranscodeFileStatus(
                        FilePath=FilePath,
                        SuccessfullyTranscoded=True,
                        FinalQuality=Attempt.Quality,
                        FinalSizeBytes=FinalSizeBytes,
                        FinalFilePath=FinalFilePath
                    )
                    # Also update SuccessDate
                    TranscodeFile = TranscodeFileModel(
                        Id=ExistingTranscodeFile.Id,
                        FilePath=FilePath,
                        AllQualitiesFailed=ExistingTranscodeFile.AllQualitiesFailed,
                        SuccessfullyTranscoded=True,
                        FirstAttemptDate=ExistingTranscodeFile.FirstAttemptDate,
                        LastAttemptDate=datetime.now(),
                        SuccessDate=datetime.now(),
                        FinalQuality=Attempt.Quality,
                        FinalSizeBytes=FinalSizeBytes,
                        TotalAttempts=ExistingTranscodeFile.TotalAttempts + 1,
                        OriginalFilePath=ExistingTranscodeFile.OriginalFilePath,
                        FinalFilePath=FinalFilePath
                    )
                    self.DatabaseManager.SaveTranscodeFile(TranscodeFile)
                else:
                    # Failure case - increment attempts, update last attempt date
                    TranscodeFile = TranscodeFileModel(
                        Id=ExistingTranscodeFile.Id,
                        FilePath=FilePath,
                        AllQualitiesFailed=ExistingTranscodeFile.AllQualitiesFailed,
                        SuccessfullyTranscoded=ExistingTranscodeFile.SuccessfullyTranscoded,
                        FirstAttemptDate=ExistingTranscodeFile.FirstAttemptDate,
                        LastAttemptDate=datetime.now(),
                        SuccessDate=ExistingTranscodeFile.SuccessDate,
                        FinalQuality=ExistingTranscodeFile.FinalQuality,
                        FinalSizeBytes=ExistingTranscodeFile.FinalSizeBytes,
                        TotalAttempts=ExistingTranscodeFile.TotalAttempts + 1,
                        OriginalFilePath=ExistingTranscodeFile.OriginalFilePath,
                        FinalFilePath=ExistingTranscodeFile.FinalFilePath
                    )
                    self.DatabaseManager.SaveTranscodeFile(TranscodeFile)
            else:
                # Create new record
                LoggingService.LogInfo(f"Creating new TranscodeFile record for {FilePath}", 
                                     "ProcessTranscodeQueueService", "UpdateTranscodeFileRecord")
                
                CurrentTime = datetime.now()
                TranscodeFile = TranscodeFileModel(
                    FilePath=FilePath,
                    AllQualitiesFailed=not IsSuccess,  # If first attempt fails, mark as all qualities failed
                    SuccessfullyTranscoded=IsSuccess,
                    FirstAttemptDate=CurrentTime,
                    LastAttemptDate=CurrentTime,
                    SuccessDate=CurrentTime if IsSuccess else None,
                    FinalQuality=Attempt.Quality if IsSuccess else None,
                    FinalSizeBytes=FinalSizeBytes if IsSuccess else None,
                    TotalAttempts=1,
                    OriginalFilePath=FilePath,
                    FinalFilePath=FinalFilePath if IsSuccess else None
                )
                self.DatabaseManager.SaveTranscodeFile(TranscodeFile)
            
            LoggingService.LogInfo(f"TranscodeFile record updated for {FilePath}, Success: {IsSuccess}", 
                                 "ProcessTranscodeQueueService", "UpdateTranscodeFileRecord")
            
        except Exception as e:
            LoggingService.LogException("Exception updating TranscodeFile record", e, 
                                      "ProcessTranscodeQueueService", "UpdateTranscodeFileRecord")
    
    def _GenerateOutputFileName(self, OriginalFileName: str, SourceResolution: str, TargetResolution: str, ContainerType: str = 'mp4') -> str:
        """Generate output filename with target resolution and container type."""
        try:
            # Get the base filename without extension
            BaseName = os.path.splitext(OriginalFileName)[0]
            
            # If resolutions are the same, just change extension
            if SourceResolution == TargetResolution:
                return f"{BaseName}.{ContainerType}"
            
            # Extract resolution from filename (e.g., "1080p", "720p")
            SourceResolutionStr = self._ExtractResolutionFromFilename(OriginalFileName)
            if not SourceResolutionStr:
                # If no resolution found in filename, add target resolution
                TargetResolutionStr = self._FormatResolutionForFilename(TargetResolution)
                return f"{BaseName}{TargetResolutionStr}.{ContainerType}"
            
            # Replace source resolution with target resolution
            TargetResolutionStr = self._FormatResolutionForFilename(TargetResolution)
            NewBaseName = OriginalFileName.replace(SourceResolutionStr, TargetResolutionStr)
            NewBaseName = os.path.splitext(NewBaseName)[0]  # Remove old extension
            
            # Add container type extension
            return f"{NewBaseName}.{ContainerType}"
            
        except Exception:
            # If anything goes wrong, return original filename with container extension
            BaseName = os.path.splitext(OriginalFileName)[0]
            return f"{BaseName}.{ContainerType}"
    
    def _ExtractResolutionFromFilename(self, Filename: str) -> Optional[str]:
        """Extract resolution string from filename (e.g., '1080p', '720p')."""
        try:
            import re
            # Look for resolution patterns like 1080p, 720p, 480p, 4K, etc.
            ResolutionPatterns = [
                r'\b2160p\b',  # 4K
                r'\b1080p\b',  # Full HD
                r'\b720p\b',   # HD
                r'\b480p\b',   # SD
                r'\b4K\b',     # 4K alternative
                r'\bHD\b',     # HD alternative
                r'\bSD\b'      # SD alternative
            ]
            
            for pattern in ResolutionPatterns:
                match = re.search(pattern, Filename, re.IGNORECASE)
                if match:
                    return match.group(0)
            
            return None
            
        except Exception:
            return None
    
    def _FormatResolutionForFilename(self, Resolution: str) -> str:
        """Format resolution for use in filename."""
        try:
            # Convert resolution categories to standard format
            if Resolution == '2160p' or Resolution == '4K':
                return '2160p'
            elif Resolution == '1080p':
                return '1080p'
            elif Resolution == '720p':
                return '720p'
            elif Resolution == '480p':
                return '480p'
            else:
                # For any other resolution, try to extract height and add 'p'
                if 'x' in Resolution:
                    height = Resolution.split('x')[1]
                    return f"{height}p"
                else:
                    return Resolution
                    
        except Exception:
            return Resolution
    
    def StopAllActiveTranscodingProcesses(self):
        """Stop all active video transcoding processes."""
        try:
            LoggingService.LogFunctionEntry("StopAllActiveTranscodingProcesses", "ProcessTranscodeQueueService")
            
            # Get all active job IDs from VideoTranscoding service
            activeJobIds = self.VideoTranscoding.GetActiveJobs()
            
            for jobId in activeJobIds:
                try:
                    result = self.VideoTranscoding.StopTranscoding(jobId)
                    if result.get("Success", False):
                        LoggingService.LogInfo(f"Stopped transcoding process for job {jobId}", "ProcessTranscodeQueueService", "StopAllActiveTranscodingProcesses")
                    else:
                        LoggingService.LogWarning(f"Failed to stop transcoding process for job {jobId}: {result.get('ErrorMessage', 'Unknown error')}", "ProcessTranscodeQueueService", "StopAllActiveTranscodingProcesses")
                except Exception as e:
                    LoggingService.LogException(f"Exception stopping transcoding process for job {jobId}", e, "ProcessTranscodeQueueService", "StopAllActiveTranscodingProcesses")
            
            LoggingService.LogInfo(f"Stopped {len(activeJobIds)} active transcoding processes", "ProcessTranscodeQueueService", "StopAllActiveTranscodingProcesses")
            
        except Exception as e:
            LoggingService.LogException("Exception stopping active transcoding processes", e, "ProcessTranscodeQueueService", "StopAllActiveTranscodingProcesses")
    
    
    def CleanupStaleProgressData(self):
        """Clean up any stale progress data from the database."""
        try:
            LoggingService.LogFunctionEntry("CleanupStaleProgressData", "ProcessTranscodeQueueService")
            
            # Get all current progress records
            currentProgress = self.DatabaseManager.GetCurrentTranscodeProgress()
            if currentProgress:
                # Delete all progress records to clean up stale data
                query = "DELETE FROM TranscodeProgress"
                affectedRows = self.DatabaseManager.DatabaseService.ExecuteNonQuery(query)
                LoggingService.LogInfo(f"Cleaned up {affectedRows} stale progress records", "ProcessTranscodeQueueService", "CleanupStaleProgressData")
            
        except Exception as e:
            LoggingService.LogException("Exception cleaning up stale progress data", e, "ProcessTranscodeQueueService", "CleanupStaleProgressData")
    
    def UpdateTranscodeProgress(self, TranscodeAttemptId: int, CurrentPhase: str, 
                              ProgressPercent: float = 0.0, AdditionalInfo: str = ""):
        """Update transcoding progress with current phase and optional progress."""
        try:
            LoggingService.LogInfo(f"Updating progress: {CurrentPhase} ({ProgressPercent}%) - {AdditionalInfo}", 
                                 "ProcessTranscodeQueueService", "UpdateTranscodeProgress")
            
            # Save progress to database
            self.DatabaseManager.SaveTranscodeProgress(
                TranscodeAttemptId=TranscodeAttemptId,
                CurrentPhase=CurrentPhase,
                ProgressPercent=ProgressPercent,
                CurrentFrame=0,  # Will be updated during transcoding phase
                CurrentFPS=0.0,
                CurrentBitrate="0kbits/s",
                CurrentTime="00:00:00",
                CurrentSpeed="0x",
                ETA="Unknown",
                TotalFrames=0,  # Will be updated during transcoding phase
                AverageFPS=0.0
            )
            
        except Exception as e:
            LoggingService.LogException("Exception updating transcoding progress", e, 
                                      "ProcessTranscodeQueueService", "UpdateTranscodeProgress")
    
    def ArchiveOriginalFileDetails(self, MediaFile: MediaFileModel, TranscodeAttemptId: int) -> bool:
        """Archive original file details before transcoding to preserve source data."""
        try:
            LoggingService.LogFunctionEntry("ArchiveOriginalFileDetails", "ProcessTranscodeQueueService", 
                                          MediaFile.Id, TranscodeAttemptId)
            
            # Archive original file details using INSERT SELECT
            ArchiveId = self.DatabaseManager.SaveMediaFileArchive(MediaFile.Id, TranscodeAttemptId)
            
            if ArchiveId:
                LoggingService.LogInfo(f"Successfully archived original file details for MediaFile {MediaFile.Id}, Archive ID: {ArchiveId}", 
                                     "ProcessTranscodeQueueService", "ArchiveOriginalFileDetails")
                return True
            else:
                LoggingService.LogError(f"Failed to archive original file details for MediaFile {MediaFile.Id}", 
                                      "ProcessTranscodeQueueService", "ArchiveOriginalFileDetails")
                return False
                
        except Exception as e:
            LoggingService.LogException("Exception archiving original file details", e, 
                                      "ProcessTranscodeQueueService", "ArchiveOriginalFileDetails")
            return False
    
    def PrivateCreateTemporaryFilePathRecord(self, TranscodeAttemptId: int, OriginalPath: str, LocalSourcePath: str) -> Optional[int]:
        """Private method to create TemporaryFilePath record."""
        try:
            LoggingService.LogFunctionEntry("PrivateCreateTemporaryFilePathRecord", "ProcessTranscodeQueueService", 
                                          TranscodeAttemptId, OriginalPath, LocalSourcePath)
            
            TemporaryFilePathId = self.DatabaseManager.CreateTemporaryFilePath(TranscodeAttemptId, OriginalPath, LocalSourcePath)
            
            if TemporaryFilePathId:
                LoggingService.LogInfo(f"Successfully created TemporaryFilePath record {TemporaryFilePathId} for TranscodeAttempt {TranscodeAttemptId}", 
                                     "ProcessTranscodeQueueService", "PrivateCreateTemporaryFilePathRecord")
                return TemporaryFilePathId
            else:
                LoggingService.LogError(f"Failed to create TemporaryFilePath record for TranscodeAttempt {TranscodeAttemptId}", 
                                      "ProcessTranscodeQueueService", "PrivateCreateTemporaryFilePathRecord")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception creating TemporaryFilePath record", e, 
                                      "ProcessTranscodeQueueService", "PrivateCreateTemporaryFilePathRecord")
            return None
    
    def PrivateHandleFilePreparationFailure(self, TranscodeAttemptId: int, ErrorMessage: str):
        """Private method to handle file preparation failures."""
        try:
            LoggingService.LogFunctionEntry("PrivateHandleFilePreparationFailure", "ProcessTranscodeQueueService", 
                                          TranscodeAttemptId, ErrorMessage)
            
            # Clean up any partial TemporaryFilePath records
            self.DatabaseManager.DeleteTemporaryFilePath(TranscodeAttemptId)
            
            LoggingService.LogError(f"File preparation failed for TranscodeAttempt {TranscodeAttemptId}: {ErrorMessage}", 
                                  "ProcessTranscodeQueueService", "PrivateHandleFilePreparationFailure")
            
        except Exception as e:
            LoggingService.LogException("Exception handling file preparation failure", e, 
                                      "ProcessTranscodeQueueService", "PrivateHandleFilePreparationFailure")
    
    def PrivateUpdateTemporaryFilePathRecord(self, TranscodeAttemptId: int, LocalOutputPath: str) -> bool:
        """Private method to update TemporaryFilePath record with LocalOutputPath."""
        try:
            LoggingService.LogFunctionEntry("PrivateUpdateTemporaryFilePathRecord", "ProcessTranscodeQueueService", 
                                          TranscodeAttemptId, LocalOutputPath)
            
            UpdateResult = self.DatabaseManager.UpdateTemporaryFilePath(TranscodeAttemptId, LocalOutputPath)
            
            if UpdateResult:
                LoggingService.LogInfo(f"Successfully updated TemporaryFilePath record for TranscodeAttempt {TranscodeAttemptId} with LocalOutputPath: {LocalOutputPath}", 
                                     "ProcessTranscodeQueueService", "PrivateUpdateTemporaryFilePathRecord")
                return True
            else:
                LoggingService.LogError(f"Failed to update TemporaryFilePath record for TranscodeAttempt {TranscodeAttemptId}", 
                                      "ProcessTranscodeQueueService", "PrivateUpdateTemporaryFilePathRecord")
                return False
                
        except Exception as e:
            LoggingService.LogException("Exception updating TemporaryFilePath record", e, 
                                      "ProcessTranscodeQueueService", "PrivateUpdateTemporaryFilePathRecord")
            return False
    
    def PrivateGetTemporaryFilePaths(self, TranscodeAttemptId: int) -> Optional[Dict[str, Any]]:
        """Private method to get TemporaryFilePath record."""
        try:
            LoggingService.LogFunctionEntry("PrivateGetTemporaryFilePaths", "ProcessTranscodeQueueService", TranscodeAttemptId)
            
            TemporaryFilePathRecord = self.DatabaseManager.GetTemporaryFilePath(TranscodeAttemptId)
            
            if TemporaryFilePathRecord:
                LoggingService.LogInfo(f"Retrieved TemporaryFilePath record for TranscodeAttempt {TranscodeAttemptId}", 
                                     "ProcessTranscodeQueueService", "PrivateGetTemporaryFilePaths")
                return TemporaryFilePathRecord
            else:
                LoggingService.LogWarning(f"No TemporaryFilePath record found for TranscodeAttempt {TranscodeAttemptId}", 
                                        "ProcessTranscodeQueueService", "PrivateGetTemporaryFilePaths")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception getting TemporaryFilePath record", e, 
                                      "ProcessTranscodeQueueService", "PrivateGetTemporaryFilePaths")
            return None
    
    def PrivateCreateQualityTestWithCorrectPaths(self, TranscodeAttemptId: int, TemporaryFilePathRecord: Dict[str, Any]) -> Optional[int]:
        """Private method to create quality test with correct file paths from TemporaryFilePaths table."""
        try:
            LoggingService.LogFunctionEntry("PrivateCreateQualityTestWithCorrectPaths", "ProcessTranscodeQueueService", 
                                          TranscodeAttemptId, TemporaryFilePathRecord)
            
            # Use LocalSourcePath and LocalOutputPath from TemporaryFilePaths table
            LocalSourcePath = TemporaryFilePathRecord.get('LocalSourcePath')
            LocalOutputPath = TemporaryFilePathRecord.get('LocalOutputPath')
            
            if not LocalSourcePath or not LocalOutputPath:
                LoggingService.LogError(f"Missing LocalSourcePath or LocalOutputPath in TemporaryFilePath record for TranscodeAttempt {TranscodeAttemptId}", 
                                      "ProcessTranscodeQueueService", "PrivateCreateQualityTestWithCorrectPaths")
                return None
            
            # Create quality test queue entry with all three file paths
            QualityTestJobId = self.DatabaseManager.CreateQualityTestQueueEntry(
                TranscodeAttemptId, TemporaryFilePathRecord.get('OriginalPath'), LocalSourcePath, LocalOutputPath
            )
            
            if QualityTestJobId:
                LoggingService.LogInfo(f"Created quality test job {QualityTestJobId} with correct local file paths for TranscodeAttempt {TranscodeAttemptId}", 
                                     "ProcessTranscodeQueueService", "PrivateCreateQualityTestWithCorrectPaths")
                return QualityTestJobId
            else:
                LoggingService.LogError(f"Failed to create quality test job with correct paths for TranscodeAttempt {TranscodeAttemptId}", 
                                      "ProcessTranscodeQueueService", "PrivateCreateQualityTestWithCorrectPaths")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception creating quality test with correct paths", e, 
                                      "ProcessTranscodeQueueService", "PrivateCreateQualityTestWithCorrectPaths")
            return None
    
