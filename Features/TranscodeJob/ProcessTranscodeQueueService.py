from typing import Dict, Any, Optional, Callable
from datetime import datetime, timezone
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
from Features.QualityTesting.PostTranscodeDispositionService import PostTranscodeDispositionService
from Core.Logging.LoggingService import LoggingService


from Core.DateTimeHelpers import ToUtcIsoZ
class ProcessTranscodeQueueService:
    """Orchestrates the complete transcoding queue processing workflow using MVVM architecture."""

    def __init__(self, DatabaseManagerInstance: DatabaseManager = None,
                 FileManagerInstance: TranscodingFileManagerService = None,
                 CommandBuilderInstance: CommandBuilderService = None,
                 VideoTranscodingInstance: VideoTranscodingService = None,
                 QueueManagementInstance: QueueManagementService = None,
                 DispositionInstance: PostTranscodeDispositionService = None,
                 WorkerName: str = None,
                 WorkerConfig: dict = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.FileManager = FileManagerInstance or TranscodingFileManagerService()
        self.CommandBuilder = CommandBuilderInstance or CommandBuilderService()
        self.VideoTranscoding = VideoTranscodingInstance or VideoTranscodingService()
        self.QueueManagement = QueueManagementInstance or QueueManagementService(DatabaseManagerInstance=self.DatabaseManager)
        # Unified post-transcode disposition (replaces ShouldQualityTestService).
        # See Features/QualityTesting/post-transcode-disposition.feature.md.
        self.Disposition = DispositionInstance or PostTranscodeDispositionService(self.DatabaseManager)

        # Worker identity for distributed transcoding
        import socket
        self.WorkerName = WorkerName or socket.gethostname()
        self.WorkerConfig = WorkerConfig or {}

        # Read shared paths from WorkerContext (set at startup), fall back to WorkerConfig dict
        from Core.WorkerContext import WorkerContext
        Ctx = WorkerContext.Current()
        if Ctx:
            self.FFmpegPath = Ctx.FFmpegPath
            self.FFprobePath = Ctx.FFprobePath
            self.OutputDirectory = Ctx.StagingDirectory
            self.PathTranslation = Ctx.PathTranslation
        else:
            self.FFmpegPath = self.WorkerConfig.get('FFmpegPath') or self.WorkerConfig.get('ffmpegpath')
            self.FFprobePath = self.WorkerConfig.get('FFprobePath') or self.WorkerConfig.get('ffprobepath')
            self.OutputDirectory = self.WorkerConfig.get('StagingDirectory') or self.WorkerConfig.get('stagingdirectory')
            self.PathTranslation = None
            MountMap = self.WorkerConfig.get('ShareMappings') or {}
            if MountMap:
                from Core.Services.PathTranslationService import PathTranslationService
                self.PathTranslation = PathTranslationService(MountMap=MountMap)

        # Final fallback: if the worker registered with NULL FFmpeg/FFprobe paths
        # (e.g. shutil.which returned None on Windows) but the project bundles them,
        # discover them locally so command-build doesn't fail with FFmpegPath=None.
        # Without this, every job hits a ValueError in CommandBuilder and the
        # broad except returns None silently.
        if not self.FFmpegPath or not self.FFprobePath:
            try:
                from Services.FFmpegService import FFmpegService
                Discovery = FFmpegService()
                if not self.FFmpegPath and Discovery.FFmpegPath:
                    self.FFmpegPath = Discovery.FFmpegPath
                    LoggingService.LogWarning(
                        f"FFmpegPath was NULL on worker init; discovered {self.FFmpegPath}. "
                        f"Persist this in Workers.FFmpegPath for {self.WorkerName} to avoid the warning.",
                        "ProcessTranscodeQueueService", "__init__"
                    )
                if not self.FFprobePath and Discovery.FFprobePath:
                    self.FFprobePath = Discovery.FFprobePath
                    LoggingService.LogWarning(
                        f"FFprobePath was NULL on worker init; discovered {self.FFprobePath}. "
                        f"Persist this in Workers.FFprobePath for {self.WorkerName} to avoid the warning.",
                        "ProcessTranscodeQueueService", "__init__"
                    )
            except Exception as Ex:
                LoggingService.LogException(
                    "Failed to discover FFmpeg/FFprobe paths during worker init",
                    Ex, "ProcessTranscodeQueueService", "__init__"
                )

        # Per-worker CPU thread limit (NULL = use global SystemSettings.MaxCpuThreads)
        RawMaxCpu = self.WorkerConfig.get('MaxCpuThreads') or self.WorkerConfig.get('maxcputhreads')
        self.MaxCpuThreads = int(RawMaxCpu) if RawMaxCpu else None

        # Interlaced routing: FALSE = skip interlaced files, leave for capable workers
        RawAccepts = self.WorkerConfig.get('AcceptsInterlaced') or self.WorkerConfig.get('acceptsinterlaced')
        self.AcceptsInterlaced = RawAccepts if RawAccepts is not None else True

        # Per-worker QualityTestEnabled is no longer cached on this service
        # instance -- the disposition function reads ServiceStatus and the
        # gate config fresh per call. Per-worker capability still gates which
        # workers claim VMAF jobs (handled by ProcessQualityTestQueueService),
        # but it does not influence the per-attempt decision.

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
                "Timestamp": ToUtcIsoZ(datetime.now(timezone.utc))
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
                # Single control plane: this loop runs iff the capability poller
                # (WorkerService._CapabilityPollingLoop) deems Workers.TranscodeEnabled
                # is True for our worker. The legacy ServiceStatus.TranscodeService
                # gate that lived here was a fossil from the retired multi-process
                # architecture and is intentionally NOT read. See
                # Features/ServiceControl/capability-control-plane.feature.md.

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
        if Job.IsTestMode:
            self.ProcessTestVariantJob(Job)
            return

        ActiveJobId = None  # Initialize for error handling
        LocalStagingSourcePath = None
        LocalStagingOutputPath = None
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

            # Step a: Load MediaFile FIRST so we can pre-flight the source path before
            # any expensive work or attempt-history writes.
            MediaFile = self.GetMediaFileData(Job)
            if not MediaFile:
                # Cannot resolve MediaFile -- this is a queue-integrity issue, record an
                # attempt for diagnosis and let HandleJobFailure clean up the queue/active job.
                FallbackAttemptId = self.CreateTranscodeAttempt(Job, None, None, None)
                self.HandleJobFailure(Job, "Failed to get media file data", FallbackAttemptId, ActiveJobId)
                return

            # Pre-flight: source file existence check (TranscodeJob.feature.md [BUG] criterion).
            # When the source has been deleted between scan and transcode (or a prior
            # replacement step lost the file), do NOT create a TranscodeAttempt or run FFprobe.
            # Mark the MediaFile so future scans/queue passes can skip it via the
            # FFprobeFailureCount safety guard, drop the queue/active-job rows, and return.
            from Core.PathStorage import Resolve as PathResolve
            LocalSourcePath = PathResolve(MediaFile.StorageRootId, MediaFile.RelativePath, self.WorkerName, self.DatabaseManager.DatabaseService)
            if not os.path.exists(LocalSourcePath):
                ErrMsg = f"Source file missing on disk: {LocalSourcePath}"
                LoggingService.LogWarning(ErrMsg, "ProcessTranscodeQueueService", "ProcessJob")
                self._MarkMediaFileSourceMissing(MediaFile.Id, ErrMsg)
                try:
                    self.DatabaseManager.DeleteTranscodeQueueItem(Job.Id)
                except Exception as DelEx:
                    LoggingService.LogException("Failed to delete queue item for missing source", DelEx, "ProcessTranscodeQueueService", "ProcessJob")
                if ActiveJobId:
                    try:
                        self.DatabaseManager.DeleteActiveJob(ActiveJobId)
                    except Exception as DelEx:
                        LoggingService.LogException("Failed to delete active job for missing source", DelEx, "ProcessTranscodeQueueService", "ProcessJob")
                return

            # Source exists -- create the attempt record now that we have something to attempt.
            TranscodeAttemptId = self.CreateTranscodeAttempt(Job, None, None, None)
            if not TranscodeAttemptId:
                self.HandleJobFailure(Job, "Failed to create transcode attempt record", None, ActiveJobId)
                return

            # Phase 1: Initializing
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Initializing", 0.0, "Job started, getting ready")

            # Phase 2: Loading Media Data (already loaded -- progress phase only)
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Loading Media Data", 0.0, "Media metadata loaded")

            # Phase 3: Loading Settings
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Loading Settings", 0.0, "Loading transcoding profile settings...")

            # Step c: Get transcoding settings
            TranscodingSettings = self.GetTranscodingSettings(Job, MediaFile)
            if not TranscodingSettings:
                self.HandleJobFailure(Job, "Failed to get transcoding settings", TranscodeAttemptId, ActiveJobId)
                return

            # Local staging: override output directory to local disk
            IsLocalStaging = self.GetTranscodeFileMode() == 'LocalStaging'
            if IsLocalStaging and not self.OutputDirectory:
                LoggingService.LogWarning("LocalStaging mode requires StagingDirectory in Workers table. Falling back to InPlace.", "ProcessTranscodeQueueService", "ProcessJob")
                IsLocalStaging = False
            if IsLocalStaging:
                TranscodingSettings['OutputDirectory'] = self.GetLocalStagingDir()
                TranscodingSettings['TranscodeOutputMode'] = 'Staging'

            # Phase 4: Preparing Files (must happen before command building — FFprobe needs the staged file)
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Preparing Files", 0.0, "Preparing files for transcoding...")

            # Step b: Setup directories and optionally copy file
            EffectiveInputPath = self.SetupFilePreparation(Job, MediaFile, TranscodeAttemptId)
            if not EffectiveInputPath:
                self.HandleJobFailure(Job, "Failed to setup file preparation", TranscodeAttemptId, ActiveJobId)
                return
            if IsLocalStaging:
                LocalStagingSourcePath = EffectiveInputPath

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
            if IsLocalStaging:
                LocalStagingOutputPath = OutputPath

            # Create TemporaryFilePaths record with CANONICAL paths (so VMAF/FileReplacement on any machine can find files)
            # OriginalPath is already canonical (from Job.FilePath in DB)
            # For local staging, map output to NFS staging dir so downstream stages find the file after copy-back
            CanonicalSourcePath = Job.FilePath  # Already canonical
            CanonicalOutputPath = self.ComputeCanonicalOutputPath(OutputPath, IsLocalStaging)
            SrcId, SrcRel, OutId, OutRel = self._ResolveTfpPathParts(Job, OutputPath, IsLocalStaging)
            TemporaryFilePathId = self.PrivateCreateTemporaryFilePathRecord(
                TranscodeAttemptId, Job.FilePath, CanonicalSourcePath, CanonicalOutputPath,
                SourceStorageRootId=SrcId, SourceRelativePath=SrcRel,
                OutputStorageRootId=OutId, OutputRelativePath=OutRel)
            if not TemporaryFilePathId:
                LoggingService.LogWarning(f"Failed to create TemporaryFilePath record for TranscodeAttempt {TranscodeAttemptId}, but file preparation succeeded",
                                        "ProcessTranscodeQueueService", "ProcessJob")
                # Don't fail the entire operation if TemporaryFilePath creation fails

            # Update attempt record with complete information (keep Success=None to indicate in-progress)
            self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                'FilePath': Job.FilePath,
                'AttemptDate': datetime.now(timezone.utc),
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
                self.CleanupLocalStagingFiles(LocalStagingSourcePath, LocalStagingOutputPath)
                self.HandleJobFailure(Job, f"Transcoding failed: {TranscodeResult.get('ErrorMessage', 'Unknown error')}", TranscodeAttemptId, ActiveJobId)
                return

            # Local staging: copy output to NFS and clean up local files
            if IsLocalStaging:
                self.UpdateTranscodeProgress(TranscodeAttemptId, "Copying Back", 0.0, "Copying output to storage...")
                NfsCopyPath = self.CopyBackFromLocalStaging(LocalStagingOutputPath)
                if not NfsCopyPath:
                    self.CleanupLocalStagingFiles(LocalStagingSourcePath, LocalStagingOutputPath)
                    self.HandleJobFailure(Job, "Failed to copy output from local staging to NFS storage", TranscodeAttemptId, ActiveJobId)
                    return
                TranscodeResult['OutputFilePath'] = NfsCopyPath
                self.CleanupLocalStagingFiles(LocalStagingSourcePath, LocalStagingOutputPath)

            # Phase 7: Finalizing
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Finalizing", 0.0, "Processing results and cleanup...")

            # Step g: Handle transcoding result
            self.HandleTranscodingResult(Job, TranscodeResult, TranscodeAttemptId, ActiveJobId)

            # Step h: Cleanup or continue
            self.CleanupOrContinue(Job)

            LoggingService.LogInfo(f"Completed job processing for job ID: {Job.Id}", "ProcessTranscodeQueueService", "ProcessJob")

        except Exception as e:
            self.CleanupLocalStagingFiles(LocalStagingSourcePath, LocalStagingOutputPath)
            LoggingService.LogException(f"Exception processing job {Job.Id}", e, "ProcessTranscodeQueueService", "ProcessJob")
            self.HandleJobFailure(Job, f"Exception during processing: {str(e)}")

    def ProcessTestVariantJob(self, Job: TranscodeQueueModel):
        """Handle a queue row flagged for multi-variant testing. Loads the
        variant set from the DB, runs each variant sequentially as its own
        TranscodeAttempt with TestVariantSetId+TestVariantName populated. The
        disposition function (PostTranscodeDispositionService) short-circuits
        to NoReplace whenever TestVariantSetId is set -- source file is never
        touched. See Features/TranscodeJob/multi-variant-testing.feature.md."""
        ActiveJobId = None
        try:
            LoggingService.LogInfo(
                f"Starting test-variant job processing for queue ID: {Job.Id} (variant set {Job.TestVariantSetId})",
                "ProcessTranscodeQueueService", "ProcessTestVariantJob",
            )

            VariantSet = self.DatabaseManager.GetTestVariantSet(Job.TestVariantSetId)
            if not VariantSet or not VariantSet.get('Variants'):
                self.HandleJobFailure(Job, f"TestVariantSet {Job.TestVariantSetId} not found or empty", None, None)
                return
            Variants = VariantSet['Variants']
            LoggingService.LogInfo(
                f"Test set {VariantSet.get('Name')!r} has {len(Variants)} variants",
                "ProcessTranscodeQueueService", "ProcessTestVariantJob",
            )

            ActiveJobId = self.DatabaseManager.CreateActiveJob(
                ServiceName="TranscodeService",
                JobType="TestVariant",
                QueueId=Job.Id,
                ProcessId=os.getpid(),
                ThreadId=threading.get_ident(),
                WorkerName=self.WorkerName,
            )
            if ActiveJobId == 0:
                self.HandleJobFailure(Job, "Failed to create active job (test mode)", None, None)
                return

            self.DatabaseManager.UpdateTranscodeQueueStatus(Job.Id, "Running")

            MediaFile = self.GetMediaFileData(Job)
            if not MediaFile:
                self.HandleJobFailure(Job, "Failed to get media file data (test mode)", None, ActiveJobId)
                return

            from Core.PathStorage import Resolve as PathResolve
            LocalSourcePath = PathResolve(MediaFile.StorageRootId, MediaFile.RelativePath, self.WorkerName, self.DatabaseManager.DatabaseService)
            if not os.path.exists(LocalSourcePath):
                ErrMsg = f"Source file missing on disk: {LocalSourcePath}"
                LoggingService.LogWarning(ErrMsg, "ProcessTranscodeQueueService", "ProcessTestVariantJob")
                self._MarkMediaFileSourceMissing(MediaFile.Id, ErrMsg)
                self._CleanupTestQueueRow(Job, ActiveJobId)
                return

            SuccessCount = 0
            FailureCount = 0
            for V in Variants:
                Name = V.get('Name', '?')
                Label = V.get('Label', Name)
                LoggingService.LogInfo(
                    f"  Variant {Name}: {Label} (CRF={V.get('Crf')}, FG={V.get('FilmGrain')})",
                    "ProcessTranscodeQueueService", "ProcessTestVariantJob",
                )
                try:
                    AttemptId = self._ProcessSingleVariant(Job, MediaFile, V, ActiveJobId)
                    if AttemptId:
                        SuccessCount += 1
                    else:
                        FailureCount += 1
                except Exception as VEx:
                    FailureCount += 1
                    LoggingService.LogException(
                        f"Variant {Name} threw exception",
                        VEx, "ProcessTranscodeQueueService", "ProcessTestVariantJob",
                    )

            LoggingService.LogInfo(
                f"Test variant job {Job.Id} complete: {SuccessCount} succeeded, {FailureCount} failed ({len(Variants)} variants total)",
                "ProcessTranscodeQueueService", "ProcessTestVariantJob",
            )

            self._CleanupTestQueueRow(Job, ActiveJobId)

        except Exception as e:
            LoggingService.LogException(
                f"Exception processing test variant job {Job.Id}",
                e, "ProcessTranscodeQueueService", "ProcessTestVariantJob",
            )
            self.HandleJobFailure(Job, f"Exception during test variant processing: {str(e)}", None, ActiveJobId)

    def _ProcessSingleVariant(self, Job: TranscodeQueueModel, MediaFile, Variant: Dict[str, Any], ActiveJobId: int) -> Optional[int]:
        """Run one variant's full encode + queue-VMAF flow. Each variant gets
        its own TranscodeAttempt with TestVariantSetId+TestVariantName populated.
        Returns the attempt id on encoder success, None on failure. Failures in
        one variant do not block other variants in the same queue row."""
        VariantName = Variant.get('Name', '?')
        LocalStagingSourcePath = None
        LocalStagingOutputPath = None

        TranscodeAttemptId = self.CreateTranscodeAttempt(Job, None, None, None)
        if not TranscodeAttemptId:
            LoggingService.LogError(
                f"Failed to create attempt for variant {VariantName}",
                "ProcessTranscodeQueueService", "_ProcessSingleVariant",
            )
            return None

        # Tag the attempt with test-variant metadata BEFORE any encode work so the
        # disposition short-circuit (NoReplace) sees it on every read.
        self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
            'TestVariantSetId': Job.TestVariantSetId,
            'TestVariantName': VariantName,
        })

        self.UpdateTranscodeProgress(TranscodeAttemptId, "Initializing", 0.0, f"Variant {VariantName}: starting")
        self.UpdateTranscodeProgress(TranscodeAttemptId, "Loading Settings", 0.0, f"Variant {VariantName}: loading settings")

        TranscodingSettings = self.GetTranscodingSettings(Job, MediaFile)
        if not TranscodingSettings:
            self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                'Success': False, 'ErrorMessage': 'Failed to get transcoding settings',
            })
            return None

        # Variant overrides applied to ProfileSettings dict that BuildTranscodeCommand reads.
        # Scale override is deferred to v2 per the feature doc; for v1, only Crf and FilmGrain.
        Ps = TranscodingSettings.setdefault('ProfileSettings', {})
        if Variant.get('Crf') is not None:
            Ps['Quality'] = Variant['Crf']
        if Variant.get('FilmGrain') is not None:
            Ps['FilmGrain'] = Variant['FilmGrain']

        IsLocalStaging = self.GetTranscodeFileMode() == 'LocalStaging'
        if IsLocalStaging and not self.OutputDirectory:
            IsLocalStaging = False
        if IsLocalStaging:
            TranscodingSettings['OutputDirectory'] = self.GetLocalStagingDir()
            TranscodingSettings['TranscodeOutputMode'] = 'Staging'

        self.UpdateTranscodeProgress(TranscodeAttemptId, "Preparing Files", 0.0, f"Variant {VariantName}: preparing")
        EffectiveInputPath = self.SetupFilePreparation(Job, MediaFile, TranscodeAttemptId)
        if not EffectiveInputPath:
            self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                'Success': False, 'ErrorMessage': 'Failed to setup file preparation',
            })
            return None
        if IsLocalStaging:
            LocalStagingSourcePath = EffectiveInputPath

        self.UpdateTranscodeProgress(TranscodeAttemptId, "Building Command", 0.0, f"Variant {VariantName}: building command")
        TranscodingSettings['InputPath'] = EffectiveInputPath
        CommandResult = self.BuildTranscodeCommand(Job, MediaFile, TranscodingSettings)
        if not CommandResult:
            self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                'Success': False, 'ErrorMessage': 'Failed to build transcoding command',
            })
            return None

        OriginalOutputPath = CommandResult['OutputPath']
        VariantOutputPath = self._VariantizeOutputPath(OriginalOutputPath, VariantName)
        if VariantOutputPath != OriginalOutputPath:
            CommandResult['OutputPath'] = VariantOutputPath
            CommandResult['Command'] = CommandResult['Command'].replace(OriginalOutputPath, VariantOutputPath)
        TranscodeCommand = CommandResult['Command']
        OutputPath = CommandResult['OutputPath']
        if IsLocalStaging:
            LocalStagingOutputPath = OutputPath

        CanonicalSourcePath = Job.FilePath
        CanonicalOutputPath = self.ComputeCanonicalOutputPath(OutputPath, IsLocalStaging)
        SrcId, SrcRel, OutId, OutRel = self._ResolveTfpPathParts(Job, OutputPath, IsLocalStaging)
        self.PrivateCreateTemporaryFilePathRecord(
            TranscodeAttemptId, Job.FilePath, CanonicalSourcePath, CanonicalOutputPath,
            SourceStorageRootId=SrcId, SourceRelativePath=SrcRel,
            OutputStorageRootId=OutId, OutputRelativePath=OutRel)

        self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
            'FilePath': Job.FilePath,
            'AttemptDate': datetime.now(timezone.utc),
            'Quality': Ps.get('Quality', 0),
            'OldSizeBytes': Job.SizeBytes,
            'NewSizeBytes': 0,
            'Success': None,
            'SizeReductionBytes': 0,
            'SizeReductionPercent': 0.0,
            'ErrorMessage': None,
            'TranscodeDurationSeconds': 0.0,
            'FfpmpegCommand': TranscodeCommand,
            'AudioBitrateKbps': Ps.get('AudioBitrateKbps'),
            'VideoBitrateKbps': Ps.get('VideoBitrateKbps'),
            'ProfileName': MediaFile.AssignedProfile,
            'VMAF': None,
            'TestVariantSetId': Job.TestVariantSetId,
            'TestVariantName': VariantName,
        })

        self.UpdateTranscodeProgress(TranscodeAttemptId, "Starting Transcode", 0.0, f"Variant {VariantName}: encoding")
        TranscodeResult = self.ExecuteTranscoding(Job, TranscodeCommand, TranscodeAttemptId, MediaFile, ActiveJobId)
        if not TranscodeResult.get("Success", False):
            if IsLocalStaging:
                self.CleanupLocalStagingFiles(LocalStagingSourcePath, LocalStagingOutputPath)
            self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                'Success': False,
                'ErrorMessage': TranscodeResult.get('ErrorMessage', 'Encode failed'),
            })
            return None

        if IsLocalStaging:
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Copying Back", 0.0, f"Variant {VariantName}: copy-back")
            NfsCopyPath = self.CopyBackFromLocalStaging(LocalStagingOutputPath)
            if not NfsCopyPath:
                self.CleanupLocalStagingFiles(LocalStagingSourcePath, LocalStagingOutputPath)
                self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                    'Success': False, 'ErrorMessage': 'Copy-back from staging failed',
                })
                return None
            TranscodeResult['OutputFilePath'] = NfsCopyPath
            self.CleanupLocalStagingFiles(LocalStagingSourcePath, LocalStagingOutputPath)

        self.UpdateTranscodeProgress(TranscodeAttemptId, "Finalizing", 0.0, f"Variant {VariantName}: queuing VMAF")
        self.HandleTranscodingResult(Job, TranscodeResult, TranscodeAttemptId, ActiveJobId)
        return TranscodeAttemptId

    def _VariantizeOutputPath(self, OutputPath: str, VariantName: str) -> str:
        """Insert -test-<VariantName> before -mv. so test variants get distinct
        on-disk filenames and never overwrite each other or a production attempt."""
        if '-mv.' in OutputPath:
            return OutputPath.replace('-mv.', f'-test-{VariantName}-mv.')
        Dir = os.path.dirname(OutputPath)
        Base = os.path.basename(OutputPath)
        Stem, Ext = os.path.splitext(Base)
        return os.path.join(Dir, f"{Stem}-test-{VariantName}{Ext}")

    def _CleanupTestQueueRow(self, Job: TranscodeQueueModel, ActiveJobId: Optional[int]) -> None:
        """Mark the queue row complete and delete the ActiveJob row. Called once
        per queue row after all variants attempt (regardless of per-variant success)."""
        try:
            self.DatabaseManager.UpdateTranscodeQueueStatus(Job.Id, "Completed")
        except Exception as Ex:
            LoggingService.LogException("Failed to mark test queue row Completed", Ex, "ProcessTranscodeQueueService", "_CleanupTestQueueRow")
        try:
            self.DatabaseManager.DeleteTranscodeQueueItem(Job.Id)
        except Exception as Ex:
            LoggingService.LogException("Failed to delete test queue row", Ex, "ProcessTranscodeQueueService", "_CleanupTestQueueRow")
        if ActiveJobId:
            try:
                self.DatabaseManager.DeleteActiveJob(ActiveJobId)
            except Exception:
                pass

    def ProcessRemuxJob(self, Job: TranscodeQueueModel):
        """Process a remux job using the rename-before-encode pattern.

        Sequence:
          1. SetupFilePreparation -- handle InPlace / LocalStaging staging
          2. PrepareReplacement -- rename source to .orig, freeing the source
             path so FFmpeg can write directly to it (InPlace mode)
          3. BuildRemuxCommand with InputPath=.orig, OutputPath=freed source
          4. ExecuteTranscoding -- FFmpeg writes to the freed source path
          5. On success: HandleRemuxResult -> FileReplacement (which detects
             the pre-renamed .orig and skips the rename step, just verifies
             and settles)
          6. On any failure between steps 2-5: RollbackReplacement to
             restore the original from .orig

        See remux.flow.md and the 2026-05-09 KNOWN-ISSUES entry for the
        path-collision incident that motivated this design.
        """
        ActiveJobId = None
        TranscodeAttemptId = None
        LocalStagingSourcePath = None
        LocalStagingOutputPath = None
        OrigBackupPath = None  # set after PrepareReplacement
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

            # Local staging: override output directory to local disk
            IsLocalStaging = self.GetTranscodeFileMode() == 'LocalStaging'
            if IsLocalStaging and not self.OutputDirectory:
                LoggingService.LogWarning("LocalStaging mode requires StagingDirectory in Workers table. Falling back to InPlace.", "ProcessTranscodeQueueService", "ProcessRemuxJob")
                IsLocalStaging = False
            EffectiveOutputDir = self.GetLocalStagingDir() if IsLocalStaging else self.OutputDirectory

            # Setup file preparation first (copy or in-place based on setting)
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Preparing Files", 0.0, "Preparing source file...")
            EffectiveInputPath = self.SetupFilePreparation(Job, MediaFile, TranscodeAttemptId)
            if not EffectiveInputPath:
                self.HandleJobFailure(Job, "Failed to setup file preparation for remux", TranscodeAttemptId, ActiveJobId)
                return
            if IsLocalStaging:
                LocalStagingSourcePath = EffectiveInputPath

            # Rename source to .orig BEFORE FFmpeg runs. This frees the
            # original path so FFmpeg can write directly to the final
            # target name (no _remuxed suffix needed; no suffix-strip in
            # FileReplacement). On InPlace the .orig sits next to where
            # FFmpeg writes; on LocalStaging the .orig sits on NFS while
            # FFmpeg works in /staging/. Either way the original file is
            # untouched until Finalize confirms the new file is good.
            from Features.FileReplacement.FileReplacementBusinessService import FileReplacementBusinessService
            FrbService = FileReplacementBusinessService()
            PrepResult = FrbService.PrepareReplacement(Job.FilePath)
            if not PrepResult.get('Success'):
                self.HandleJobFailure(
                    Job,
                    f"PrepareReplacement failed: {PrepResult.get('ErrorMessage', 'unknown')}",
                    TranscodeAttemptId, ActiveJobId,
                )
                return
            OrigBackupPath = PrepResult['OrigBackupPath']

            # Compute the final target path. For InPlace: same dir as source,
            # basename + .mp4. EffectiveInputPath is the local-mounted path
            # SetupFilePreparation returned; for InPlace this equals the
            # original source path (which has just been renamed to .orig).
            # We strip the .orig suffix to recover the freed source path,
            # then change the extension to .mp4.
            import os as _os
            EffectiveInputForFfmpeg = OrigBackupPath  # FFmpeg reads from .orig
            FreedSourceLocalPath = OrigBackupPath[:-len('.orig')] if OrigBackupPath.endswith('.orig') else OrigBackupPath
            BaseName, _ = _os.path.splitext(_os.path.basename(FreedSourceLocalPath))
            TargetLocalPath = _os.path.join(_os.path.dirname(FreedSourceLocalPath), BaseName + '.mp4')

            # Build remux command. Caller-supplied OutputPath overrides the
            # builder's filename derivation (no _remuxed suffix needed).
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Building Command", 0.0, "Building remux command...")
            CommandResult = self.CommandBuilder.BuildRemuxCommand(
                Job, MediaFile,
                InputPath=EffectiveInputForFfmpeg,
                TranscodingSettings={
                    'FFmpegPath': self.FFmpegPath,
                    'OutputDirectory': EffectiveOutputDir,
                    'OutputPath': TargetLocalPath,
                },
            )
            if not CommandResult:
                # Roll back the .orig rename before bailing.
                FrbService.RollbackReplacement(Job.FilePath, OrigBackupPath, TargetLocalPath)
                self.HandleJobFailure(Job, "Failed to build remux command", TranscodeAttemptId, ActiveJobId)
                return

            RemuxCommand = CommandResult['Command']
            OutputPath = CommandResult['OutputPath']
            if IsLocalStaging:
                LocalStagingOutputPath = OutputPath

            # Create TemporaryFilePaths record with canonical paths
            CanonicalOutputPath = self.ComputeCanonicalOutputPath(OutputPath, IsLocalStaging)
            SrcId, SrcRel, OutId, OutRel = self._ResolveTfpPathParts(Job, OutputPath, IsLocalStaging)
            TemporaryFilePathId = self.PrivateCreateTemporaryFilePathRecord(
                TranscodeAttemptId, Job.FilePath, Job.FilePath, CanonicalOutputPath,
                SourceStorageRootId=SrcId, SourceRelativePath=SrcRel,
                OutputStorageRootId=OutId, OutputRelativePath=OutRel)

            # Update attempt record (keep Success=None to indicate in-progress)
            self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                'FilePath': Job.FilePath,
                'AttemptDate': datetime.now(timezone.utc),
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
                self.CleanupLocalStagingFiles(LocalStagingSourcePath, LocalStagingOutputPath)
                # Roll back the .orig rename so the source file is restored
                # to its original path. Without this, the operator would see
                # an .orig file and no original on a failed remux.
                if OrigBackupPath:
                    FrbService.RollbackReplacement(Job.FilePath, OrigBackupPath, TargetLocalPath)
                self.HandleJobFailure(Job, f"Remux failed: {TranscodeResult.get('ErrorMessage', 'Unknown error')}", TranscodeAttemptId, ActiveJobId)
                return

            # Local staging: copy output to NFS and clean up local files
            if IsLocalStaging:
                self.UpdateTranscodeProgress(TranscodeAttemptId, "Copying Back", 0.0, "Copying output to storage...")
                NfsCopyPath = self.CopyBackFromLocalStaging(LocalStagingOutputPath)
                if not NfsCopyPath:
                    self.CleanupLocalStagingFiles(LocalStagingSourcePath, LocalStagingOutputPath)
                    if OrigBackupPath:
                        FrbService.RollbackReplacement(Job.FilePath, OrigBackupPath, TargetLocalPath)
                    self.HandleJobFailure(Job, "Failed to copy remux output from local staging to NFS storage", TranscodeAttemptId, ActiveJobId)
                    return
                TranscodeResult['OutputFilePath'] = NfsCopyPath
                OutputPath = NfsCopyPath
                self.CleanupLocalStagingFiles(LocalStagingSourcePath, LocalStagingOutputPath)

            # Handle result - skip quality testing for remux
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Finalizing", 0.0, "Finalizing remux...")
            self.HandleRemuxResult(Job, TranscodeResult, TranscodeAttemptId, ActiveJobId, OutputPath)
            self.CleanupOrContinue(Job)

            LoggingService.LogInfo(f"Completed remux job processing for job ID: {Job.Id}", "ProcessTranscodeQueueService", "ProcessRemuxJob")

        except Exception as e:
            self.CleanupLocalStagingFiles(LocalStagingSourcePath, LocalStagingOutputPath)
            # If we got past PrepareReplacement before the exception, the
            # source is sitting at .orig and needs to be restored before we
            # mark the job failed -- otherwise the operator sees an .orig
            # and no original.
            if OrigBackupPath:
                try:
                    from Features.FileReplacement.FileReplacementBusinessService import FileReplacementBusinessService
                    FileReplacementBusinessService().RollbackReplacement(
                        Job.FilePath, OrigBackupPath,
                        TargetLocalPath if 'TargetLocalPath' in dir() else None,
                    )
                except Exception as RbEx:
                    LoggingService.LogException(
                        f"Rollback during exception cleanup also failed for job {Job.Id}",
                        RbEx, "ProcessTranscodeQueueService", "ProcessRemuxJob"
                    )
            LoggingService.LogException(f"Exception processing remux job {Job.Id}", e, "ProcessTranscodeQueueService", "ProcessRemuxJob")
            self.HandleJobFailure(Job, f"Exception during remux: {str(e)}", TranscodeAttemptId, ActiveJobId)

    def ProcessSubtitleFixJob(self, Job: TranscodeQueueModel):
        """Process a subtitle fix job: copy video+audio, convert ASS/SSA subtitle to mov_text, output MP4."""
        ActiveJobId = None
        TranscodeAttemptId = None
        LocalStagingSourcePath = None
        LocalStagingOutputPath = None
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

            # Local staging: override output directory to local disk
            IsLocalStaging = self.GetTranscodeFileMode() == 'LocalStaging'
            if IsLocalStaging and not self.OutputDirectory:
                LoggingService.LogWarning("LocalStaging mode requires StagingDirectory in Workers table. Falling back to InPlace.", "ProcessTranscodeQueueService", "ProcessSubtitleFixJob")
                IsLocalStaging = False
            EffectiveOutputDir = self.GetLocalStagingDir() if IsLocalStaging else self.OutputDirectory

            # Setup file preparation first (copy or in-place based on setting)
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Preparing Files", 0.0, "Preparing source file...")
            EffectiveInputPath = self.SetupFilePreparation(Job, MediaFile, TranscodeAttemptId)
            if not EffectiveInputPath:
                self.HandleJobFailure(Job, "Failed to setup file preparation for subtitle fix", TranscodeAttemptId, ActiveJobId)
                return
            if IsLocalStaging:
                LocalStagingSourcePath = EffectiveInputPath

            # Build subtitle fix command (pass effective input path)
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Building Command", 0.0, "Building subtitle fix command...")
            CommandResult = self.CommandBuilder.BuildSubtitleFixCommand(Job, MediaFile, InputPath=EffectiveInputPath, TranscodingSettings={'FFmpegPath': self.FFmpegPath, 'OutputDirectory': EffectiveOutputDir})
            if not CommandResult:
                self.HandleJobFailure(Job, "Failed to build subtitle fix command", TranscodeAttemptId, ActiveJobId)
                return

            SubFixCommand = CommandResult['Command']
            OutputPath = CommandResult['OutputPath']
            if IsLocalStaging:
                LocalStagingOutputPath = OutputPath

            # Create TemporaryFilePaths record with canonical paths
            CanonicalOutputPath = self.ComputeCanonicalOutputPath(OutputPath, IsLocalStaging)
            SrcId, SrcRel, OutId, OutRel = self._ResolveTfpPathParts(Job, OutputPath, IsLocalStaging)
            TemporaryFilePathId = self.PrivateCreateTemporaryFilePathRecord(
                TranscodeAttemptId, Job.FilePath, Job.FilePath, CanonicalOutputPath,
                SourceStorageRootId=SrcId, SourceRelativePath=SrcRel,
                OutputStorageRootId=OutId, OutputRelativePath=OutRel)

            # Update attempt record (keep Success=None to indicate in-progress)
            self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                'FilePath': Job.FilePath,
                'AttemptDate': datetime.now(timezone.utc),
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
                self.CleanupLocalStagingFiles(LocalStagingSourcePath, LocalStagingOutputPath)
                self.HandleJobFailure(Job, f"Subtitle fix failed: {TranscodeResult.get('ErrorMessage', 'Unknown error')}", TranscodeAttemptId, ActiveJobId)
                return

            # Local staging: copy output to NFS and clean up local files
            if IsLocalStaging:
                self.UpdateTranscodeProgress(TranscodeAttemptId, "Copying Back", 0.0, "Copying output to storage...")
                NfsCopyPath = self.CopyBackFromLocalStaging(LocalStagingOutputPath)
                if not NfsCopyPath:
                    self.CleanupLocalStagingFiles(LocalStagingSourcePath, LocalStagingOutputPath)
                    self.HandleJobFailure(Job, "Failed to copy subtitle fix output from local staging to NFS storage", TranscodeAttemptId, ActiveJobId)
                    return
                TranscodeResult['OutputFilePath'] = NfsCopyPath
                OutputPath = NfsCopyPath
                self.CleanupLocalStagingFiles(LocalStagingSourcePath, LocalStagingOutputPath)

            # Handle result - skip quality testing (same as remux)
            self.UpdateTranscodeProgress(TranscodeAttemptId, "Finalizing", 0.0, "Finalizing subtitle fix...")
            self.HandleRemuxResult(Job, TranscodeResult, TranscodeAttemptId, ActiveJobId, OutputPath)
            self.CleanupOrContinue(Job)

            LoggingService.LogInfo(f"Completed subtitle fix job processing for job ID: {Job.Id}", "ProcessTranscodeQueueService", "ProcessSubtitleFixJob")

        except Exception as e:
            self.CleanupLocalStagingFiles(LocalStagingSourcePath, LocalStagingOutputPath)
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
                'CompletedDate': datetime.now(timezone.utc),
                'TranscodeDurationSeconds': TranscodeResult.get('Duration', 0.0),
                'NewSizeBytes': NewSizeBytes,
                'SizeReductionBytes': SizeReductionBytes,
                'SizeReductionPercent': SizeReductionPercent,
                'QualityTestRequired': False
            })

            # Update TranscodeFiles record
            self.UpdateTranscodeFileRecord(Job.FilePath, TranscodeAttemptId, True, OutputFilePath, NewSizeBytes, MediaFileId=Job.MediaFileId)

            # Decide disposition + act. For remuxes the input row's
            # QualityTestRequired was set False above, so the disposition
            # function returns BypassReplace/QualityTestNotRequired and the
            # dispatcher hands off to FileReplacement.
            self.DispatchDisposition(TranscodeAttemptId, Job, OutputFilePath)

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

    def DispatchDisposition(self, TranscodeAttemptId: int, Job: TranscodeQueueModel,
                            OutputFilePath: str) -> None:
        """Decide the disposition for a finished transcode and act on it.

        Delegates the decision to PostTranscodeDispositionService (single source
        of truth). Acts on the result:

          Replace / BypassReplace -> hand off to FileReplacementBusinessService
          Pending (AwaitingVmaf)   -> enqueue to QualityTestQueue
          Discard / NoReplace / Requeue -> audit row already committed by the
            disposition function; staged file remains in StagingDirectory for
            operator inspection. (Action paths for these are deferred -- the
            disposition + audit trail give the operator visibility today.)

        Replaces the legacy `ShouldQualityTestService.ProcessTranscodedFile`
        call. See Features/QualityTesting/post-transcode-disposition.feature.md.
        """
        try:
            Result = self.Disposition.DecidePostTranscodeDisposition(TranscodeAttemptId)
            Disposition = Result.Disposition

            if Disposition in ('Replace', 'BypassReplace'):
                from Features.FileReplacement.FileReplacementBusinessService import FileReplacementBusinessService
                ReplacementService = FileReplacementBusinessService(
                    self.DatabaseManager,
                    PathTranslation=self.PathTranslation,
                    FFprobePath=self.FFprobePath,
                )
                ReplacementService.ProcessFileReplacement(TranscodeAttemptId)

            elif Disposition == 'Pending':
                # AwaitingVmaf -- enqueue VMAF; the QT worker will re-call
                # DecidePostTranscodeDisposition once the score lands.
                from Services.QualityTestQueueService import QualityTestQueueService
                QualityTestQueueService(self.DatabaseManager).AddToQualityTestQueue(TranscodeAttemptId)

            else:
                # Discard / NoReplace / Requeue: audit row is already committed.
                # The action layer for these dispositions is intentionally minimal
                # in this iteration -- staged file persists in StagingDirectory,
                # operator can query
                #   SELECT FilePath, Disposition, DispositionReason
                #   FROM TranscodeAttempts WHERE Disposition='<value>'
                # and decide manually. Future iterations can wire automatic
                # cleanup / requeue without changing the disposition contract.
                pass
        except Exception as Ex:
            LoggingService.LogException(
                f"DispatchDisposition failed for TranscodeAttempt {TranscodeAttemptId}",
                Ex, "ProcessTranscodeQueueService", "DispatchDisposition",
            )

    def _MarkMediaFileSourceMissing(self, MediaFileId: int, ErrorMessage: str) -> None:
        """Record that a worker could not find the source file on disk.

        Mirrors the FFprobe-failure-counter convention used during scanning so the
        existing 'skip files with FFprobeFailureCount >= 3' guard prevents the
        queue from re-targeting this MediaFile on subsequent passes. Does not raise --
        bookkeeping failure must not cascade into the caller's failure handling.
        """
        try:
            Query = """
                UPDATE MediaFiles
                SET LastFFprobeError = %s,
                    LastFFprobeAttemptDate = NOW(),
                    FFprobeFailureCount = COALESCE(FFprobeFailureCount, 0) + 1
                WHERE Id = %s
            """
            self.DatabaseManager.DatabaseService.ExecuteNonQuery(Query, (ErrorMessage, MediaFileId))
            LoggingService.LogInfo(
                f"Marked MediaFile {MediaFileId} as source-missing (FFprobeFailureCount incremented)",
                "ProcessTranscodeQueueService", "_MarkMediaFileSourceMissing"
            )
        except Exception as Ex:
            LoggingService.LogException(
                f"Failed to mark MediaFile {MediaFileId} source-missing", Ex,
                "ProcessTranscodeQueueService", "_MarkMediaFileSourceMissing"
            )

    def GetTranscodeFileMode(self) -> str:
        """Get the transcode file mode from SystemSettings. Returns 'InPlace' (default), 'CopyLocal', or 'LocalStaging'."""
        try:
            from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
            Repo = SystemSettingsRepository()
            Mode = Repo.GetSystemSetting('TranscodeFileMode')
            if Mode:
                ModeNorm = Mode.strip().lower()
                if ModeNorm == 'copylocal':
                    return 'CopyLocal'
                if ModeNorm == 'localstaging':
                    return 'LocalStaging'
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

            # Workers without a configured StagingDirectory cannot use LocalStaging.
            # Match the fallback decision made in ProcessJob/ProcessRemuxJob/ProcessSubtitleFixJob
            # so this method does not silently keep building staging paths.
            if FileMode == 'LocalStaging' and not self.OutputDirectory:
                FileMode = 'InPlace'

            from Core.PathStorage import Resolve as PathResolve
            SourcePath = PathResolve(Job.StorageRootId, Job.RelativePath, self.WorkerName, self.DatabaseManager.DatabaseService)

            if FileMode == 'LocalStaging':
                # Copy source to local staging disk (skip if already exists — crash recovery)
                LocalStagingDir = self.GetLocalStagingDir()
                os.makedirs(LocalStagingDir, exist_ok=True)
                DestinationPath = os.path.join(LocalStagingDir, MediaFile.FileName)
                if os.path.exists(DestinationPath):
                    LoggingService.LogInfo(f"LocalStaging mode: source already staged, skipping copy: {DestinationPath}", "ProcessTranscodeQueueService", "SetupFilePreparation")
                else:
                    CopyResult = self.FileManager.CopyFile(SourcePath, DestinationPath)
                    if not CopyResult:
                        return None
                    LoggingService.LogInfo(f"LocalStaging mode: copied {SourcePath} to {DestinationPath}", "ProcessTranscodeQueueService", "SetupFilePreparation")
                return DestinationPath
            elif FileMode == 'CopyLocal':
                # Copy file to local source directory
                DestinationPath = f"C:\\MediaVortex\\Source\\{MediaFile.FileName}"
                CopyResult = self.FileManager.CopyFile(SourcePath, DestinationPath)
                if not CopyResult:
                    return None
                LoggingService.LogInfo(f"CopyLocal mode: copied {SourcePath} to {DestinationPath}", "ProcessTranscodeQueueService", "SetupFilePreparation")
                return DestinationPath
            else:
                # InPlace mode: SourcePath is already the worker-local path from Resolve()
                LoggingService.LogInfo(f"InPlace mode: using path: {SourcePath}", "ProcessTranscodeQueueService", "SetupFilePreparation")
                return SourcePath

        except Exception as e:
            LoggingService.LogException("Exception in file preparation", e, "ProcessTranscodeQueueService", "SetupFilePreparation")
            self.PrivateHandleFilePreparationFailure(TranscodeAttemptId, str(e))
            return None

    def GetLocalStagingDir(self) -> str:
        """Get the local staging directory path for this worker."""
        BaseDir = os.environ.get('MEDIAVORTEX_LOCAL_STAGING_DIR', '/staging')
        return os.path.join(BaseDir, self.WorkerName)

    def CopyBackFromLocalStaging(self, LocalOutputPath: str) -> Optional[str]:
        """Copy transcoded output from local staging to NFS staging directory.
        Returns the NFS output path, or None on failure."""
        try:
            OutputFileName = os.path.basename(LocalOutputPath)
            NfsOutputDir = self.OutputDirectory  # Workers.StagingDirectory (NFS)
            if not NfsOutputDir:
                LoggingService.LogError("No StagingDirectory configured — cannot copy output from local staging to NFS", "ProcessTranscodeQueueService", "CopyBackFromLocalStaging")
                return None
            NfsOutputPath = os.path.join(NfsOutputDir, OutputFileName)
            CopyResult = self.FileManager.CopyFile(LocalOutputPath, NfsOutputPath)
            if not CopyResult:
                return None
            LoggingService.LogInfo(f"LocalStaging: copied output to NFS: {LocalOutputPath} -> {NfsOutputPath}", "ProcessTranscodeQueueService", "CopyBackFromLocalStaging")
            return NfsOutputPath
        except Exception as e:
            LoggingService.LogException("Exception copying output from local staging to NFS", e, "ProcessTranscodeQueueService", "CopyBackFromLocalStaging")
            return None

    def CleanupLocalStagingFiles(self, *Paths: str):
        """Delete local staging files. Logs but does not raise on failure."""
        for FilePath in Paths:
            if FilePath and os.path.exists(FilePath):
                try:
                    os.remove(FilePath)
                    LoggingService.LogInfo(f"LocalStaging: deleted {FilePath}", "ProcessTranscodeQueueService", "CleanupLocalStagingFiles")
                except Exception as e:
                    LoggingService.LogWarning(f"LocalStaging: failed to delete {FilePath}: {e}", "ProcessTranscodeQueueService", "CleanupLocalStagingFiles")

    def ComputeCanonicalOutputPath(self, OutputPath: str, IsLocalStaging: bool) -> str:
        """Compute the canonical output path for TemporaryFilePaths.
        For local staging, maps to NFS staging directory so downstream stages can find the file."""
        if IsLocalStaging:
            if not self.OutputDirectory:
                LoggingService.LogWarning("ComputeCanonicalOutputPath called with LocalStaging but no OutputDirectory set", "ProcessTranscodeQueueService", "ComputeCanonicalOutputPath")
                return OutputPath
            NfsOutputPath = os.path.join(self.OutputDirectory, os.path.basename(OutputPath))
            if self.PathTranslation:
                return self.PathTranslation.ToCanonicalPath(NfsOutputPath)
            return NfsOutputPath
        if self.PathTranslation:
            return self.PathTranslation.ToCanonicalPath(OutputPath)
        return OutputPath

    def GetTranscodingSettings(self, Job: TranscodeQueueModel, MediaFile: MediaFileModel) -> Optional[Dict[str, Any]]:
        """Get transcoding settings including profile, codec flags, and parameters."""
        try:
            # Get profile settings for target resolution
            ProfileSettings = self.DatabaseManager.GetProfileSettingsForTargetResolution(
                MediaFile.AssignedProfile, MediaFile.Resolution
            )
            if not ProfileSettings:
                return None

            # Apply ShowSettings override only when a per-show row exists for
            # this file. The `*` global default does NOT override an explicit
            # profile target -- profile.TranscodeDownTo is the default, and
            # ShowSettings overrides only when the operator has opted that
            # specific show in. See ShowSettings.feature.md criterion 1.
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
                    "SELECT StartTime FROM TranscodeAttempts WHERE MediaFileId = %s ORDER BY AttemptDate DESC LIMIT 1",
                    (Job.MediaFileId,)
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
                previousAttempt = adaptiveService.GetLatestTranscodeAttemptWithVMAF(Job.MediaFileId)

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
                AttemptDate=datetime.now(timezone.utc),
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
                QualityTestRequired=True,  # Disposition function decides if VMAF actually runs based on ServiceStatus + gate config
                QualityTestCompleted=False,
                StartTime=TranscodingSettings.get('StartTime') if TranscodingSettings else None,
                WorkerName=self.WorkerName
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
                    'CompletedDate': datetime.now(timezone.utc),
                    'TranscodeDurationSeconds': TranscodeResult.get('Duration', 0.0),
                    'NewSizeBytes': NewSizeBytes,
                    'SizeReductionBytes': SizeReductionBytes,
                    'SizeReductionPercent': SizeReductionPercent,
                    'QualityTestRequired': True  # Disposition function decides at post-flight
                })

                # Update TranscodeFiles record for overall file status
                self.UpdateTranscodeFileRecord(Job.FilePath, TranscodeAttemptId, True, OutputFilePath, NewSizeBytes, MediaFileId=Job.MediaFileId)

                # LocalOutputPath was already set during command building (single source of truth)

                # Decide disposition + act. The disposition function logs a
                # single rolled-up INFO line per decision and persists the
                # audit columns to TranscodeAttempts.
                self.DispatchDisposition(TranscodeAttemptId, Job, OutputFilePath)

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
                    'CompletedDate': datetime.now(timezone.utc)
                })

                # Update TranscodeFiles record for overall file status (failure)
                self.UpdateTranscodeFileRecord(Job.FilePath, TranscodeAttemptId, False, MediaFileId=Job.MediaFileId)
            else:
                # Create new attempt record for investigation (fallback case)
                Attempt = TranscodeAttemptModel(
                    FilePath=Job.FilePath,
                    AttemptDate=datetime.now(timezone.utc),
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
                    CompletedDate=datetime.now(timezone.utc),
                    WorkerName=self.WorkerName
                )
                AttemptId = self.DatabaseManager.SaveTranscodeAttempt(Attempt)

                # Update TranscodeFiles record for overall file status (failure)
                self.UpdateTranscodeFileRecord(Job.FilePath, AttemptId, False, MediaFileId=Job.MediaFileId)

            # Clean up partial output file and TemporaryFilePaths for failed attempt
            if TranscodeAttemptId:
                self._CleanupFailedAttemptFiles(TranscodeAttemptId)

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

    def _CleanupFailedAttemptFiles(self, TranscodeAttemptId: int):
        """Clean up partial output file and TemporaryFilePaths row for a failed transcode attempt."""
        try:
            LoggingService.LogInfo(f"Cleaning up files for failed TranscodeAttempt {TranscodeAttemptId}",
                                 "ProcessTranscodeQueueService", "_CleanupFailedAttemptFiles")

            TemporaryFilePathRecord = self.DatabaseManager.GetTemporaryFilePath(TranscodeAttemptId)

            if TemporaryFilePathRecord:
                # Delete partial output file from disk if it exists
                LocalOutputPath = TemporaryFilePathRecord.get('LocalOutputPath')
                if LocalOutputPath:
                    # Translate canonical path to local mount path if needed
                    ActualPath = LocalOutputPath
                    if self.PathTranslation:
                        ActualPath = self.PathTranslation.ToLocalPath(LocalOutputPath)

                    if os.path.exists(ActualPath):
                        try:
                            os.remove(ActualPath)
                            LoggingService.LogInfo(f"Deleted partial output file: {ActualPath}",
                                                 "ProcessTranscodeQueueService", "_CleanupFailedAttemptFiles")
                        except Exception as e:
                            LoggingService.LogWarning(f"Failed to delete partial output file {ActualPath}: {str(e)}",
                                                    "ProcessTranscodeQueueService", "_CleanupFailedAttemptFiles")
                    else:
                        LoggingService.LogInfo(f"Partial output file does not exist (already cleaned up): {ActualPath}",
                                             "ProcessTranscodeQueueService", "_CleanupFailedAttemptFiles")

                # Delete the TemporaryFilePaths row
                self.DatabaseManager.DeleteTemporaryFilePath(TranscodeAttemptId)
            else:
                LoggingService.LogInfo(f"No TemporaryFilePaths record found for TranscodeAttempt {TranscodeAttemptId} (nothing to clean up)",
                                     "ProcessTranscodeQueueService", "_CleanupFailedAttemptFiles")

        except Exception as e:
            LoggingService.LogException(f"Exception cleaning up failed attempt files for TranscodeAttempt {TranscodeAttemptId}",
                                       e, "ProcessTranscodeQueueService", "_CleanupFailedAttemptFiles")

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
                                 FinalFilePath: str = None, FinalSizeBytes: int = None,
                                 MediaFileId: int = None):
        """Update or create TranscodeFiles record for overall file transcoding status."""
        try:
            LoggingService.LogFunctionEntry("UpdateTranscodeFileRecord", "ProcessTranscodeQueueService",
                                          FilePath, TranscodeAttemptId, IsSuccess)

            # Resolve MediaFileId if not provided
            if not MediaFileId:
                MediaFileId = self.DatabaseManager.LookupMediaFileId(FilePath)

            # Get attempt details to extract quality and other info
            Attempt = self.DatabaseManager.GetTranscodeAttemptById(TranscodeAttemptId)
            if not Attempt:
                LoggingService.LogWarning(f"Could not retrieve attempt {TranscodeAttemptId} for TranscodeFiles update",
                                        "ProcessTranscodeQueueService", "UpdateTranscodeFileRecord")
                return

            # Check if TranscodeFile record already exists
            ExistingTranscodeFile = self.DatabaseManager.GetTranscodeFileByMediaFileId(MediaFileId) if MediaFileId else None

            if ExistingTranscodeFile:
                # Update existing record
                LoggingService.LogInfo(f"Updating existing TranscodeFile record for {FilePath}",
                                     "ProcessTranscodeQueueService", "UpdateTranscodeFileRecord")

                if IsSuccess:
                    # Success case - update with final details
                    self.DatabaseManager.UpdateTranscodeFileStatus(
                        MediaFileId=MediaFileId,
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
                        LastAttemptDate=datetime.now(timezone.utc),
                        SuccessDate=datetime.now(timezone.utc),
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
                        LastAttemptDate=datetime.now(timezone.utc),
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

                CurrentTime = datetime.now(timezone.utc)
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

    def _ResolveTfpPathParts(self, Job, OutputPath: str, IsLocalStaging: bool):
        """Compute (SrcId, SrcRel, OutId, OutRel) for TemporaryFilePaths writes.

        Output side is derived from Job.RelativePath (canonical, always '/'-separated)
        and the basename of the worker-local OutputPath. Parsing the worker-local
        OutputPath against StorageRoots was fragile (Linux os.path.basename on a
        Windows-shaped canonical string returned the whole string, polluting the
        stored relative path with 'T:/' fragments). The two layouts:
          - LocalStaging: MediaVortex/Staging/<WorkerName>/<output_basename>
          - InPlace:      <dirname(Job.RelativePath)>/<output_basename>
        OutputStorageRootId is always the source's StorageRootId -- the staging
        area lives inside the same physical StorageRoot as the source media."""
        import os as _os
        SrcId = getattr(Job, 'StorageRootId', None)
        SrcRel = getattr(Job, 'RelativePath', None) or None
        OutBase = _os.path.basename(OutputPath) if OutputPath else ''
        OutId = SrcId
        if IsLocalStaging:
            OutRel = f"MediaVortex/Staging/{self.WorkerName}/{OutBase}" if OutBase else None
        else:
            SrcDirRel = SrcRel.rsplit('/', 1)[0] if (SrcRel and '/' in SrcRel) else ''
            OutRel = f"{SrcDirRel}/{OutBase}" if SrcDirRel else OutBase
            OutRel = OutRel or None
        return SrcId, SrcRel, OutId, OutRel

    def PrivateCreateTemporaryFilePathRecord(self, TranscodeAttemptId: int, OriginalPath: str, LocalSourcePath: str, LocalOutputPath: str = None,
                                              SourceStorageRootId: int = None, SourceRelativePath: str = None,
                                              OutputStorageRootId: int = None, OutputRelativePath: str = None) -> Optional[int]:
        """Private method to create TemporaryFilePath record.

        Source side comes from the Job's (StorageRootId, RelativePath). Output side is parsed
        from the canonical output path via PathStorage.Parse so BuildVMAFCommand can resolve
        the encoded file on any worker without relying on legacy LocalOutputPath strings."""
        try:
            LoggingService.LogFunctionEntry("PrivateCreateTemporaryFilePathRecord", "ProcessTranscodeQueueService",
                                          TranscodeAttemptId, OriginalPath, LocalSourcePath, LocalOutputPath,
                                          SourceStorageRootId, SourceRelativePath,
                                          OutputStorageRootId, OutputRelativePath)

            TemporaryFilePathId = self.DatabaseManager.CreateTemporaryFilePath(
                TranscodeAttemptId, OriginalPath, LocalSourcePath, LocalOutputPath,
                SourceStorageRootId=SourceStorageRootId, SourceRelativePath=SourceRelativePath,
                OutputStorageRootId=OutputStorageRootId, OutputRelativePath=OutputRelativePath,
            )

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
                "WHERE MediaFileId = %s AND Success IS NULL", (job.MediaFileId,))

            # 3. Clean up TranscodeProgress records
            self.DatabaseManager.DatabaseService.ExecuteNonQuery(
                "DELETE FROM TranscodeProgress WHERE TranscodeAttemptId IN ("
                "SELECT Id FROM TranscodeAttempts WHERE MediaFileId = %s AND Success = FALSE)",
                (job.MediaFileId,))

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
                JOIN TranscodeQueue tq ON ta.MediaFileId = tq.MediaFileId
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
