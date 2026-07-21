from typing import Dict, Any, Optional, Callable
from datetime import datetime, timezone
import threading
import time
import os
import ntpath
import re
from Features.TranscodeQueue.Models.TranscodeQueueModel import TranscodeQueueModel
from Core.Models.MediaFileModel import MediaFileModel
from Core.Models.TranscodeAttemptModel import TranscodeAttemptModel
from Core.Models.TranscodeFileModel import TranscodeFileModel
from Repositories.DatabaseManager import DatabaseManager
from Features.TranscodeJob.Emit.CommandComposer import CommandComposer
from Features.TranscodeJob.Emit.ResolutionCalculator import ResolutionCalculator
from Features.TranscodeJob.Emit.OutputFilenameBuilder import OutputFilenameBuilder
from Features.TranscodeJob.Emit.VideoFilterBuilder import VideoFilterBuilder
from Features.TranscodeJob.Emit.MediaProbeAdapter import MediaProbeAdapter
from Features.TranscodeJob.Emit.Slots.VideoSlot import VideoSlot
from Features.TranscodeJob.Emit.Slots.AudioSlot import AudioSlot
from Features.TranscodeJob.Emit.Slots.SubtitleSlot import SubtitleSlot
from Features.TranscodeJob.Emit.Slots.ContainerSlot import ContainerSlot
from Features.TranscodeJob.Emit.Plan import PlanFactory
from Features.TranscodeJob.VideoTranscodingService import VideoTranscodingService
from Services.QueueManagementService import QueueManagementService
from Features.QualityTesting.Disposition.DispositionDispatcher import DispositionDispatcher
from Features.QualityTesting.Disposition.PostTranscodeDispositionDecider import PostTranscodeDispositionDecider
from Features.QualityTesting.Disposition.AttemptCleanupService import AttemptCleanupService
from Features.QualityTesting.Disposition.RetryBudgetService import RetryBudgetService
from Features.QualityTesting.Disposition.RetranscodeDecider import RetranscodeDecider
from Features.QualityTesting.PostTranscodeGateConfigRepository import PostTranscodeGateConfigRepository
from Features.TranscodeJob.Adjustments.AdjustmentRegistry import AdjustmentRegistry
from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Core.Path import Path, Worker, PathError
from Core.Path.LocalPath import LocalBasename, LocalDirname, LocalJoin, LocalSplitExt, LocalExists


from Core.DateTimeHelpers import ToUtcIsoZ
from Features.TranscodeQueue.TranscodeQueueRepository import TranscodeQueueRepository
from Core.Database.CodecFlagsRepository import CodecFlagsRepository
from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
from Features.ServiceControl.ActiveJobRepository import ActiveJobRepository
# directive: transcodejob-uses-path | # see path.S5
class ProcessTranscodeQueueService:
    """Orchestrates the complete transcoding queue processing workflow using MVVM architecture."""

    # directive: nvenc-rate-anchored-remediation
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None,
                 VideoTranscodingInstance: VideoTranscodingService = None,
                 QueueManagementInstance: QueueManagementService = None,
                 DispositionDispatcherInstance: DispositionDispatcher = None,
                 WorkerName: str = None,
                 WorkerConfig: dict = None, TranscodeQueueRepositoryInstance: Optional[TranscodeQueueRepository] = None, CodecFlagsRepositoryInstance: Optional[CodecFlagsRepository] = None, SystemSettingsRepositoryInstance: Optional[SystemSettingsRepository] = None, ActiveJobRepositoryInstance: Optional[ActiveJobRepository] = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.VideoTranscoding = VideoTranscodingInstance or VideoTranscodingService()
        self.QueueManagement = QueueManagementInstance or QueueManagementService(DatabaseManagerInstance=self.DatabaseManager)
        self.DispositionDispatcher = DispositionDispatcherInstance or self._BuildDefaultDispositionDispatcher()

        # Worker identity for distributed transcoding
        import socket
        self.WorkerName = WorkerName or socket.gethostname()
        self.WorkerConfig = WorkerConfig or {}

        from Core.WorkerContext import WorkerContext
        Ctx = WorkerContext.TryCurrent()
        if Ctx:
            self.FFmpegPath = Ctx.FFmpegPath
            self.FFprobePath = Ctx.FFprobePath
        else:
            self.FFmpegPath = self.WorkerConfig.get('FFmpegPath') or self.WorkerConfig.get('ffmpegpath')
            self.FFprobePath = self.WorkerConfig.get('FFprobePath') or self.WorkerConfig.get('ffprobepath')

        if not self.FFmpegPath or not self.FFprobePath:
            try:
                from Services.FFmpegService import FFmpegService
                from Core.Database.DatabaseService import DatabaseService
                Discovery = FFmpegService()
                Persisted = False
                if not self.FFmpegPath and Discovery.FFmpegPath:
                    self.FFmpegPath = Discovery.FFmpegPath
                    Persisted = True
                if not self.FFprobePath and Discovery.FFprobePath:
                    self.FFprobePath = Discovery.FFprobePath
                    Persisted = True
                # directive: transcode-flow-canonical -- self-heal Workers row so next boot reads clean; no warning cycle
                if Persisted:
                    DatabaseService().ExecuteNonQuery(
                        "UPDATE Workers SET FFmpegPath = %s, FFprobePath = %s WHERE WorkerName = %s",
                        (self.FFmpegPath, self.FFprobePath, self.WorkerName),
                    )
                    LoggingService.LogInfo(
                        f"Discovered + persisted FFmpeg/FFprobe paths for {self.WorkerName} (ffmpeg={self.FFmpegPath}, ffprobe={self.FFprobePath})",
                        "ProcessTranscodeQueueService", "__init__",
                    )
            except Exception as Ex:
                LoggingService.LogException(
                    "Failed to discover/persist FFmpeg/FFprobe paths during worker init",
                    Ex, "ProcessTranscodeQueueService", "__init__"
                )

        # Per-worker CPU thread limit (NULL = use global SystemSettings.MaxCpuThreads)
        RawMaxCpu = self.WorkerConfig.get('MaxCpuThreads') or self.WorkerConfig.get('maxcputhreads')
        self.MaxCpuThreads = int(RawMaxCpu) if RawMaxCpu else None

        # Interlaced routing: FALSE = skip interlaced files, leave for capable workers
        RawAccepts = self.WorkerConfig.get('AcceptsInterlaced') or self.WorkerConfig.get('acceptsinterlaced')
        self.AcceptsInterlaced = RawAccepts if RawAccepts is not None else True


        # Processing state
        self.IsProcessing = False
        self.MaxConcurrentJobs = 1
        self.ActiveJobs = []
        self.ProcessingThread = None
        self.StopRequested = False
        self._LastSetupError = None

        # Stuck job monitoring
        self.StuckJobMonitoringThread = None
        self.StuckJobMonitoringActive = False
        self.TranscodeQueueRepository = TranscodeQueueRepositoryInstance or TranscodeQueueRepository()
        self.CodecFlagsRepository = CodecFlagsRepositoryInstance or CodecFlagsRepository()
        self.SystemSettingsRepository = SystemSettingsRepositoryInstance or SystemSettingsRepository()
        self.ActiveJobRepository = ActiveJobRepositoryInstance or ActiveJobRepository()
        # directive: transcode-flow-canonical | # see transcode.ST5
        self.CommandComposer = self._BuildDefaultCommandComposer()

        # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S3
        from Features.AudioNormalization.Workers.PostEncodeAudioHandler import PostEncodeAudioHandler
        self.PostEncodeAudioHandler = PostEncodeAudioHandler(
            FFmpegPath=self.FFmpegPath,
            FFprobePath=self.FFprobePath,
        )

    # directive: transcode-flow-canonical | # see transcode.ST5
    def _BuildDefaultCommandComposer(self) -> CommandComposer:
        Probe = MediaProbeAdapter(FFprobePath=self.FFprobePath)
        return CommandComposer(
            VideoSlotInstance=VideoSlot(VideoFilterBuilder=VideoFilterBuilder()),
            AudioSlotInstance=AudioSlot(),
            SubtitleSlotInstance=SubtitleSlot(),
            ContainerSlotInstance=ContainerSlot(),
            ResolutionCalculatorInstance=ResolutionCalculator(),
            OutputFilenameBuilderInstance=OutputFilenameBuilder(),
            MediaProbeAdapterInstance=Probe,
            PlanFactoryInstance=PlanFactory(),
        )

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C9
    def _BuildDefaultDispositionDispatcher(self) -> DispositionDispatcher:
        """Compose the default DispositionDispatcher graph; Phase 3 lifts this to WorkerCompositionRoot."""
        GateRepo = PostTranscodeGateConfigRepository()
        Db = DatabaseService()
        Cleanup = AttemptCleanupService(Db)
        Retry = RetryBudgetService(AttemptRepository=self.DatabaseManager, GateConfigRepository=GateRepo)
        # directive: transcode-flow-canonical | # see transcode.ST7 -- C14 SmartConfidenceRepo composition
        from Features.QualityTesting.VmafConfidenceStatsRepository import VmafConfidenceStatsRepository
        SmartRepo = VmafConfidenceStatsRepository(Db)
        return DispositionDispatcher(
            Decider=PostTranscodeDispositionDecider(SmartConfidenceRepo=SmartRepo),
            GateConfigRepository=GateRepo,
            AttemptCleanupService=Cleanup,
            DatabaseService=Db,
            RetryBudgetService=Retry,
        )

    # directive: nvenc-rate-anchored-remediation | # see transcode.ST6
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
            if not isinstance(MaxConcurrentJobs, int) or MaxConcurrentJobs < 1:
                return {
                    "Success": False,
                    "ErrorMessage": "MaxConcurrentJobs must be a positive integer"
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

    # directive: nvenc-rate-anchored-remediation
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

    # directive: nvenc-rate-anchored-remediation
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

    # directive: nvenc-rate-anchored-remediation
    def ProcessQueueLoop(self):
        """Main processing loop that runs in background thread."""
        try:
            LoggingService.LogInfo("Starting transcoding queue processing loop", "ProcessTranscodeQueueService", "ProcessQueueLoop")

            while not self.StopRequested:

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

    # directive: nvenc-rate-anchored-remediation
    def GetNextJob(self) -> Optional[TranscodeQueueModel]:
        """Get and atomically claim the next pending job from the queue.
        Uses SELECT FOR UPDATE SKIP LOCKED for safe distributed operation.
        Respects AcceptsInterlaced worker setting to skip interlaced files."""
        try:
            return self.DatabaseManager.ClaimNextPendingJob(self.WorkerName, AcceptsInterlaced=self.AcceptsInterlaced)
        except Exception as e:
            LoggingService.LogException("Exception getting next job", e, "ProcessTranscodeQueueService", "GetNextJob")
            return None

    # directive: nvenc-rate-anchored-remediation
    def _ProcessSingleVariant(self, Job: TranscodeQueueModel, MediaFile, Variant: Dict[str, Any], ActiveJobId: int) -> Optional[int]:
        """Run one variant's full encode + queue-VMAF flow. Each variant gets
        its own TranscodeAttempt with TestVariantSetId+TestVariantName populated.
        Returns the attempt id on encoder success, None on failure. Failures in
        one variant do not block other variants in the same queue row."""
        VariantName = Variant.get('Name', '?')

        TranscodeAttemptId = self.CreateTranscodeAttempt(Job, None, None, None)
        if not TranscodeAttemptId:
            LoggingService.LogError(
                f"Failed to create attempt for variant {VariantName}",
                "ProcessTranscodeQueueService", "_ProcessSingleVariant",
            )
            return None

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

        Ps = TranscodingSettings.setdefault('ProfileSettings', {})
        if Variant.get('Crf') is not None:
            Ps['Quality'] = Variant['Crf']
        if Variant.get('FilmGrain') is not None:
            Ps['FilmGrain'] = Variant['FilmGrain']

        self.UpdateTranscodeProgress(TranscodeAttemptId, "Preparing Files", 0.0, f"Variant {VariantName}: preparing")
        self._LastSetupError = None
        EffectiveInputPath = self.SetupFilePreparation(Job, MediaFile, TranscodeAttemptId)
        if not EffectiveInputPath:
            Detail = self._LastSetupError or "unknown"
            self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                'Success': False, 'ErrorMessage': f'Failed to setup file preparation: {Detail}',
            })
            return None

        # directive: audio-dialog-boost-real | # see audio-normalization.C8
        from Features.AudioNormalization.Services import AudioPreEncodeFacade
        def _VariantProgress(Phase, Percent, Info):
            try:
                self.UpdateTranscodeProgress(TranscodeAttemptId, Phase, Percent, Info)
            except Exception:
                pass
        VariantPreAudio = AudioPreEncodeFacade.Prepare(
            FfmpegPath=self.FFmpegPath, InputPath=EffectiveInputPath,
            JobId=getattr(Job, 'Id', 'unknown'), ProgressReporter=_VariantProgress,
        )
        AudioPreEncodeFacade.EnrichContext(TranscodingSettings, VariantPreAudio)

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

        # directive: path-schema-migration | # see path.S8
        SrcId, SrcRel, OutId, OutRel = self._ResolveTfpPathParts(Job, OutputPath)
        self.PrivateCreateTemporaryFilePathRecord(
            TranscodeAttemptId, SrcId, SrcRel, OutId, OutRel)

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
            self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                'Success': False,
                'ErrorMessage': TranscodeResult.get('ErrorMessage', 'Encode failed'),
            })
            return None

        # directive: audio-dialog-boost-real | # see audio-normalization.C8
        try:
            from Features.AudioNormalization.Services.PostEncodeMeasurementService import PostEncodeMeasurementService
            PostEncodeMeasurementService(FFmpegPath=self.FFmpegPath, FFprobePath=self.FFprobePath).Probe(TranscodeAttemptId, OutputPath)
        except Exception as ProbeEx:
            LoggingService.LogException(f"Variant post-encode probe failed for AttemptId={TranscodeAttemptId} ({OutputPath})", ProbeEx, "ProcessTranscodeQueueService", "_ProcessSingleVariant")
        self.UpdateTranscodeProgress(TranscodeAttemptId, "Finalizing", 0.0, f"Variant {VariantName}: queuing VMAF")
        self.HandleTranscodingResult(Job, TranscodeResult, TranscodeAttemptId, ActiveJobId)
        AudioPreEncodeFacade.PersistMeta(TranscodeAttemptId, VariantPreAudio)
        AudioPreEncodeFacade.Cleanup(self.FFmpegPath, VariantPreAudio)
        return TranscodeAttemptId

    # directive: nvenc-rate-anchored-remediation
    def _VerifyInProgressFile(self, LocalInProgressPath: str) -> bool:
        """FFprobe a freshly-written `.inprogress` file to confirm it is a valid
        media file. Owns worker-lifecycle.feature.md criterion 7."""
        try:
            if not LocalExists(LocalInProgressPath):
                LoggingService.LogError(
                    f"FFprobe verify failed: .inprogress file not found at {LocalInProgressPath}",
                    "ProcessTranscodeQueueService", "_VerifyInProgressFile"
                )
                return False
            from Services.FFmpegAnalysisService import FFmpegAnalysisService
            Analysis = FFmpegAnalysisService(FFprobePath=self.FFprobePath).AnalyzeMediaFile(LocalInProgressPath)
            if not Analysis:
                LoggingService.LogError(
                    f"FFprobe verify failed for {LocalInProgressPath}: no analysis result",
                    "ProcessTranscodeQueueService", "_VerifyInProgressFile"
                )
                return False
            return True
        except Exception as e:
            LoggingService.LogException(
                f"Exception verifying .inprogress file {LocalInProgressPath}",
                e, "ProcessTranscodeQueueService", "_VerifyInProgressFile"
            )
            return False

    # directive: nvenc-rate-anchored-remediation
    def _DeleteInProgressFile(self, LocalInProgressPath: str) -> None:
        """Best-effort delete of a `.inprogress` artifact after FFmpeg or
        FFprobe-verify failure. Owns worker-lifecycle.feature.md criterion 9.
        Defensive: refuses to delete any path that does not end in `.inprogress`
        so a bad caller can never destroy a source or finalized output."""
        if not LocalInProgressPath:
            return
        if not LocalInProgressPath.endswith('.inprogress'):
            LoggingService.LogWarning(
                f"_DeleteInProgressFile refused to delete non-.inprogress path: {LocalInProgressPath}",
                "ProcessTranscodeQueueService", "_DeleteInProgressFile"
            )
            return
        try:
            if LocalExists(LocalInProgressPath):
                os.remove(LocalInProgressPath)
                LoggingService.LogInfo(
                    f"Deleted .inprogress artifact: {LocalInProgressPath}",
                    "ProcessTranscodeQueueService", "_DeleteInProgressFile"
                )
        except Exception as e:
            LoggingService.LogWarning(
                f"Could not delete .inprogress artifact at {LocalInProgressPath}: {str(e)}",
                "ProcessTranscodeQueueService", "_DeleteInProgressFile"
            )

    # directive: nvenc-rate-anchored-remediation
    def _VariantizeOutputPath(self, OutputPath: str, VariantName: str) -> str:
        """Insert -test-<VariantName> before -mv. so test variants get distinct
        on-disk filenames and never overwrite each other or a production attempt."""
        if '-mv.' in OutputPath:
            return OutputPath.replace('-mv.', f'-test-{VariantName}-mv.')
        Dir = LocalDirname(OutputPath)
        Base = LocalBasename(OutputPath)
        Stem, Ext = LocalSplitExt(Base)
        return LocalJoin(Dir, f"{Stem}-test-{VariantName}{Ext}")

    # directive: nvenc-rate-anchored-remediation
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
                self.ActiveJobRepository.DeleteActiveJob(ActiveJobId)
            except Exception:
                pass

    # directive: transcode-flow-canonical | # see transcode.ST8 -- StreamCopy checksum verify
    def HandleRemuxResult(self, Job: TranscodeQueueModel, TranscodeResult: Dict[str, Any], TranscodeAttemptId: int, ActiveJobId: int, OutputPath: str):
        """StreamCopy path: checksum-verify then dispatch disposition. Vmaf=100.0 sentinel on match; Success=False on mismatch."""
        try:
            NewSizeBytes = TranscodeResult.get("NewSizeBytes", 0)
            RawOutputFilePath = TranscodeResult.get("OutputFilePath", OutputPath)
            OutputFilePath = RawOutputFilePath[:-len('.inprogress')] if RawOutputFilePath.endswith('.inprogress') else RawOutputFilePath
            OldSizeBytes = Job.SizeBytes

            SizeReductionBytes = OldSizeBytes - NewSizeBytes if NewSizeBytes > 0 and OldSizeBytes > 0 else 0
            SizeReductionPercent = (SizeReductionBytes / OldSizeBytes) * 100 if OldSizeBytes > 0 else 0.0

            ChecksumOutcome = self._VerifyStreamCopyChecksum(Job, RawOutputFilePath, TranscodeAttemptId)
            AttemptUpdate = {
                'CompletedDate': datetime.now(timezone.utc),
                'TranscodeDurationSeconds': TranscodeResult.get('Duration', 0.0),
                'NewSizeBytes': NewSizeBytes,
                'SizeReductionBytes': SizeReductionBytes,
                'SizeReductionPercent': SizeReductionPercent,
                'QualityTestRequired': False,
                'Success': ChecksumOutcome['Success'],
                'VMAF': ChecksumOutcome['Vmaf'],
            }
            if not ChecksumOutcome['Success']:
                AttemptUpdate['ErrorMessage'] = ChecksumOutcome['ErrorMessage']
            self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, AttemptUpdate)

            # Update TranscodeFiles record
            self.UpdateTranscodeFileRecord(Job.FilePath, TranscodeAttemptId, True, OutputFilePath, NewSizeBytes, MediaFileId=Job.MediaFileId)

            self.DispatchDisposition(TranscodeAttemptId, Job, OutputFilePath)

            # Delete job from queue
            self.DatabaseManager.DeleteTranscodeQueueItem(Job.Id)
            self.DatabaseManager.DeleteTranscodeProgress(TranscodeAttemptId)

            if ActiveJobId:
                self.ActiveJobRepository.CompleteActiveJob(ActiveJobId, Success=True)

            Mode = (Job.ProcessingMode or 'Remux').lower()
            LoggingService.LogInfo(f"{Mode} job {Job.Id} completed successfully", "ProcessTranscodeQueueService", "HandleRemuxResult")

        except Exception as e:
            LoggingService.LogException("Exception handling job result", e, "ProcessTranscodeQueueService", "HandleRemuxResult")

    # directive: transcode-flow-canonical | # see transcode.ST8 -- StreamCopy verify emits checksum
    def _VerifyStreamCopyChecksum(self, Job: TranscodeQueueModel, StagedOutputPath: str, TranscodeAttemptId: int) -> Dict[str, Any]:
        """Return {Success, Vmaf, ErrorMessage}. Vmaf=100.0 on video-stream MD5 match; Success=False on mismatch or probe error."""
        import subprocess
        try:
            SourceLocalPath = Path(Job.StorageRootId, Job.RelativePath).Resolve(Worker.Current(Db=self.DatabaseManager.DatabaseService))
            if not SourceLocalPath or not LocalExists(SourceLocalPath):
                return {'Success': False, 'Vmaf': None, 'ErrorMessage': f'StreamCopy verify: source unresolved or missing at {SourceLocalPath!r}'}
            if not LocalExists(StagedOutputPath):
                return {'Success': False, 'Vmaf': None, 'ErrorMessage': f'StreamCopy verify: staged output missing at {StagedOutputPath!r}'}
            SourceMd5 = self._ComputeVideoStreamMd5(SourceLocalPath)
            OutputMd5 = self._ComputeVideoStreamMd5(StagedOutputPath)
            if SourceMd5 is None or OutputMd5 is None:
                return {'Success': False, 'Vmaf': None, 'ErrorMessage': f'StreamCopy verify: MD5 probe failed (source={SourceMd5!r} output={OutputMd5!r})'}
            if SourceMd5 != OutputMd5:
                LoggingService.LogError(
                    f"StreamCopy checksum mismatch on TranscodeAttempt {TranscodeAttemptId}: source MD5={SourceMd5} output MD5={OutputMd5}",
                    "ProcessTranscodeQueueService", "_VerifyStreamCopyChecksum",
                )
                return {'Success': False, 'Vmaf': None, 'ErrorMessage': f'StreamCopy checksum mismatch: source={SourceMd5} output={OutputMd5}'}
            LoggingService.LogInfo(
                f"StreamCopy checksum verified on TranscodeAttempt {TranscodeAttemptId}: MD5={SourceMd5}",
                "ProcessTranscodeQueueService", "_VerifyStreamCopyChecksum",
            )
            return {'Success': True, 'Vmaf': 100.0, 'ErrorMessage': None}
        except Exception as Ex:
            LoggingService.LogException(
                f"StreamCopy checksum verify failed on TranscodeAttempt {TranscodeAttemptId}",
                Ex, "ProcessTranscodeQueueService", "_VerifyStreamCopyChecksum",
            )
            return {'Success': False, 'Vmaf': None, 'ErrorMessage': f'StreamCopy verify raised: {str(Ex)[:200]}'}

    # directive: transcode-flow-canonical | # see transcode.ST8 -- ffprobe per-packet data_hash chain (muxer-independent, BUG-0084 fix)
    def _ComputeVideoStreamMd5(self, LocalPath: str) -> Optional[str]:
        """Return hex MD5 of concatenated per-packet data_hash for first video stream."""
        import subprocess
        import hashlib
        try:
            Command = [self.FFprobePath, '-hide_banner', '-loglevel', 'error',
                       '-show_data_hash', 'md5',
                       '-show_packets',
                       '-select_streams', 'v:0',
                       '-show_entries', 'packet=data_hash',
                       '-of', 'default=nokey=1:noprint_wrappers=1',
                       LocalPath]
            Result = subprocess.run(Command, capture_output=True, text=True, timeout=600)
            if Result.returncode != 0:
                LoggingService.LogError(
                    f"ffprobe packet-hash probe returned {Result.returncode} for {LocalPath!r}: {Result.stderr.strip()[:200]}",
                    "ProcessTranscodeQueueService", "_ComputeVideoStreamMd5",
                )
                return None
            Digest = hashlib.md5()
            PacketCount = 0
            for Line in Result.stdout.splitlines():
                Line = Line.strip()
                if not Line:
                    continue
                Digest.update(Line.encode('ascii'))
                PacketCount += 1
            if PacketCount == 0:
                LoggingService.LogError(
                    f"ffprobe packet-hash returned zero packets for {LocalPath!r}",
                    "ProcessTranscodeQueueService", "_ComputeVideoStreamMd5",
                )
                return None
            return Digest.hexdigest()
        except Exception as Ex:
            LoggingService.LogException(
                f"MD5 probe raised for {LocalPath!r}",
                Ex, "ProcessTranscodeQueueService", "_ComputeVideoStreamMd5",
            )
            return None

    # directive: nvenc-rate-anchored-remediation
    def GetMediaFileData(self, Job: TranscodeQueueModel) -> Optional[MediaFileModel]:
        """Get MediaFile data by FilePath to retrieve source resolution."""
        try:
            return self.DatabaseManager.GetMediaFileByPath(Job.FilePath)
        except Exception as e:
            LoggingService.LogException("Exception getting media file data", e, "ProcessTranscodeQueueService", "GetMediaFileData")
            return None

    # directive: e2e-bug-fixes | # see e2e-bug-fixes.C22
    def _ResolveMediaFileOrRaise(self, Job: TranscodeQueueModel, Caller: str) -> MediaFileModel:
        MediaFileId = getattr(Job, 'MediaFileId', None)
        if not MediaFileId:
            raise ValueError(f"{Caller}: Job {getattr(Job, 'Id', None)} missing MediaFileId; cannot resolve profile.")
        Mf = self.DatabaseManager.GetMediaFileById(MediaFileId)
        if Mf is None:
            raise ValueError(f"{Caller}: MediaFileId {MediaFileId} not found in DB for Job {getattr(Job, 'Id', None)}.")
        return Mf

    # directive: e2e-bug-fixes | # see e2e-bug-fixes.C22
    def _ResolveProfileNameOrRaise(self, MediaFile: MediaFileModel, Caller: str) -> str:
        Name = getattr(MediaFile, 'AssignedProfile', None)
        if not Name:
            raise ValueError(f"{Caller}: MediaFile {getattr(MediaFile, 'Id', None)} has no AssignedProfile; refuse to label attempt with ProcessingMode fallback.")
        return Name

    # directive: e2e-bug-fixes | # see e2e-bug-fixes.C30 -- exceptions propagate; caller (HandleTranscodingResult) writes Success=False + ErrorMessage in its outer catch. No internal swallow.
    def DispatchDisposition(self, TranscodeAttemptId: int, Job: TranscodeQueueModel,
                            OutputFilePath: str, EncodeSucceeded: bool = True) -> None:
        """Replace -> FileReplacementBusinessService; Pending -> QualityTestQueue; other terminals audited by dispatcher. Raises on any pipeline failure so HandleTranscodingResult flips Success=False."""
        Result = self.DispositionDispatcher.Dispatch(TranscodeAttemptId, EncodeSucceeded=EncodeSucceeded)
        Disposition = Result.Disposition

        if Disposition == 'Replace':
            from Features.FileReplacement.FileReplacementBusinessService import FileReplacementBusinessService
            ReplacementService = FileReplacementBusinessService(
                self.DatabaseManager,
                FFprobePath=self.FFprobePath,
            )
            PfrResult = ReplacementService.ProcessFileReplacement(TranscodeAttemptId)
            if not (PfrResult or {}).get('Success', False):
                raise RuntimeError(
                    f"ProcessFileReplacement returned failure for TranscodeAttempt {TranscodeAttemptId}: "
                    f"{(PfrResult or {}).get('ErrorMessage', 'unknown error')}"
                )

        elif Disposition == 'Pending':
            from Services.QualityTestQueueService import QualityTestQueueService
            QualityTestQueueService(self.DatabaseManager).AddToQualityTestQueue(TranscodeAttemptId)

    # directive: nvenc-rate-anchored-remediation
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

    # directive: nvenc-rate-anchored-remediation, local-staging | # see local-staging.C4
    def SetupFilePreparation(self, Job: TranscodeQueueModel, MediaFile: MediaFileModel, TranscodeAttemptId: int) -> Optional[str]:
        """Resolve worker-local source path; conditionally stage to local scratch via LocalStagingService when the worker opts in and size >= floor."""
        try:
            CanonicalLocalSource = Path(Job.StorageRootId, Job.RelativePath).Resolve(Worker.Current(Db=self.DatabaseManager.DatabaseService))
            LoggingService.LogInfo(f"Resolved source path: {CanonicalLocalSource}", "ProcessTranscodeQueueService", "SetupFilePreparation")
            from Features.TranscodeJob.LocalStagingService import LocalStagingService
            Staging = LocalStagingService(self.DatabaseManager.DatabaseService)
            SourceSizeMB = float(getattr(MediaFile, 'SizeMB', None) or getattr(Job, 'SizeMB', None) or 0)
            if Staging.ShouldStage(self.WorkerName, SourceSizeMB):
                LoggingService.LogInfo(f"LocalStaging active for MediaFileId={Job.MediaFileId} (SizeMB={SourceSizeMB}); copying to scratch before encode", "ProcessTranscodeQueueService", "SetupFilePreparation")
                StagedSource = Staging.StageSource(self.WorkerName, Job.MediaFileId, CanonicalLocalSource)
                if StagedSource:
                    return StagedSource
                LoggingService.LogWarning(f"LocalStaging.StageSource returned None for MediaFileId={Job.MediaFileId}; falling back to direct mount read", "ProcessTranscodeQueueService", "SetupFilePreparation")
            return CanonicalLocalSource

        except Exception as e:
            LoggingService.LogException("Exception in file preparation", e, "ProcessTranscodeQueueService", "SetupFilePreparation")
            self._LastSetupError = str(e)
            self.PrivateHandleFilePreparationFailure(TranscodeAttemptId, str(e))
            return None

    # directive: path-perfect-implementation | # see path.S11
    def ComputeCanonicalOutputPath(self, OutputPath: str) -> str:
        from Core.Path.Worker import Worker as _W
        from Core.Path.PathStorageRoots import GetPrefixMap as _GPM
        P = _W.Current(Db=self.DatabaseManager.DatabaseService).LocalToPath(OutputPath)
        if P is None:
            return OutputPath
        return P.CanonicalDisplay(_GPM())

    # directive: nvenc-rate-anchored-remediation
    def GetTranscodingSettings(self, Job: TranscodeQueueModel, MediaFile: MediaFileModel) -> Optional[Dict[str, Any]]:
        """Reads encoder knobs via EncoderKnobRepository (lifted columns) so CommandBuilder receives data-driven knobs."""
        try:
            from Features.Profiles.EncoderKnobRepository import EncoderKnobRepository
            from Core.Database.DatabaseService import DatabaseService
            KnobRepo = EncoderKnobRepository(DatabaseService())
            Knobs = KnobRepo.GetEncoderKnobsForProfile(
                MediaFile.AssignedProfile, MediaFile.Resolution
            )
            if Knobs is None:
                return None
            ProfileSettings = Knobs.ToDict()

            ProfileSettings['SourceVideoBitrateKbps'] = MediaFile.VideoBitrateKbps

            # directive: transcode-flow-canonical | # see transcode-flow-canonical.C25
            if (ProfileSettings.get('Codec') or '').lower() == 'av1':
                from Features.TranscodeJob.Worker.WorkerEncoderResolver import WorkerEncoderResolver
                WorkerEncoderResolver(DatabaseService()).ApplyOverrides(self.WorkerName, ProfileSettings)

            CodecFlags = self.CodecFlagsRepository.GetCodecFlagsByCodecName(ProfileSettings.get('Codec'))
            if not CodecFlags:
                return None

            # Get codec parameters
            CodecParameters = self.CodecFlagsRepository.GetCodecParametersByCodecFlagsId(CodecFlags['Id'])
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

            normalizedPath = Job.FilePath.lower().replace('\\', '/')
            fileName = ntpath.basename(Job.FilePath or "").lower()

            # Try full path first
            overrideKey = f"CRFOverride_{normalizedPath}"
            crfOverride = self.SystemSettingsRepository.GetSystemSetting(overrideKey)

            # If not found, try with just filename (for overrides set from attempt records)
            if not crfOverride:
                overrideKey = f"CRFOverride_{fileName}"
                crfOverride = self.SystemSettingsRepository.GetSystemSetting(overrideKey)

            # If still not found, try with drive letter and filename only (Z:filename.mp4 format)
            if not crfOverride and ':' in normalizedPath:
                driveAndFile = normalizedPath.split(':', 1)[1].lstrip('/').replace('/', '')
                if driveAndFile:
                    overrideKey = f"CRFOverride_{normalizedPath[0]}:{driveAndFile}"
                    crfOverride = self.SystemSettingsRepository.GetSystemSetting(overrideKey)

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

            # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C10
            if not overrideApplied:
                Decider = RetranscodeDecider(AttemptRepository=self.DatabaseManager)
                _, previousAttempt = Decider.Decide(Job.MediaFileId)

                if previousAttempt:
                    previousCRF = previousAttempt.get('Quality')
                    vmafScore = previousAttempt.get('VMAF')

                    if previousCRF and vmafScore is not None and vmafScore < 80:
                        Calculator = AdjustmentRegistry().Get('cq')
                        Overrides = Calculator.Calculate(
                            PreviousAttempt={'Quality': previousCRF, 'VMAF': vmafScore},
                            ProfileSettings=ProfileSettings,
                            GateThreshold=80.0,
                        )
                        adjustedCRF = Overrides.CRF
                        currentCRF = ProfileSettings.get('Quality')

                        if adjustedCRF:
                            finalCRF = min(adjustedCRF, currentCRF)
                            ProfileSettings['Quality'] = finalCRF

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
                'MaxCpuThreads': self.MaxCpuThreads
            }

        except Exception as e:
            LoggingService.LogException("Exception getting transcoding settings", e, "ProcessTranscodeQueueService", "GetTranscodingSettings")
            return None


    # directive: transcode-flow-canonical | # see transcode.ST5
    def BuildTranscodeCommand(self, Job: TranscodeQueueModel, MediaFile: MediaFileModel,
                              TranscodingSettings: Dict[str, Any]) -> Optional[Dict[str, str]]:
        try:
            Spec = self.CommandComposer.Build(MediaFile, Job, TranscodingSettings)
            if Spec is None:
                return None
            return {'Command': Spec.Command, 'OutputPath': Spec.OutputPath}
        except Exception as e:
            LoggingService.LogException("Exception building transcode command", e, "ProcessTranscodeQueueService", "BuildTranscodeCommand")
            return None

    # directive: nvenc-rate-anchored-remediation
    def CreateTranscodeAttempt(self, Job: TranscodeQueueModel, MediaFile: MediaFileModel = None,
                              TranscodingSettings: Dict[str, Any] = None, TranscodeCommand: str = None) -> Optional[int]:
        """Create a transcode attempt record for progress tracking."""
        try:
            if TranscodingSettings is None:
                TranscodingSettings = {}
            if MediaFile is None:
                MediaFile = self._ResolveMediaFileOrRaise(Job, "CreateTranscodeAttempt")

            ProfileSettings = TranscodingSettings.get('ProfileSettings', {})
            CodecFlags = TranscodingSettings.get('CodecFlags', {})

            # directive: e2e-bug-fixes | # see e2e-bug-fixes.C22
            ProfileName = self._ResolveProfileNameOrRaise(MediaFile, "CreateTranscodeAttempt")
            # allow: R12 SQL preexisting; relocate to ProfilesRepository in follow-up
            ProfileRow = self.DatabaseManager.DatabaseService.ExecuteQuery(
                "SELECT qualitytestrequired FROM profiles WHERE profilename = %s LIMIT 1",
                (ProfileName,),
            )
            QualityTestRequiredForProfile = bool(ProfileRow[0].get('QualityTestRequired')) if ProfileRow else True

            Attempt = TranscodeAttemptModel(
                StorageRootId=Job.StorageRootId,
                RelativePath=Job.RelativePath,
                AttemptDate=datetime.now(timezone.utc),
                Quality=ProfileSettings.get('Quality', 0),
                OldSizeBytes=Job.SizeBytes,
                NewSizeBytes=0,
                Success=None,
                SizeReductionBytes=0,
                SizeReductionPercent=0.0,
                ErrorMessage=None,
                TranscodeDurationSeconds=0.0,
                FfpmpegCommand=TranscodeCommand,
                AudioBitrateKbps=ProfileSettings.get('AudioBitrateKbps'),
                VideoBitrateKbps=ProfileSettings.get('VideoBitrateKbps'),
                ProfileName=ProfileName,
                VMAF=None,
                QualityTestRequired=QualityTestRequiredForProfile,
                QualityTestCompleted=False,
                StartTime=TranscodingSettings.get('StartTime') if TranscodingSettings else None,
                WorkerName=self.WorkerName,
                MediaFileId=getattr(Job, 'MediaFileId', None),
                ProcessingMode=(getattr(Job, 'ProcessingMode', None) or 'Transcode'),
            )

            return self.DatabaseManager.SaveTranscodeAttempt(Attempt)

        except Exception as e:
            LoggingService.LogException("Exception creating transcode attempt", e, "ProcessTranscodeQueueService", "CreateTranscodeAttempt")
            return None

    # directive: nvenc-rate-anchored-remediation
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

    # directive: nvenc-rate-anchored-remediation
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

            # directive: nvenc-rate-anchored-remediation
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

    # directive: nvenc-rate-anchored-remediation
    def HandleTranscodingResult(self, Job: TranscodeQueueModel, TranscodeResult: Dict[str, Any], TranscodeAttemptId: int, ActiveJobId: int = None):
        """Handle transcoding results - success or failure processing."""
        try:
            if TranscodeResult.get("Success", False):
                # Use pre-calculated file size from ExecuteTranscoding (captured immediately after transcode)
                NewSizeBytes = TranscodeResult.get("NewSizeBytes", 0)
                RawOutputFilePath = TranscodeResult.get("OutputFilePath", "")
                OutputFilePath = RawOutputFilePath[:-len('.inprogress')] if RawOutputFilePath.endswith('.inprogress') else RawOutputFilePath

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

                # directive: e2e-bug-fixes | # see e2e-bug-fixes.C30 -- Success stays NULL through the pipeline; flipped TRUE only after DispatchDisposition completes end-to-end so ta_one_inflight_per_mfid keeps the claim held for the whole encode-through-replacement span.
                self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                    'CompletedDate': datetime.now(timezone.utc),
                    'TranscodeDurationSeconds': TranscodeResult.get('Duration', 0.0),
                    'NewSizeBytes': NewSizeBytes,
                    'SizeReductionBytes': SizeReductionBytes,
                    'SizeReductionPercent': SizeReductionPercent,
                    'QualityTestRequired': True
                })

                self.UpdateTranscodeFileRecord(Job.FilePath, TranscodeAttemptId, True, OutputFilePath, NewSizeBytes, MediaFileId=Job.MediaFileId)

                self.DispatchDisposition(TranscodeAttemptId, Job, OutputFilePath, EncodeSucceeded=True)

                self.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {'Success': True})

                self.DatabaseManager.DeleteTranscodeQueueItem(Job.Id)

                self.DatabaseManager.DeleteTranscodeProgress(TranscodeAttemptId)

                # Complete active job if it exists
                if ActiveJobId:
                    self.ActiveJobRepository.CompleteActiveJob(ActiveJobId, Success=True)
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
            # directive: e2e-bug-fixes | # see e2e-bug-fixes.C30 -- any exception in the post-encode pipeline (DispatchDisposition, PFR, rename, MediaFiles update) flips Success=FALSE + writes ErrorMessage; no ghost row with Success=NULL or Success=TRUE + FileReplaced=FALSE possible.
            LoggingService.LogException("Exception handling transcoding result", e, "ProcessTranscodeQueueService", "HandleTranscodingResult")
            self.HandleJobFailure(Job, f"Post-encode pipeline failed: {str(e)[:400]}", TranscodeAttemptId, ActiveJobId)

    # directive: nvenc-rate-anchored-remediation
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
                # directive: e2e-bug-fixes | # see e2e-bug-fixes.C22
                MediaFile = self._ResolveMediaFileOrRaise(Job, "HandleJobFailure")
                ResolvedProfileName = self._ResolveProfileNameOrRaise(MediaFile, "HandleJobFailure")

                Attempt = TranscodeAttemptModel(
                    StorageRootId=Job.StorageRootId,
                    RelativePath=Job.RelativePath,
                    AttemptDate=datetime.now(timezone.utc),
                    Quality=0,
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
                    ProfileName=ResolvedProfileName,
                    VMAF=None,
                    CompletedDate=datetime.now(timezone.utc),
                    WorkerName=self.WorkerName,
                    MediaFileId=getattr(Job, 'MediaFileId', None),
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
                self.ActiveJobRepository.CompleteActiveJob(ActiveJobId, Success=False, ErrorMessage=ErrorMessage)
                LoggingService.LogInfo(f"Completed failed active job {ActiveJobId}",
                                      "ProcessTranscodeQueueService", "HandleJobFailure")

            LoggingService.LogError(f"Job {Job.Id} failed and removed from queue: {ErrorMessage}", "ProcessTranscodeQueueService", "HandleJobFailure")

        except Exception as e:
            LoggingService.LogException("Exception handling job failure", e, "ProcessTranscodeQueueService", "HandleJobFailure")

    # directive: nvenc-rate-anchored-remediation
    def _CleanupFailedAttemptFiles(self, TranscodeAttemptId: int):
        """Clean up partial output file and TemporaryFilePaths row for a failed transcode attempt."""
        try:
            LoggingService.LogInfo(f"Cleaning up files for failed TranscodeAttempt {TranscodeAttemptId}",
                                 "ProcessTranscodeQueueService", "_CleanupFailedAttemptFiles")

            # directive: path-schema-migration | # see path.S8
            from Features.QualityTesting.QualityTestRepository import QualityTestRepository
            TemporaryFilePathRecord = QualityTestRepository(self.DatabaseManager.DatabaseService).GetTemporaryFilePath(TranscodeAttemptId)

            if TemporaryFilePathRecord:
                # directive: path-perfect-implementation | # see path.S11
                OutSid = TemporaryFilePathRecord.get('OutputStorageRootId')
                OutRel = TemporaryFilePathRecord.get('OutputRelativePath')
                ActualPath = None
                if OutSid is not None and OutRel is not None:
                    try:
                        ActualPath = Path(OutSid, OutRel).Resolve(Worker.Current(Db=self.DatabaseManager.DatabaseService))
                    except PathError:
                        ActualPath = None
                if ActualPath:
                    if LocalExists(ActualPath):
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

                # directive: local-staging | # see local-staging.C11
                if TemporaryFilePathRecord.get('IsStaged'):
                    from Features.TranscodeJob.LocalStagingService import LocalStagingService
                    Staging = LocalStagingService(self.DatabaseManager.DatabaseService)
                    Staging.Cleanup(TemporaryFilePathRecord.get('LocalSourcePath'))
                    Staging.Cleanup(TemporaryFilePathRecord.get('LocalOutputPath'))

                # Delete the TemporaryFilePaths row
                self.DatabaseManager.DeleteTemporaryFilePath(TranscodeAttemptId)
            else:
                LoggingService.LogInfo(f"No TemporaryFilePaths record found for TranscodeAttempt {TranscodeAttemptId} (nothing to clean up)",
                                     "ProcessTranscodeQueueService", "_CleanupFailedAttemptFiles")

        except Exception as e:
            LoggingService.LogException(f"Exception cleaning up failed attempt files for TranscodeAttempt {TranscodeAttemptId}",
                                       e, "ProcessTranscodeQueueService", "_CleanupFailedAttemptFiles")

    # directive: nvenc-rate-anchored-remediation
    def CleanupOrContinue(self, Job: TranscodeQueueModel):
        """Determine next action after job completion."""
        try:
            LoggingService.LogInfo(f"Job {Job.Id} cleanup completed", "ProcessTranscodeQueueService", "CleanupOrContinue")

        except Exception as e:
            LoggingService.LogException("Exception in cleanup", e, "ProcessTranscodeQueueService", "CleanupOrContinue")

    # directive: nvenc-rate-anchored-remediation
    def GetOutputFilePathFromCommand(self, Job: TranscodeQueueModel, TranscodeAttemptId: int = None) -> Optional[str]:
        """Get output file path for a transcoding job. Uses TemporaryFilePaths table as source of truth if TranscodeAttemptId provided."""
        try:
            # If TranscodeAttemptId is provided, try to get the actual output path from TemporaryFilePaths table first
            if TranscodeAttemptId:
                try:
                    # directive: path-schema-migration | # see path.S8
                    from Features.QualityTesting.QualityTestRepository import QualityTestRepository
                    TemporaryFilePathRecord = QualityTestRepository(self.DatabaseManager.DatabaseService).GetTemporaryFilePath(TranscodeAttemptId)
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

            InputFileName = ntpath.basename(Job.FilePath or "")

            # Get the MediaFile to determine source resolution
            MediaFile = self.DatabaseManager.GetMediaFileByPath(Job.FilePath)
            if not MediaFile:
                LoggingService.LogWarning(f"Could not get MediaFile for {Job.FilePath}", "ProcessTranscodeQueueService", "GetOutputFilePathFromCommand")
                return ntpath.join("C:\\MediaVortex",InputFileName)

            # Get transcoding settings to determine target resolution
            TranscodingSettings = self.GetTranscodingSettings(Job, MediaFile)
            if not TranscodingSettings:
                LoggingService.LogWarning(f"Could not get transcoding settings for {Job.FilePath}", "ProcessTranscodeQueueService", "GetOutputFilePathFromCommand")
                return ntpath.join("C:\\MediaVortex",InputFileName)

            # Generate output filename with target resolution and container type
            ProfileSettings = TranscodingSettings.get('ProfileSettings', {})
            SourceResolution = TranscodingSettings.get('SourceResolution', '')
            TargetResolution = ProfileSettings.get('TargetResolution', '')
            ContainerType = ProfileSettings.get('ContainerType', 'mp4')

            OutputFileName = self._GenerateOutputFileName(InputFileName, SourceResolution, TargetResolution, ContainerType)
            OutputFilePath = ntpath.join("C:\\MediaVortex",OutputFileName)

            LoggingService.LogInfo(f"Calculated output path (fallback): {OutputFilePath}", "ProcessTranscodeQueueService", "GetOutputFilePathFromCommand")
            return OutputFilePath

        except Exception as e:
            LoggingService.LogException("Exception getting output file path", e, "ProcessTranscodeQueueService", "GetOutputFilePathFromCommand")
            return None

    # directive: nvenc-rate-anchored-remediation
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

    # directive: nvenc-rate-anchored-remediation
    def _GenerateOutputFileName(self, OriginalFileName: str, SourceResolution: str, TargetResolution: str, ContainerType: str = 'mp4') -> str:
        """Generate output filename with target resolution and container type."""
        try:
            # Get the base filename without extension
            BaseName = ntpath.splitext(OriginalFileName or "")[0]

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
            NewBaseName = ntpath.splitext(NewBaseName or "")[0]  # Remove old extension

            # Add container type extension
            return f"{NewBaseName}.{ContainerType}"

        except Exception:
            # If anything goes wrong, return original filename with container extension
            BaseName = ntpath.splitext(OriginalFileName or "")[0]
            return f"{BaseName}.{ContainerType}"

    # directive: nvenc-rate-anchored-remediation
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

    # directive: nvenc-rate-anchored-remediation
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

    # directive: nvenc-rate-anchored-remediation
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


    # directive: nvenc-rate-anchored-remediation
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

    # directive: nvenc-rate-anchored-remediation
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

    # directive: nvenc-rate-anchored-remediation
    def _ResolveTfpPathParts(self, Job, OutputPath: str):
        """Compute (SrcId, SrcRel, OutId, OutRel) for TemporaryFilePaths writes.
        Output side is derived from Job.RelativePath (canonical, always '/'-separated)
        and the basename of the worker-local OutputPath. The .inprogress file
        always lands next to the source, so OutputStorageRootId == source
        StorageRootId and OutRel == <dirname(Job.RelativePath)>/<output_basename>.
        Parsing the worker-local OutputPath against StorageRoots was fragile
        (Linux os.path.basename on a Windows-shaped canonical string returned
        the whole string, polluting the stored relative path with 'T:/'
        fragments)."""
        SrcId = getattr(Job, 'StorageRootId', None)
        SrcRel = getattr(Job, 'RelativePath', None) or None
        OutBase = LocalBasename(OutputPath) if OutputPath else ''
        OutId = SrcId
        SrcDirRel = SrcRel.rsplit('/', 1)[0] if (SrcRel and '/' in SrcRel) else ''
        OutRel = f"{SrcDirRel}/{OutBase}" if SrcDirRel else OutBase
        OutRel = OutRel or None
        return SrcId, SrcRel, OutId, OutRel

    # directive: local-staging | # see local-staging.C7
    def _GetLocalStagingPathsIfActive(self, EffectiveInputPath: str, OutputPath: str):
        """Return (LocalSourcePath, LocalOutputPath) iff EffectiveInputPath lies under this worker's LocalScratchDir; else (None, None)."""
        try:
            Rows = self.DatabaseManager.DatabaseService.ExecuteQuery("SELECT LocalScratchDir FROM Workers WHERE WorkerName = %s", (self.WorkerName,))
            if not Rows:
                return (None, None)
            ScratchDir = (Rows[0].get('localscratchdir') or '').strip()
            if not ScratchDir:
                return (None, None)
            EffStr = str(EffectiveInputPath or '')
            if EffStr.startswith(ScratchDir):
                return (EffStr, str(OutputPath) if OutputPath else None)
            return (None, None)
        except Exception as Ex:
            LoggingService.LogException("_GetLocalStagingPathsIfActive failed", Ex, "ProcessTranscodeQueueService", "_GetLocalStagingPathsIfActive")
            return (None, None)

    # directive: local-staging | # see local-staging.C10
    def _ResolveCanonicalOutputPath(self, OutputStorageRootId, OutputRelativePath) -> Optional[str]:
        """Resolve the canonical typed-pair output path to the worker-native mount path (e.g. M:\\Show\\foo-mv.mp4.inprogress)."""
        try:
            if OutputStorageRootId is None or OutputRelativePath is None:
                return None
            return Path(OutputStorageRootId, OutputRelativePath).Resolve(Worker.Current(Db=self.DatabaseManager.DatabaseService))
        except Exception as Ex:
            LoggingService.LogException("_ResolveCanonicalOutputPath failed", Ex, "ProcessTranscodeQueueService", "_ResolveCanonicalOutputPath")
            return None

    # directive: local-staging | # see local-staging.C10
    def _CopyBackStagedOutput(self, LocalOutputPath: str, CanonicalOutputPath: str, MediaFileId: int) -> bool:
        """Copy local .inprogress back to the canonical side-by-side path; size-verify; return False on any failure."""
        try:
            if not LocalOutputPath or not CanonicalOutputPath:
                LoggingService.LogError(f"Copy-back missing path: local={LocalOutputPath} canonical={CanonicalOutputPath} mid={MediaFileId}", "ProcessTranscodeQueueService", "_CopyBackStagedOutput")
                return False
            import shutil as _shutil
            from Core.Path.LocalPath import LocalDirname, LocalExists, LocalGetSize
            DestDir = LocalDirname(CanonicalOutputPath)
            if DestDir and not LocalExists(DestDir):
                os.makedirs(DestDir, exist_ok=True)
            LoggingService.LogInfo(f"Copy-back staged output for MediaFileId={MediaFileId}: {LocalOutputPath} -> {CanonicalOutputPath}", "ProcessTranscodeQueueService", "_CopyBackStagedOutput")
            _shutil.copy2(LocalOutputPath, CanonicalOutputPath)
            SrcSize = LocalGetSize(LocalOutputPath)
            DstSize = LocalGetSize(CanonicalOutputPath)
            if SrcSize != DstSize:
                LoggingService.LogError(f"Copy-back size mismatch for MediaFileId={MediaFileId}: src={SrcSize} dst={DstSize}; deleting partial canonical write", "ProcessTranscodeQueueService", "_CopyBackStagedOutput")
                try:
                    os.remove(CanonicalOutputPath)
                except Exception:
                    pass
                return False
            LoggingService.LogInfo(f"Copy-back complete for MediaFileId={MediaFileId}: {DstSize} bytes at {CanonicalOutputPath}", "ProcessTranscodeQueueService", "_CopyBackStagedOutput")
            return True
        except Exception as Ex:
            LoggingService.LogException(f"_CopyBackStagedOutput failed for MediaFileId={MediaFileId}", Ex, "ProcessTranscodeQueueService", "_CopyBackStagedOutput")
            return False

    # directive: local-staging | # see local-staging.C11
    def _CleanupLocalScratchForAttempt(self, MediaFileId: int) -> bool:
        """Idempotent removal of the per-job scratch subdir (source + any leftover output)."""
        try:
            from Features.TranscodeJob.LocalStagingService import LocalStagingService
            return LocalStagingService(self.DatabaseManager.DatabaseService).CleanupJobScratchDir(self.WorkerName, MediaFileId)
        except Exception as Ex:
            LoggingService.LogException(f"_CleanupLocalScratchForAttempt failed for MediaFileId={MediaFileId}", Ex, "ProcessTranscodeQueueService", "_CleanupLocalScratchForAttempt")
            return False

    # directive: path-schema-migration, local-staging | # see path.S8, local-staging.C7
    def PrivateCreateTemporaryFilePathRecord(self, TranscodeAttemptId: int,
                                              SourceStorageRootId: int, SourceRelativePath: str,
                                              OutputStorageRootId: Optional[int] = None,
                                              OutputRelativePath: Optional[str] = None,
                                              LocalSourcePath: Optional[str] = None,
                                              LocalOutputPath: Optional[str] = None) -> Optional[int]:
        """Route TemporaryFilePaths insert through QualityTestRepository; populate worker-local staging paths when staging is active."""
        try:
            LoggingService.LogFunctionEntry("PrivateCreateTemporaryFilePathRecord", "ProcessTranscodeQueueService",
                                          TranscodeAttemptId, SourceStorageRootId, SourceRelativePath,
                                          OutputStorageRootId, OutputRelativePath, LocalSourcePath, LocalOutputPath)

            from Features.QualityTesting.QualityTestRepository import QualityTestRepository
            _Repo = QualityTestRepository(self.DatabaseManager.DatabaseService)
            TemporaryFilePathId = _Repo.CreateTemporaryFilePath(
                TranscodeAttemptId, SourceStorageRootId, SourceRelativePath,
                OutputStorageRootId, OutputRelativePath,
                LocalSourcePath, LocalOutputPath,
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

    # directive: nvenc-rate-anchored-remediation
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

    # directive: nvenc-rate-anchored-remediation
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
            from Features.ServiceControl.ActiveJobRepository import ActiveJobRepository as _AJR
            process_mgmt = ProcessManagementService()
            active_jobs = self.ActiveJobRepository.GetActiveJobsByService(_AJR.BuildActiveJobsQuery("TranscodeService"))
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
                    self.ActiveJobRepository.CompleteActiveJob(active_job['Id'], False, "Cancelled by user")
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

    # directive: nvenc-rate-anchored-remediation
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

    # directive: nvenc-rate-anchored-remediation
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

    # directive: nvenc-rate-anchored-remediation
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

    # directive: nvenc-rate-anchored-remediation
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

    # directive: nvenc-rate-anchored-remediation
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
