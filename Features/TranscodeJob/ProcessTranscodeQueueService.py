from typing import Dict, Any, Optional, Callable
from datetime import datetime
import threading
import time
import os
import re
from Features.TranscodeQueue.Models.TranscodeQueueModel import TranscodeQueueModel
from Core.Models.MediaFileModel import MediaFileModel
from Core.Models.TranscodeAttemptModel import TranscodeAttemptModel
from Core.Models.TranscodeFileModel import TranscodeFileModel
from Repositories.DatabaseManager import DatabaseManager
from Features.TranscodeJob.TranscodingFileManagerService import TranscodingFileManagerService
from Services.CommandBuilderService import CommandBuilderService
from Features.TranscodeJob.VideoTranscodingService import VideoTranscodingService
from Services.QueueManagementService import QueueManagementService
from Services.ShouldQualityTestService import ShouldQualityTestService
from Core.Logging.LoggingService import LoggingService


class ProcessTranscodeQueueService:
    """Orchestrates the complete transcoding queue processing workflow using MVVM architecture."""

    def __init__(self, DatabaseManagerInstance: DatabaseManager = None,
                 FileManagerInstance: TranscodingFileManagerService = None,
                 CommandBuilderInstance: CommandBuilderService = None,
                 VideoTranscodingInstance: VideoTranscodingService = None,
                 QueueManagementInstance: QueueManagementService = None,
                 ShouldQualityTestInstance: ShouldQualityTestService = None,
                 WorkerName: str = None,
                 WorkerConfig: dict = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.FileManager = FileManagerInstance or TranscodingFileManagerService()
        self.CommandBuilder = CommandBuilderInstance or CommandBuilderService()
        self.VideoTranscoding = VideoTranscodingInstance or VideoTranscodingService()
        self.QueueManagement = QueueManagementInstance or QueueManagementService(DatabaseManagerInstance=self.DatabaseManager)
        self.ShouldQualityTest = ShouldQualityTestInstance or ShouldQualityTestService()

        # Worker identity for distributed transcoding
        import socket
        self.WorkerName = WorkerName or socket.gethostname()
        self.WorkerConfig = WorkerConfig or {}

        # Worker-specific paths (from Workers table, with fallback defaults)
        self.FFmpegPath = self.WorkerConfig.get('FFmpegPath') or self.WorkerConfig.get('ffmpegpath')
        self.FFprobePath = self.WorkerConfig.get('FFprobePath') or self.WorkerConfig.get('ffprobepath')
        self.OutputDirectory = self.WorkerConfig.get('StagingDirectory') or self.WorkerConfig.get('stagingdirectory')

        # Per-worker CPU thread limit (NULL = use global SystemSettings.MaxCpuThreads)
        RawMaxCpu = self.WorkerConfig.get('MaxCpuThreads') or self.WorkerConfig.get('maxcputhreads')
        self.MaxCpuThreads = int(RawMaxCpu) if RawMaxCpu else None

        # Interlaced routing: FALSE = skip interlaced files, leave for capable workers
        RawAccepts = self.WorkerConfig.get('AcceptsInterlaced') or self.WorkerConfig.get('acceptsinterlaced')
        self.AcceptsInterlaced = RawAccepts if RawAccepts is not None else True

        # VMAF quality test: per-worker override (NULL = use global setting)
        RawWorkerQT = self.WorkerConfig.get('QualityTestEnabled') or self.WorkerConfig.get('qualitytestenabled')
        self.WorkerQualityTestEnabled = RawWorkerQT  # None means "use global"

        # Path translation service for cross-platform support
        # MountMap is a {DriveLetter: LocalMountPrefix} dict from WorkerShareMappings table
        self.PathTranslation = None
        MountMap = self.WorkerConfig.get('ShareMappings') or {}
        if MountMap:
            from Core.Services.PathTranslationService import PathTranslationService
            self.PathTranslation = PathTranslationService(MountMap=MountMap)

        # Processing state
        self.IsProcessing = False
        self.MaxConcurrentJobs = 1
        self.ActiveJobs = []
        self.ProcessingThread = None
        self.StopRequested = False

        # Stuck job monitoring
        self.StuckJobMonitoringThread = None
        self.StuckJobMonitoringActive = False

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

            # Clean up any stuck jobs before starting
            self.DetectAndCleanStuckJobsBeforeStart()

            # Start processing in background thread
            self.ProcessingThread = threading.Thread(target=self.ProcessQueueLoop, daemon=True)
            self.ProcessingThread.start()

            # Start stuck job monitoring thread
            self.StartStuckJobMonitoring()

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

            # Reset this worker's running jobs to pending status
            resetResult = self.QueueManagement.ResetRunningJobsToPending("TranscodeQueue", "Transcoding cancelled by user stop request", WorkerName=self.WorkerName)
            if resetResult.get("Success", False):
                LoggingService.LogInfo(f"Queue reset completed: {resetResult.get('Message', '')}",
                                     "ProcessTranscodeQueueService", "Stop")
            else:
                LoggingService.LogWarning(f"Queue reset failed: {resetResult.get('ErrorMessage', 'Unknown error')}",
                                        "ProcessTranscodeQueueService", "Stop")

            # Clean up any stale progress data from database
            self.CleanupStaleProgressData()

            # Stop stuck job monitoring
            self.StopStuckJobMonitoring()

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
                # Check if service is paused
                try:
                    service_status = self.DatabaseManager.GetServiceStatus("TranscodeService")
                    if service_status and service_status.get('Status') == 'Paused':
                        LoggingService.LogInfo("TranscodeService is paused, skipping queue processing",
                                             "ProcessTranscodeQueueService", "ProcessQueueLoop")
                        time.sleep(5)
                        continue
                except Exception as e:
                    LoggingService.LogException("Error checking service status", e,
                                              "ProcessTranscodeQueueService", "ProcessQueueLoop")

                # Check thermal clearance before starting new job
                from Services.CpuAffinityService import GetCpuAffinityServiceInstance
                CpuAffinityServiceInstance = GetCpuAffinityServiceInstance()
                if CpuAffinityServiceInstance.CpuAffinityEnabled and CpuAffinityServiceInstance.ThermalGateEnabled:
                    ThermalReady = CpuAffinityServiceInstance.WaitForThermalClearance(CoreCount=0)
                    if not ThermalReady:
                        LoggingService.LogWarning("Thermal clearance timeout — starting job anyway",
                                                 "ProcessTranscodeQueueService", "ProcessQueueLoop")

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
        """Get and atomically claim the next pending job from the queue.
        Uses SELECT FOR UPDATE SKIP LOCKED for safe distributed operation.
        Respects AcceptsInterlaced worker setting to skip interlaced files."""
        try:
            return self.DatabaseManager.ClaimNextPendingTranscodeJob(self.WorkerName, AcceptsInterlaced=self.AcceptsInterlaced)
        except Exception as e:
            LoggingService.LogException("Exception getting next job", e, "ProcessTranscodeQueueService", "GetNextJob")
            return None

    def ProcessJob(self, Job: TranscodeQueueModel):
        """Process a single transcoding job through the complete workflow."""
        # Branch on processing mode
        if Job.IsRemux:
            self.ProcessRemuxJob(Job)
            return
        if Job.IsSubtitleFix:
            self.ProcessSubtitleFixJob(Job)
            return

        ActiveJobId = None  # Initialize for error handling
        try:
            LoggingService.LogInfo(f"Starting job processing for job ID: {Job.Id}", "ProcessTranscodeQueueService", "ProcessJob")

            # CREATE ACTIVE JOB RECORD
            ActiveJobId = self.DatabaseManager.CreateActiveJob(
                ServiceName="TranscodeService",
                JobType="Transcode",
                QueueId=Job.Id,
                ProcessId=os.getpid(),
                ThreadId=threading.get_ident(),
                WorkerName=self.WorkerName
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

            # Phase 4: Preparing Files (must happen before command building — FFprobe needs the staged file)
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Preparing Files", 0.0, "Preparing files for transcoding...")

            # Step b: Setup directories and optionally copy file
            EffectiveInputPath = self.SetupFilePreparation(Job, MediaFile, TranscodeAttemptId)
            if not EffectiveInputPath:
                self.HandleJobFailure(Job, "Failed to setup file preparation", TranscodeAttemptId, ActiveJobId)
                return

            # Phase 5: Building Command
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Building Command", 0.0, "Building FFmpeg command...")

            # Step d: Build transcoding command (pass effective input path)
            TranscodingSettings['InputPath'] = EffectiveInputPath
            CommandResult = self.BuildTranscodeCommand(Job, MediaFile, TranscodingSettings)
            if not CommandResult:
                self.HandleJobFailure(Job, "Failed to build transcoding command", TranscodeAttemptId, ActiveJobId)
                return

            # Extract command and output path from result
            TranscodeCommand = CommandResult['Command']
            OutputPath = CommandResult['OutputPath']

            # Create TemporaryFilePaths record with CANONICAL paths (so VMAF/FileReplacement on any machine can find files)
            # OriginalPath is already canonical (from Job.FilePath in DB)
            # LocalSourcePath and OutputPath must be converted back to canonical if this is a remote worker
            CanonicalSourcePath = Job.FilePath  # Already canonical
            CanonicalOutputPath = OutputPath
            if self.PathTranslation:
                CanonicalOutputPath = self.PathTranslation.ToCanonicalPath(OutputPath)
            TemporaryFilePathId = self.PrivateCreateTemporaryFilePathRecord(TranscodeAttemptId, Job.FilePath, CanonicalSourcePath, CanonicalOutputPath)
            if not TemporaryFilePathId:
                LoggingService.LogWarning(f"Failed to create TemporaryFilePath record for TranscodeAttempt {TranscodeAttemptId}, but file preparation succeeded",
                                        "ProcessTranscodeQueueService", "ProcessJob")
                # Don't fail the entire operation if TemporaryFilePath creation fails

            # Update attempt record with complete information (keep Success=None to indicate in-progress)
            self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                'FilePath': Job.FilePath,
                'AttemptDate': datetime.now(),
                'Quality': TranscodingSettings.get('ProfileSettings', {}).get('Quality', 0),
                'OldSizeBytes': Job.SizeBytes,
                'NewSizeBytes': 0,
                'Success': None,
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

    def ProcessRemuxJob(self, Job: TranscodeQueueModel):
        """Process a remux (compatibility-only) job: copy video, handle audio, change container to MP4."""
        ActiveJobId = None
        TranscodeAttemptId = None
        try:
            LoggingService.LogInfo(f"Starting remux job processing for job ID: {Job.Id}", "ProcessTranscodeQueueService", "ProcessRemuxJob")

            # Create active job record
            ActiveJobId = self.DatabaseManager.CreateActiveJob(
                ServiceName="TranscodeService",
                JobType="Remux",
                QueueId=Job.Id,
                ProcessId=os.getpid(),
                ThreadId=threading.get_ident(),
                WorkerName=self.WorkerName
            )
            if ActiveJobId == 0:
                self.HandleJobFailure(Job, "Failed to create active job record for remux", None, ActiveJobId)
                return

            # Update queue status to Running
            self.DatabaseManager.UpdateTranscodeQueueStatus(Job.Id, "Running")

            # Create transcode attempt record
            TranscodeAttemptId = self.CreateTranscodeAttempt(Job, None, None, None)
            if not TranscodeAttemptId:
                self.HandleJobFailure(Job, "Failed to create transcode attempt record for remux", None, ActiveJobId)
                return

            self.UpdateTranscodeProgress(TranscodeAttemptId, "Initializing", 0.0, "Starting remux (container change)...")

            # Get MediaFile data
            MediaFile = self.GetMediaFileData(Job)
            if not MediaFile:
                self.HandleJobFailure(Job, "Failed to get media file data for remux", TranscodeAttemptId, ActiveJobId)
                return

            self.ArchiveOriginalFileDetails(MediaFile, TranscodeAttemptId)

            # Setup file preparation first (copy or in-place based on setting)
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Preparing Files", 0.0, "Preparing source file...")
            EffectiveInputPath = self.SetupFilePreparation(Job, MediaFile, TranscodeAttemptId)
            if not EffectiveInputPath:
                self.HandleJobFailure(Job, "Failed to setup file preparation for remux", TranscodeAttemptId, ActiveJobId)
                return

            # Build remux command (pass effective input path)
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Building Command", 0.0, "Building remux command...")
            CommandResult = self.CommandBuilder.BuildRemuxCommand(Job, MediaFile, InputPath=EffectiveInputPath, TranscodingSettings={'FFmpegPath': self.FFmpegPath, 'OutputDirectory': self.OutputDirectory})
            if not CommandResult:
                self.HandleJobFailure(Job, "Failed to build remux command", TranscodeAttemptId, ActiveJobId)
                return

            RemuxCommand = CommandResult['Command']
            OutputPath = CommandResult['OutputPath']

            # Create TemporaryFilePaths record with canonical paths
            CanonicalOutputPath = OutputPath
            if self.PathTranslation:
                CanonicalOutputPath = self.PathTranslation.ToCanonicalPath(OutputPath)
            TemporaryFilePathId = self.PrivateCreateTemporaryFilePathRecord(TranscodeAttemptId, Job.FilePath, Job.FilePath, CanonicalOutputPath)

            # Update attempt record (keep Success=None to indicate in-progress)
            self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                'FilePath': Job.FilePath,
                'AttemptDate': datetime.now(),
                'Quality': 0,
                'OldSizeBytes': Job.SizeBytes,
                'NewSizeBytes': 0,
                'Success': None,
                'FfpmpegCommand': RemuxCommand,
                'ProfileName': 'Remux',
                'VMAF': None
            })

            # Execute remux
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Remuxing", 0.0, "Remuxing to MP4...")
            TranscodeResult = self.ExecuteTranscoding(Job, RemuxCommand, TranscodeAttemptId, MediaFile, ActiveJobId)
            if not TranscodeResult.get("Success", False):
                self.HandleJobFailure(Job, f"Remux failed: {TranscodeResult.get('ErrorMessage', 'Unknown error')}", TranscodeAttemptId, ActiveJobId)
                return

            # Handle result - skip quality testing for remux
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Finalizing", 0.0, "Finalizing remux...")
            self.HandleRemuxResult(Job, TranscodeResult, TranscodeAttemptId, ActiveJobId, OutputPath)
            self.CleanupOrContinue(Job)

            LoggingService.LogInfo(f"Completed remux job processing for job ID: {Job.Id}", "ProcessTranscodeQueueService", "ProcessRemuxJob")

        except Exception as e:
            LoggingService.LogException(f"Exception processing remux job {Job.Id}", e, "ProcessTranscodeQueueService", "ProcessRemuxJob")
            self.HandleJobFailure(Job, f"Exception during remux: {str(e)}", TranscodeAttemptId, ActiveJobId)

    def ProcessSubtitleFixJob(self, Job: TranscodeQueueModel):
        """Process a subtitle fix job: copy video+audio, convert ASS/SSA subtitle to mov_text, output MP4."""
        ActiveJobId = None
        TranscodeAttemptId = None
        try:
            LoggingService.LogInfo(f"Starting subtitle fix job processing for job ID: {Job.Id}", "ProcessTranscodeQueueService", "ProcessSubtitleFixJob")

            # Create active job record
            ActiveJobId = self.DatabaseManager.CreateActiveJob(
                ServiceName="TranscodeService",
                JobType="SubtitleFix",
                QueueId=Job.Id,
                ProcessId=os.getpid(),
                ThreadId=threading.get_ident(),
                WorkerName=self.WorkerName
            )
            if ActiveJobId == 0:
                self.HandleJobFailure(Job, "Failed to create active job record for subtitle fix", None, ActiveJobId)
                return

            # Update queue status to Running
            self.DatabaseManager.UpdateTranscodeQueueStatus(Job.Id, "Running")

            # Create transcode attempt record
            TranscodeAttemptId = self.CreateTranscodeAttempt(Job, None, None, None)
            if not TranscodeAttemptId:
                self.HandleJobFailure(Job, "Failed to create transcode attempt record for subtitle fix", None, ActiveJobId)
                return

            self.UpdateTranscodeProgress(TranscodeAttemptId, "Initializing", 0.0, "Starting subtitle fix (ASS/SSA → mov_text)...")

            # Get MediaFile data
            MediaFile = self.GetMediaFileData(Job)
            if not MediaFile:
                self.HandleJobFailure(Job, "Failed to get media file data for subtitle fix", TranscodeAttemptId, ActiveJobId)
                return

            self.ArchiveOriginalFileDetails(MediaFile, TranscodeAttemptId)

            # Setup file preparation first (copy or in-place based on setting)
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Preparing Files", 0.0, "Preparing source file...")
            EffectiveInputPath = self.SetupFilePreparation(Job, MediaFile, TranscodeAttemptId)
            if not EffectiveInputPath:
                self.HandleJobFailure(Job, "Failed to setup file preparation for subtitle fix", TranscodeAttemptId, ActiveJobId)
                return

            # Build subtitle fix command (pass effective input path)
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Building Command", 0.0, "Building subtitle fix command...")
            CommandResult = self.CommandBuilder.BuildSubtitleFixCommand(Job, MediaFile, InputPath=EffectiveInputPath, TranscodingSettings={'FFmpegPath': self.FFmpegPath, 'OutputDirectory': self.OutputDirectory})
            if not CommandResult:
                self.HandleJobFailure(Job, "Failed to build subtitle fix command", TranscodeAttemptId, ActiveJobId)
                return

            SubFixCommand = CommandResult['Command']
            OutputPath = CommandResult['OutputPath']

            # Create TemporaryFilePaths record with canonical paths
            CanonicalOutputPath = OutputPath
            if self.PathTranslation:
                CanonicalOutputPath = self.PathTranslation.ToCanonicalPath(OutputPath)
            TemporaryFilePathId = self.PrivateCreateTemporaryFilePathRecord(TranscodeAttemptId, Job.FilePath, Job.FilePath, CanonicalOutputPath)

            # Update attempt record (keep Success=None to indicate in-progress)
            self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                'FilePath': Job.FilePath,
                'AttemptDate': datetime.now(),
                'Quality': 0,
                'OldSizeBytes': Job.SizeBytes,
                'NewSizeBytes': 0,
                'Success': None,
                'FfpmpegCommand': SubFixCommand,
                'ProfileName': 'SubtitleFix',
                'VMAF': None
            })

            # Execute subtitle fix
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Fixing Subtitles", 0.0, "Converting subtitles to mov_text...")
            TranscodeResult = self.ExecuteTranscoding(Job, SubFixCommand, TranscodeAttemptId, MediaFile, ActiveJobId)
            if not TranscodeResult.get("Success", False):
                self.HandleJobFailure(Job, f"Subtitle fix failed: {TranscodeResult.get('ErrorMessage', 'Unknown error')}", TranscodeAttemptId, ActiveJobId)
                return

            # Handle result - skip quality testing (same as remux)
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Finalizing", 0.0, "Finalizing subtitle fix...")
            self.HandleRemuxResult(Job, TranscodeResult, TranscodeAttemptId, ActiveJobId, OutputPath)
            self.CleanupOrContinue(Job)

            LoggingService.LogInfo(f"Completed subtitle fix job processing for job ID: {Job.Id}", "ProcessTranscodeQueueService", "ProcessSubtitleFixJob")

        except Exception as e:
            LoggingService.LogException(f"Exception processing subtitle fix job {Job.Id}", e, "ProcessTranscodeQueueService", "ProcessSubtitleFixJob")
            self.HandleJobFailure(Job, f"Exception during subtitle fix: {str(e)}", TranscodeAttemptId, ActiveJobId)

    def HandleRemuxResult(self, Job: TranscodeQueueModel, TranscodeResult: Dict[str, Any], TranscodeAttemptId: int, ActiveJobId: int, OutputPath: str):
        """Handle remux results - skip quality testing, go directly to file replacement."""
        try:
            NewSizeBytes = TranscodeResult.get("NewSizeBytes", 0)
            OutputFilePath = TranscodeResult.get("OutputFilePath", OutputPath)
            OldSizeBytes = Job.SizeBytes

            SizeReductionBytes = OldSizeBytes - NewSizeBytes if NewSizeBytes > 0 and OldSizeBytes > 0 else 0
            SizeReductionPercent = (SizeReductionBytes / OldSizeBytes) * 100 if OldSizeBytes > 0 else 0.0

            # Update attempt as successful, no quality test needed
            self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                'Success': True,
                'CompletedDate': datetime.now(),
                'TranscodeDurationSeconds': TranscodeResult.get('Duration', 0.0),
                'NewSizeBytes': NewSizeBytes,
                'SizeReductionBytes': SizeReductionBytes,
                'SizeReductionPercent': SizeReductionPercent,
                'QualityTestRequired': False
            })

            # Update TranscodeFiles record
            self.UpdateTranscodeFileRecord(Job.FilePath, TranscodeAttemptId, True, OutputFilePath, NewSizeBytes)

            # Skip quality testing - go directly to file replacement
            # Use ShouldQualityTest with bypass since video is bit-identical
            QualityTestResult = self.ShouldQualityTest.ProcessTranscodedFile(TranscodeAttemptId, Job.FilePath, OutputFilePath)

            if QualityTestResult.get("Success"):
                LoggingService.LogInfo(f"Remux file replacement processed for TranscodeAttempt {TranscodeAttemptId}", "ProcessTranscodeQueueService", "HandleRemuxResult")
            else:
                LoggingService.LogWarning(f"Remux file replacement issue for TranscodeAttempt {TranscodeAttemptId}: {QualityTestResult.get('Message')}", "ProcessTranscodeQueueService", "HandleRemuxResult")

            # Delete job from queue
            self.DatabaseManager.DeleteTranscodeQueueItem(Job.Id)
            self.DatabaseManager.DeleteTranscodeProgress(TranscodeAttemptId)

            if ActiveJobId:
                self.DatabaseManager.CompleteActiveJob(ActiveJobId, Success=True)

            LoggingService.LogInfo(f"Remux job {Job.Id} completed successfully", "ProcessTranscodeQueueService", "HandleRemuxResult")

        except Exception as e:
            LoggingService.LogException("Exception handling remux result", e, "ProcessTranscodeQueueService", "HandleRemuxResult")

    def GetMediaFileData(self, Job: TranscodeQueueModel) -> Optional[MediaFileModel]:
        """Get MediaFile data by FilePath to retrieve source resolution."""
        try:
            return self.DatabaseManager.GetMediaFileByPath(Job.FilePath)
        except Exception as e:
            LoggingService.LogException("Exception getting media file data", e, "ProcessTranscodeQueueService", "GetMediaFileData")
            return None

    def GetTranscodeFileMode(self) -> str:
        """Get the transcode file mode from SystemSettings. Returns 'InPlace' (default) or 'CopyLocal'."""
        try:
            from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
            Repo = SystemSettingsRepository()
            Mode = Repo.GetSystemSetting('TranscodeFileMode')
            if Mode and Mode.strip().lower() == 'copylocal':
                return 'CopyLocal'
            return 'InPlace'
        except Exception as Ex:
            LoggingService.LogException("Exception reading TranscodeFileMode, defaulting to InPlace", Ex, "ProcessTranscodeQueueService", "GetTranscodeFileMode")
            return 'InPlace'

    def GetTranscodeOutputMode(self) -> str:
        """Get output placement mode. Returns 'InPlace' (default) or 'Staging'."""
        try:
            from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
            Repo = SystemSettingsRepository()
            Mode = Repo.GetSystemSetting('TranscodeOutputMode')
            if Mode and Mode.strip().lower() == 'staging':
                return 'Staging'
            return 'InPlace'
        except Exception as Ex:
            LoggingService.LogException("Exception reading TranscodeOutputMode, defaulting to InPlace", Ex, "ProcessTranscodeQueueService", "GetTranscodeOutputMode")
            return 'InPlace'

    def IsQualityTestEnabled(self) -> bool:
        """Resolve whether quality test is enabled. Per-worker override > global setting."""
        # Per-worker override takes priority
        if self.WorkerQualityTestEnabled is not None:
            return bool(self.WorkerQualityTestEnabled)
        # Fall back to global setting
        try:
            from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
            Repo = SystemSettingsRepository()
            Value = Repo.GetSystemSetting('QualityTestEnabled')
            if Value is not None:
                return Value.strip().lower() in ('1', 'true', 'yes', 'on')
            return False  # Default OFF
        except Exception as Ex:
            LoggingService.LogException("Exception reading QualityTestEnabled, defaulting to False", Ex, "ProcessTranscodeQueueService", "IsQualityTestEnabled")
            return False

    def SetupFilePreparation(self, Job: TranscodeQueueModel, MediaFile: MediaFileModel, TranscodeAttemptId: int) -> Optional[str]:
        """Setup transcoding directories and optionally copy source file.
        Returns the effective input path for FFmpeg, or None on failure.
        When TranscodeFileMode is 'InPlace', skips the copy and returns the network path (translated for this worker's platform).
        When 'CopyLocal', copies to C:\\MediaVortex\\Source\\ and returns the local path."""
        try:
            # Setup output directory (always needed, uses worker's configured staging dir if set)
            if not self.FileManager.SetupTranscodingDirectories(OutputDirectory=self.OutputDirectory):
                return None

            FileMode = self.GetTranscodeFileMode()

            if FileMode == 'CopyLocal':
                # Copy file to local source directory
                SourcePath = Job.FilePath
                if self.PathTranslation:
                    SourcePath = self.PathTranslation.ToLocalPath(SourcePath)
                DestinationPath = f"C:\\MediaVortex\\Source\\{MediaFile.FileName}"
                CopyResult = self.FileManager.CopyFile(SourcePath, DestinationPath)
                if not CopyResult:
                    return None
                LoggingService.LogInfo(f"CopyLocal mode: copied {SourcePath} to {DestinationPath}", "ProcessTranscodeQueueService", "SetupFilePreparation")
                return DestinationPath
            else:
                # InPlace mode: translate canonical DB path to local worker path
                LocalPath = Job.FilePath
                if self.PathTranslation:
                    LocalPath = self.PathTranslation.ToLocalPath(Job.FilePath)
                LoggingService.LogInfo(f"InPlace mode: using path: {LocalPath}", "ProcessTranscodeQueueService", "SetupFilePreparation")
                return LocalPath

        except Exception as e:
            LoggingService.LogException("Exception in file preparation", e, "ProcessTranscodeQueueService", "SetupFilePreparation")
            self.PrivateHandleFilePreparationFailure(TranscodeAttemptId, str(e))
            return None

    def GetTranscodingSettings(self, Job: TranscodeQueueModel, MediaFile: MediaFileModel) -> Optional[Dict[str, Any]]:
        """Get transcoding settings including profile, codec flags, and parameters."""
        try:
            # Get profile settings for target resolution
            ProfileSettings = self.DatabaseManager.GetProfileSettingsForTargetResolution(
                MediaFile.AssignedProfile, MediaFile.Resolution
            )
            if not ProfileSettings:
                return None

            # Apply ShowSettings override for target resolution if configured
            try:
                from Features.ShowSettings.ShowSettingsRepository import ShowSettingsRepository
                ShowSettingsRepo = ShowSettingsRepository()
                ShowTargetResolution = ShowSettingsRepo.GetTargetResolutionForFile(Job.FilePath)
                if ShowTargetResolution:
                    OriginalTarget = ProfileSettings.get('TargetResolution', '')
                    ProfileSettings['TargetResolution'] = ShowTargetResolution
                    LoggingService.LogInfo(
                        f"ShowSettings override: {Job.FileName} target resolution changed from '{OriginalTarget}' to '{ShowTargetResolution}'",
                        "ProcessTranscodeQueueService", "GetTranscodingSettings"
                    )
            except Exception as ShowSettingsEx:
                LoggingService.LogWarning(
                    f"Could not check ShowSettings for {Job.FileName}: {ShowSettingsEx}",
                    "ProcessTranscodeQueueService", "GetTranscodingSettings"
                )

            # Get codec flags
            CodecFlags = self.DatabaseManager.GetCodecFlagsByCodecName(ProfileSettings.get('Codec'))
            if not CodecFlags:
                return None

            # Get codec parameters
            CodecParameters = self.DatabaseManager.GetCodecParametersByCodecFlagsId(CodecFlags['Id'])
            if not CodecParameters:
                return None

            # Get StartTime from TranscodeAttempts if available
            StartTime = None
            try:
                # Query for StartTime from the most recent TranscodeAttempt for this file
                StartTimeResult = self.DatabaseManager.DatabaseService.ExecuteQuery(
                    "SELECT StartTime FROM TranscodeAttempts WHERE LOWER(FilePath) = LOWER(%s) ORDER BY AttemptDate DESC LIMIT 1",
                    (Job.FilePath,)
                )
                if StartTimeResult and StartTimeResult[0]['StartTime']:
                    StartTime = StartTimeResult[0]['StartTime']
                    LoggingService.LogInfo(f"Retrieved StartTime {StartTime} for file {Job.FilePath}",
                                         "ProcessTranscodeQueueService", "GetTranscodingSettings")
            except Exception as e:
                LoggingService.LogException("Error retrieving StartTime from TranscodeAttempts", e,
                                         "ProcessTranscodeQueueService", "GetTranscodingSettings")

            # Check for CRF override first (user-specified target CRF)
            # Try multiple path formats to match overrides set with different path formats
            normalizedPath = Job.FilePath.lower().replace('\\', '/')
            fileName = os.path.basename(Job.FilePath).lower()

            # Try full path first
            overrideKey = f"CRFOverride_{normalizedPath}"
            crfOverride = self.DatabaseManager.GetSystemSetting(overrideKey)

            # If not found, try with just filename (for overrides set from attempt records)
            if not crfOverride:
                overrideKey = f"CRFOverride_{fileName}"
                crfOverride = self.DatabaseManager.GetSystemSetting(overrideKey)

            # If still not found, try with drive letter and filename only (Z:filename.mp4 format)
            if not crfOverride and ':' in normalizedPath:
                driveAndFile = normalizedPath.split(':', 1)[1].lstrip('/').replace('/', '')
                if driveAndFile:
                    overrideKey = f"CRFOverride_{normalizedPath[0]}:{driveAndFile}"
                    crfOverride = self.DatabaseManager.GetSystemSetting(overrideKey)

            # Track if override was successfully applied
            overrideApplied = False

            # Debug logging to help troubleshoot override lookup
            if crfOverride:
                LoggingService.LogDebug(f"CRF override found: Key='{overrideKey}', FilePath='{Job.FilePath}', Value='{crfOverride}'",
                                      "ProcessTranscodeQueueService", "GetTranscodingSettings")
                try:
                    overrideCRF = int(crfOverride)
                    ProfileSettings['Quality'] = overrideCRF
                    overrideApplied = True
                    LoggingService.LogInfo(f"CRF override applied for {Job.FilePath}: Using CRF={overrideCRF} (user-specified, key={overrideKey})",
                                         "ProcessTranscodeQueueService", "GetTranscodingSettings")
                except (ValueError, TypeError):
                    LoggingService.LogWarning(f"Invalid CRF override value '{crfOverride}' for {Job.FilePath}, ignoring",
                                            "ProcessTranscodeQueueService", "GetTranscodingSettings")
            else:
                LoggingService.LogDebug(f"No CRF override found. Tried keys: CRFOverride_{normalizedPath}, CRFOverride_{fileName}, CRFOverride_{normalizedPath[0] if ':' in normalizedPath else ''}:{normalizedPath.split(':', 1)[1].lstrip('/').replace('/', '') if ':' in normalizedPath else ''}",
                                      "ProcessTranscodeQueueService", "GetTranscodingSettings")

            # If no override was successfully applied, check for previous attempts and adjust CRF if needed
            if not overrideApplied:
                from Services.AdaptiveQualityService import AdaptiveQualityService
                adaptiveService = AdaptiveQualityService(self.DatabaseManager)
                previousAttempt = adaptiveService.GetLatestTranscodeAttemptWithVMAF(Job.FilePath)

                if previousAttempt:
                    previousCRF = previousAttempt.get('Quality')
                    vmafScore = previousAttempt.get('VMAF')

                    if previousCRF and vmafScore is not None and vmafScore < 80:
                        # Calculate adjusted CRF
                        adjustedCRF = adaptiveService.CalculateAdjustedCRF(previousCRF, vmafScore)
                        currentCRF = ProfileSettings.get('Quality')

                        # Use the minimum (lowest) CRF value between adjusted and profile
                        # Lower CRF = higher quality, so we want whichever is lower
                        if adjustedCRF:
                            finalCRF = min(adjustedCRF, currentCRF)
                            ProfileSettings['Quality'] = finalCRF

                            # Log adjustment decision at Info level
                            logMessage = f"CRF selection for {Job.FilePath}: Previous CRF={previousCRF}, VMAF={vmafScore:.2f}, Calculated CRF={adjustedCRF}, Profile CRF={currentCRF}, Selected CRF={finalCRF} (minimum)"
                            LoggingService.LogInfo(logMessage, "ProcessTranscodeQueueService", "GetTranscodingSettings")

            # Log final CRF value that will be used (for debugging)
            finalCRF = ProfileSettings.get('Quality')
            if overrideApplied:
                LoggingService.LogInfo(f"Final CRF for {Job.FilePath}: {finalCRF} (from override)",
                                     "ProcessTranscodeQueueService", "GetTranscodingSettings")
            else:
                LoggingService.LogDebug(f"Final CRF for {Job.FilePath}: {finalCRF} (from profile/adaptive)",
                                     "ProcessTranscodeQueueService", "GetTranscodingSettings")

            return {
                'ProfileSettings': ProfileSettings,
                'CodecFlags': CodecFlags,
                'CodecParameters': CodecParameters,
                'SourceResolution': MediaFile.Resolution,
                'StartTime': StartTime,
                'FFmpegPath': self.FFmpegPath,
                'FFprobePath': self.FFprobePath,
                'OutputDirectory': self.OutputDirectory,
                'TranscodeOutputMode': self.GetTranscodeOutputMode(),
                'MaxCpuThreads': self.MaxCpuThreads
            }

        except Exception as e:
            LoggingService.LogException("Exception getting transcoding settings", e, "ProcessTranscodeQueueService", "GetTranscodingSettings")
            return None

    def BuildTranscodeCommand(self, Job: TranscodeQueueModel, MediaFile: MediaFileModel,
                              TranscodingSettings: Dict[str, Any]) -> Optional[Dict[str, str]]:
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
                QualityTestRequired=self.IsQualityTestEnabled(),
                QualityTestCompleted=False,
                StartTime=TranscodingSettings.get('StartTime') if TranscodingSettings else None
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

            TranscodeResult = self.VideoTranscoding.TranscodeVideo(TranscodeAttemptId, TranscodeCommand, ProgressCallback, TotalFramesFromMediaFile, ActiveJobId, self.DatabaseManager, MaxCpuThreads=self.MaxCpuThreads)

            # File size calculation is now handled in VideoTranscodingService.TranscodeVideo()
            return TranscodeResult

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
                # Use pre-calculated file size from ExecuteTranscoding (captured immediately after transcode)
                NewSizeBytes = TranscodeResult.get("NewSizeBytes", 0)
                OutputFilePath = TranscodeResult.get("OutputFilePath", "")

                # Calculate size reduction metrics
                SizeReductionBytes = 0
                SizeReductionPercent = 0.0
                OldSizeBytes = Job.SizeBytes

                if NewSizeBytes > 0 and OldSizeBytes > 0:
                    SizeReductionBytes = OldSizeBytes - NewSizeBytes
                    SizeReductionPercent = (SizeReductionBytes / OldSizeBytes) * 100
                    LoggingService.LogInfo(f"File sizes - Original: {OldSizeBytes} bytes, Transcoded: {NewSizeBytes} bytes, Reduction: {SizeReductionPercent:.1f}%",
                                         "ProcessTranscodeQueueService", "HandleTranscodingResult")
                else:
                    LoggingService.LogWarning(f"Invalid file size data - NewSizeBytes: {NewSizeBytes}, OldSizeBytes: {OldSizeBytes}",
                                            "ProcessTranscodeQueueService", "HandleTranscodingResult")

                # Update attempt record with success details
                self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                    'Success': True,
                    'CompletedDate': datetime.now(),
                    'TranscodeDurationSeconds': TranscodeResult.get('Duration', 0.0),
                    'NewSizeBytes': NewSizeBytes,
                    'SizeReductionBytes': SizeReductionBytes,
                    'SizeReductionPercent': SizeReductionPercent,
                    'QualityTestRequired': self.IsQualityTestEnabled()
                })

                # Update TranscodeFiles record for overall file status
                self.UpdateTranscodeFileRecord(Job.FilePath, TranscodeAttemptId, True, OutputFilePath, NewSizeBytes)

                # LocalOutputPath was already set during command building (single source of truth)

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
                    'ErrorMessage': ErrorMessage,
                    'CompletedDate': datetime.now()
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
                    VMAF=None,
                    CompletedDate=datetime.now()
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

    def GetOutputFilePathFromCommand(self, Job: TranscodeQueueModel, TranscodeAttemptId: int = None) -> Optional[str]:
        """Get output file path for a transcoding job. Uses TemporaryFilePaths table as source of truth if TranscodeAttemptId provided."""
        try:
            # If TranscodeAttemptId is provided, try to get the actual output path from TemporaryFilePaths table first
            if TranscodeAttemptId:
                try:
                    TemporaryFilePathRecord = self.DatabaseManager.GetTemporaryFilePath(TranscodeAttemptId)
                    if TemporaryFilePathRecord and TemporaryFilePathRecord.get('LocalOutputPath'):
                        OutputPath = TemporaryFilePathRecord['LocalOutputPath']
                        LoggingService.LogInfo(f"Retrieved output path from TemporaryFilePaths table: {OutputPath}", "ProcessTranscodeQueueService", "GetOutputFilePathFromCommand")
                        return OutputPath
                    else:
                        LoggingService.LogWarning(f"No LocalOutputPath found in TemporaryFilePaths for TranscodeAttempt {TranscodeAttemptId}, falling back to calculation",
                                                "ProcessTranscodeQueueService", "GetOutputFilePathFromCommand")
                except Exception as e:
                    LoggingService.LogWarning(f"Failed to retrieve output path from TemporaryFilePaths table for TranscodeAttempt {TranscodeAttemptId}: {str(e)}, falling back to calculation",
                                            "ProcessTranscodeQueueService", "GetOutputFilePathFromCommand")

            # Fallback to calculation method (legacy behavior)
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

            LoggingService.LogInfo(f"Calculated output path (fallback): {OutputFilePath}", "ProcessTranscodeQueueService", "GetOutputFilePathFromCommand")
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

    def PrivateCreateTemporaryFilePathRecord(self, TranscodeAttemptId: int, OriginalPath: str, LocalSourcePath: str, LocalOutputPath: str = None) -> Optional[int]:
        """Private method to create TemporaryFilePath record."""
        try:
            LoggingService.LogFunctionEntry("PrivateCreateTemporaryFilePathRecord", "ProcessTranscodeQueueService",
                                          TranscodeAttemptId, OriginalPath, LocalSourcePath, LocalOutputPath)

            TemporaryFilePathId = self.DatabaseManager.CreateTemporaryFilePath(TranscodeAttemptId, OriginalPath, LocalSourcePath, LocalOutputPath)

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

    def CancelActiveTranscodeJob(self) -> Dict[str, Any]:
        """Cancel the currently running transcode job — kill FFmpeg by PID, clean up DB, remove from queue."""
        try:
            LoggingService.LogFunctionEntry("CancelActiveTranscodeJob", "ProcessTranscodeQueueService")

            # Get active transcode job from TranscodeQueue (Status='Running')
            running_jobs = self.DatabaseManager.GetTranscodeQueueItemsByStatus("Running")
            if not running_jobs:
                return {"Success": False, "ErrorMessage": "No active transcode job found"}

            job = running_jobs[0]
            job_id = job.Id

            LoggingService.LogInfo(f"Cancelling active transcode job {job_id} for file: {job.FileName}",
                                 "ProcessTranscodeQueueService", "CancelActiveTranscodeJob")

            # 1. Kill FFmpeg process via ActiveJobs PID
            from Services.ProcessManagementService import ProcessManagementService
            process_mgmt = ProcessManagementService()
            active_jobs = self.DatabaseManager.GetActiveJobsByService("TranscodeService")
            for active_job in active_jobs:
                if active_job.get('QueueId') == job_id:
                    pid = active_job.get('ProcessId')
                    if pid:
                        try:
                            process_mgmt.KillProcess(pid, Graceful=True)
                            LoggingService.LogInfo(f"Killed FFmpeg process PID {pid} for job {job_id}",
                                                 "ProcessTranscodeQueueService", "CancelActiveTranscodeJob")
                        except Exception as e:
                            LoggingService.LogException(f"Error killing FFmpeg process PID {pid}", e,
                                                      "ProcessTranscodeQueueService", "CancelActiveTranscodeJob")
                    self.DatabaseManager.CompleteActiveJob(active_job['Id'], False, "Cancelled by user")
                    break

            # 2. Mark TranscodeAttempts as cancelled
            self.DatabaseManager.DatabaseService.ExecuteNonQuery(
                "UPDATE TranscodeAttempts SET Success = FALSE, ErrorMessage = 'Cancelled by user' "
                "WHERE LOWER(FilePath) = LOWER(%s) AND Success IS NULL", (job.FilePath,))

            # 3. Clean up TranscodeProgress records
            self.DatabaseManager.DatabaseService.ExecuteNonQuery(
                "DELETE FROM TranscodeProgress WHERE TranscodeAttemptId IN ("
                "SELECT Id FROM TranscodeAttempts WHERE LOWER(FilePath) = LOWER(%s) AND Success = FALSE)",
                (job.FilePath,))

            # 4. Delete the queue item (same as queue page cancel)
            self.DatabaseManager.DeleteTranscodeQueueItem(job_id)

            LoggingService.LogInfo(f"Successfully cancelled and removed transcode job {job_id} for file: {job.FileName}",
                                 "ProcessTranscodeQueueService", "CancelActiveTranscodeJob")

            return {
                "Success": True,
                "Message": f"Transcode job cancelled and removed. File: {job.FileName}",
                "JobId": job_id
            }

        except Exception as e:
            LoggingService.LogException("Error cancelling active transcode job", e,
                                      "ProcessTranscodeQueueService", "CancelActiveTranscodeJob")
            return {"Success": False, "ErrorMessage": str(e)}

    def PrivateGetTranscodeAttemptIdForJob(self, JobId: int) -> Optional[int]:
        """Private method to get TranscodeAttemptId for a given TranscodeQueue job."""
        try:
            # Query to find the most recent TranscodeAttempt for this file
            query = """
                SELECT ta.Id
                FROM TranscodeAttempts ta
                JOIN TranscodeQueue tq ON ta.FilePath = tq.FilePath
                WHERE tq.Id = %s
                ORDER BY ta.AttemptDate DESC
                LIMIT 1
            """

            result = self.DatabaseManager.DatabaseService.ExecuteQuery(query, (JobId,))
            if result:
                return result[0]['Id']
            return None

        except Exception as e:
            LoggingService.LogException(f"Error getting TranscodeAttemptId for job {JobId}", e,
                                      "ProcessTranscodeQueueService", "PrivateGetTranscodeAttemptIdForJob")
            return None

    def DetectAndCleanStuckJobsBeforeStart(self):
        """Detect and clean up stuck jobs before starting transcoding."""
        try:
            LoggingService.LogInfo("Checking for stuck jobs before starting transcoding",
                                 "ProcessTranscodeQueueService", "DetectAndCleanStuckJobsBeforeStart")

            from Services.StuckJobDetectionService import StuckJobDetectionService
            detection_service = StuckJobDetectionService(self.DatabaseManager)

            result = detection_service.DetectAndCleanStuckTranscodeJobs()

            if result.get("Success", False):
                stuck_found = result.get("StuckJobsFound", 0)
                jobs_cleaned = result.get("JobsCleaned", 0)
                if stuck_found > 0:
                    LoggingService.LogInfo(f"Pre-start stuck job detection: {stuck_found} stuck jobs found, {jobs_cleaned} jobs cleaned",
                                         "ProcessTranscodeQueueService", "DetectAndCleanStuckJobsBeforeStart")
                else:
                    LoggingService.LogInfo("Pre-start stuck job detection: No stuck jobs found",
                                         "ProcessTranscodeQueueService", "DetectAndCleanStuckJobsBeforeStart")
            else:
                LoggingService.LogWarning(f"Pre-start stuck job detection failed: {result.get('ErrorMessage', 'Unknown error')}",
                                        "ProcessTranscodeQueueService", "DetectAndCleanStuckJobsBeforeStart")

        except Exception as e:
            LoggingService.LogException("Error during pre-start stuck job detection", e,
                                      "ProcessTranscodeQueueService", "DetectAndCleanStuckJobsBeforeStart")

    def StartStuckJobMonitoring(self):
        """Start background monitoring for stuck jobs."""
        try:
            if self.StuckJobMonitoringActive:
                LoggingService.LogInfo("Stuck job monitoring already active",
                                     "ProcessTranscodeQueueService", "StartStuckJobMonitoring")
                return

            self.StuckJobMonitoringActive = True
            self.StuckJobMonitoringThread = threading.Thread(
                target=self.StuckJobMonitoringLoop,
                daemon=True,
                name="StuckJobMonitor"
            )
            self.StuckJobMonitoringThread.start()

            LoggingService.LogInfo("Started stuck job monitoring thread",
                                 "ProcessTranscodeQueueService", "StartStuckJobMonitoring")

        except Exception as e:
            LoggingService.LogException("Error starting stuck job monitoring", e,
                                      "ProcessTranscodeQueueService", "StartStuckJobMonitoring")

    def StopStuckJobMonitoring(self):
        """Stop background monitoring for stuck jobs."""
        try:
            if not self.StuckJobMonitoringActive:
                return

            self.StuckJobMonitoringActive = False

            if self.StuckJobMonitoringThread and self.StuckJobMonitoringThread.is_alive():
                self.StuckJobMonitoringThread.join(timeout=5)

            LoggingService.LogInfo("Stopped stuck job monitoring thread",
                                 "ProcessTranscodeQueueService", "StopStuckJobMonitoring")

        except Exception as e:
            LoggingService.LogException("Error stopping stuck job monitoring", e,
                                      "ProcessTranscodeQueueService", "StopStuckJobMonitoring")

    def StuckJobMonitoringLoop(self):
        """Background monitoring loop for stuck jobs - runs every 5 minutes."""
        try:
            LoggingService.LogInfo("Stuck job monitoring loop started",
                                 "ProcessTranscodeQueueService", "StuckJobMonitoringLoop")

            while self.StuckJobMonitoringActive and not self.StopRequested:
                try:
                    # Check for stuck jobs
                    from Services.StuckJobDetectionService import StuckJobDetectionService
                    detection_service = StuckJobDetectionService(self.DatabaseManager)

                    result = detection_service.DetectAndCleanStuckTranscodeJobs()

                    if result.get("Success", False):
                        stuck_found = result.get("StuckJobsFound", 0)
                        jobs_cleaned = result.get("JobsCleaned", 0)

                        if stuck_found > 0:
                            LoggingService.LogInfo(f"Periodic stuck job detection: {stuck_found} stuck jobs found, {jobs_cleaned} jobs cleaned",
                                                 "ProcessTranscodeQueueService", "StuckJobMonitoringLoop")
                        else:
                            # Log periodic check even when no stuck jobs found (for audit trail)
                            LoggingService.LogInfo("Periodic stuck job detection: No stuck jobs found",
                                                 "ProcessTranscodeQueueService", "StuckJobMonitoringLoop")
                    else:
                        LoggingService.LogWarning(f"Periodic stuck job detection failed: {result.get('ErrorMessage', 'Unknown error')}",
                                                "ProcessTranscodeQueueService", "StuckJobMonitoringLoop")

                except Exception as e:
                    LoggingService.LogException("Error in periodic stuck job detection", e,
                                              "ProcessTranscodeQueueService", "StuckJobMonitoringLoop")

                # Wait 5 minutes before next check
                for _ in range(300):  # 5 minutes = 300 seconds
                    if not self.StuckJobMonitoringActive or self.StopRequested:
                        break
                    time.sleep(1)

            LoggingService.LogInfo("Stuck job monitoring loop completed",
                                 "ProcessTranscodeQueueService", "StuckJobMonitoringLoop")

        except Exception as e:
            LoggingService.LogException("Error in stuck job monitoring loop", e,
                                      "ProcessTranscodeQueueService", "StuckJobMonitoringLoop")
        finally:
            self.StuckJobMonitoringActive = False
