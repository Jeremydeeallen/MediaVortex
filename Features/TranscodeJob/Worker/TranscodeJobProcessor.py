import os
import threading
from datetime import datetime, timezone
from Core.Logging.LoggingService import LoggingService
from Core.Path import Path, Worker
from Core.Path.LocalPath import LocalExists
from Features.TranscodeJob.Worker.JobProcessor import JobProcessor
from Features.TranscodeJob.Worker.JobResult import JobResult


# directive: worker-loop-method-extraction | # see worker-loop.C5
class TranscodeJobProcessor(JobProcessor):
    """Self-contained JobProcessor strategy for ProcessingMode='Transcode'; absorbs ProcessTranscodeQueueService.ProcessJob orchestration."""

    # directive: worker-loop-method-extraction | # see worker-loop.C5
    def __init__(self, QueueService):
        """Inject the QueueService that retains shared helpers (GetMediaFileData, SetupFilePreparation, GetTranscodingSettings, BuildTranscodeCommand, HandleJobFailure, etc.)."""
        self.QueueService = QueueService

    # directive: worker-loop-method-extraction | # see worker-loop.C5
    def Process(self, Job, MediaFile=None) -> JobResult:
        """Run the Transcode orchestration to terminal state; return JobResult."""
        try:
            self._ProcessImpl(Job)
            return JobResult(Success=True)
        except Exception as Ex:
            LoggingService.LogException(f"TranscodeJobProcessor.Process failed for job {getattr(Job, 'Id', None)}", Ex, "TranscodeJobProcessor", "Process")
            return JobResult(Success=False, ErrorMessage=str(Ex))

    # directive: worker-loop-method-extraction | # see worker-loop.C5
    def _ProcessImpl(self, Job):
        """Port of ProcessTranscodeQueueService.ProcessJob with self.<X> rewritten to self.QueueService.<X>."""
        if Job.IsRemux:
            self.QueueService.ProcessRemuxJob(Job)
            return
        if Job.IsSubtitleFix:
            self.QueueService.ProcessSubtitleFixJob(Job)
            return
        if Job.IsTestMode:
            self.QueueService.ProcessTestVariantJob(Job)
            return

        ActiveJobId = None
        OutputPath = None
        TemporaryFilePathId = None
        TranscodeAttemptId = None
        OwnershipTransferred = False
        try:
            LoggingService.LogInfo(f"Starting job processing for job ID: {Job.Id}", "TranscodeJobProcessor", "_ProcessImpl")

            ActiveJobId = self.QueueService.ActiveJobRepository.CreateActiveJob(
                ServiceName="TranscodeService",
                JobType="Transcode",
                QueueId=Job.Id,
                ProcessId=os.getpid(),
                ThreadId=threading.get_ident(),
                WorkerName=self.QueueService.WorkerName
            )

            if ActiveJobId == 0:
                LoggingService.LogError(f"Failed to create active job for queue ID {Job.Id}", "TranscodeJobProcessor", "_ProcessImpl")
                self.QueueService.HandleJobFailure(Job, "Failed to create active job record", None, ActiveJobId)
                return

            self.QueueService.DatabaseManager.UpdateTranscodeQueueStatus(Job.Id, "Running")

            MediaFile = self.QueueService.GetMediaFileData(Job)
            if not MediaFile:
                FallbackAttemptId = self.QueueService.CreateTranscodeAttempt(Job, None, None, None)
                self.QueueService.HandleJobFailure(Job, "Failed to get media file data", FallbackAttemptId, ActiveJobId)
                return

            LocalSourcePath = Path(MediaFile.StorageRootId, MediaFile.RelativePath).Resolve(Worker.Current(Db=self.QueueService.DatabaseManager.DatabaseService))
            if not LocalExists(LocalSourcePath):
                ErrMsg = f"Source file missing on disk: {LocalSourcePath}"
                LoggingService.LogWarning(ErrMsg, "TranscodeJobProcessor", "_ProcessImpl")
                self.QueueService._MarkMediaFileSourceMissing(MediaFile.Id, ErrMsg)
                try:
                    self.QueueService.DatabaseManager.DeleteTranscodeQueueItem(Job.Id)
                except Exception as DelEx:
                    LoggingService.LogException("Failed to delete queue item for missing source", DelEx, "TranscodeJobProcessor", "_ProcessImpl")
                if ActiveJobId:
                    try:
                        self.QueueService.ActiveJobRepository.DeleteActiveJob(ActiveJobId)
                    except Exception as DelEx:
                        LoggingService.LogException("Failed to delete active job for missing source", DelEx, "TranscodeJobProcessor", "_ProcessImpl")
                return

            TranscodeAttemptId = self.QueueService.CreateTranscodeAttempt(Job, None, None, None)
            if not TranscodeAttemptId:
                self.QueueService.HandleJobFailure(Job, "Failed to create transcode attempt record", None, ActiveJobId)
                return

            self.QueueService.UpdateTranscodeProgress(TranscodeAttemptId, "Initializing", 0.0, "Job started, getting ready")
            self.QueueService.UpdateTranscodeProgress(TranscodeAttemptId, "Loading Media Data", 0.0, "Media metadata loaded")
            self.QueueService.UpdateTranscodeProgress(TranscodeAttemptId, "Loading Settings", 0.0, "Loading transcoding profile settings...")

            TranscodingSettings = self.QueueService.GetTranscodingSettings(Job, MediaFile)
            if not TranscodingSettings:
                self.QueueService.HandleJobFailure(Job, "Failed to get transcoding settings", TranscodeAttemptId, ActiveJobId)
                return

            self.QueueService.UpdateTranscodeProgress(TranscodeAttemptId, "Preparing Files", 0.0, "Preparing files for transcoding...")

            self.QueueService._LastSetupError = None
            EffectiveInputPath = self.QueueService.SetupFilePreparation(Job, MediaFile, TranscodeAttemptId)
            if not EffectiveInputPath:
                Detail = self.QueueService._LastSetupError or "unknown"
                self.QueueService.HandleJobFailure(Job, f"Failed to setup file preparation: {Detail}", TranscodeAttemptId, ActiveJobId)
                return

            self.QueueService.UpdateTranscodeProgress(TranscodeAttemptId, "Building Command", 0.0, "Building FFmpeg command...")

            TranscodingSettings['InputPath'] = EffectiveInputPath
            CommandResult = self.QueueService.BuildTranscodeCommand(Job, MediaFile, TranscodingSettings)
            if not CommandResult:
                self.QueueService.HandleJobFailure(Job, "Failed to build transcoding command", TranscodeAttemptId, ActiveJobId)
                return

            TranscodeCommand = CommandResult['Command']
            OutputPath = CommandResult['OutputPath']

            SrcId, SrcRel, OutId, OutRel = self.QueueService._ResolveTfpPathParts(Job, OutputPath)
            LocalSrcPath, LocalOutPath = self.QueueService._GetLocalStagingPathsIfActive(EffectiveInputPath, OutputPath)
            TemporaryFilePathId = self.QueueService.PrivateCreateTemporaryFilePathRecord(
                TranscodeAttemptId, SrcId, SrcRel, OutId, OutRel,
                LocalSourcePath=LocalSrcPath, LocalOutputPath=LocalOutPath)
            if not TemporaryFilePathId:
                LoggingService.LogWarning(f"Failed to create TemporaryFilePath record for TranscodeAttempt {TranscodeAttemptId}, but file preparation succeeded", "TranscodeJobProcessor", "_ProcessImpl")

            self.QueueService.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
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

            self.QueueService.UpdateTranscodeProgress(TranscodeAttemptId, "Starting Transcode", 0.0, "Starting video processing...")

            TranscodeResult = self.QueueService.ExecuteTranscoding(Job, TranscodeCommand, TranscodeAttemptId, MediaFile, ActiveJobId)
            if not TranscodeResult.get("Success", False):
                self.QueueService._DeleteInProgressFile(OutputPath)
                self.QueueService.HandleJobFailure(Job, f"Transcoding failed: {TranscodeResult.get('ErrorMessage', 'Unknown error')}", TranscodeAttemptId, ActiveJobId)
                return

            if not self.QueueService._VerifyInProgressFile(OutputPath):
                self.QueueService._DeleteInProgressFile(OutputPath)
                self.QueueService.HandleJobFailure(Job, f"Transcode output failed FFprobe verification: {OutputPath}", TranscodeAttemptId, ActiveJobId)
                return

            SkipModeBCopyBack = False
            if LocalSrcPath and LocalOutPath:
                from Features.TranscodeJob.LocalStagingService import LocalStagingService
                Staging = LocalStagingService(self.QueueService.DatabaseManager.DatabaseService)
                if Staging.IsLocalVmafFirst(self.QueueService.WorkerName):
                    from Features.QualityTesting.QualityTestingBusinessService import QualityTestingBusinessService
                    from Features.QualityTesting.PostTranscodeGateConfigRepository import PostTranscodeGateConfigRepository
                    ModeAResult = QualityTestingBusinessService(self.QueueService.DatabaseManager).RunLocalVmafForAttempt(TranscodeAttemptId, LocalSrcPath, OutputPath)
                    if ModeAResult.get('Success'):
                        ModeAScore = float(ModeAResult.get('VMAFScore') or 0.0)
                        GateConfig = PostTranscodeGateConfigRepository(self.QueueService.DatabaseManager.DatabaseService).Get()
                        if ModeAScore < float(GateConfig.VmafAutoReplaceMinThreshold):
                            LoggingService.LogInfo(f"Mode A VMAF {ModeAScore} < {GateConfig.VmafAutoReplaceMinThreshold} for attempt {TranscodeAttemptId}; skipping copy-back, disposition will Requeue", "TranscodeJobProcessor", "_ProcessImpl")
                            self.QueueService._CleanupLocalScratchForAttempt(Job.MediaFileId)
                            SkipModeBCopyBack = True
                        else:
                            LoggingService.LogInfo(f"Mode A VMAF {ModeAScore} >= {GateConfig.VmafAutoReplaceMinThreshold} for attempt {TranscodeAttemptId}; proceeding to copy-back + replacement", "TranscodeJobProcessor", "_ProcessImpl")
                    else:
                        LoggingService.LogWarning(f"Mode A VMAF execution failed for attempt {TranscodeAttemptId}: {ModeAResult.get('Error')}; falling through to Mode B canonical copy-back", "TranscodeJobProcessor", "_ProcessImpl")

            if LocalOutPath and not SkipModeBCopyBack:
                CanonicalOutputPath = self.QueueService._ResolveCanonicalOutputPath(OutId, OutRel)
                if not self.QueueService._CopyBackStagedOutput(OutputPath, CanonicalOutputPath, Job.MediaFileId):
                    self.QueueService.HandleJobFailure(Job, f"Staged output copy-back failed: {OutputPath} -> {CanonicalOutputPath}", TranscodeAttemptId, ActiveJobId)
                    return
                self.QueueService._CleanupLocalScratchForAttempt(Job.MediaFileId)
                OutputPath = CanonicalOutputPath

            self.QueueService.UpdateTranscodeProgress(TranscodeAttemptId, "Finalizing", 0.0, "Processing results and cleanup...")

            OwnershipTransferred = True
            self.QueueService.HandleTranscodingResult(Job, TranscodeResult, TranscodeAttemptId, ActiveJobId)
            self.QueueService.CleanupOrContinue(Job)

            LoggingService.LogInfo(f"Completed job processing for job ID: {Job.Id}", "TranscodeJobProcessor", "_ProcessImpl")

        except Exception as e:
            LoggingService.LogException(f"Exception processing job {Job.Id}", e, "TranscodeJobProcessor", "_ProcessImpl")
            self.QueueService.HandleJobFailure(Job, f"Exception during processing: {str(e)}", TranscodeAttemptId, ActiveJobId)
        finally:
            if not OwnershipTransferred:
                if OutputPath:
                    try:
                        self.QueueService._DeleteInProgressFile(OutputPath)
                    except Exception as CleanupEx:
                        LoggingService.LogException(f"Worker-owned .inprogress cleanup failed for job {Job.Id}", CleanupEx, "TranscodeJobProcessor", "_ProcessImpl")
                if TemporaryFilePathId and TranscodeAttemptId:
                    try:
                        self.QueueService.DatabaseManager.DeleteTemporaryFilePath(TranscodeAttemptId)
                    except Exception as TfpEx:
                        LoggingService.LogException(f"Worker-owned TFP cleanup failed for job {Job.Id}", TfpEx, "TranscodeJobProcessor", "_ProcessImpl")
