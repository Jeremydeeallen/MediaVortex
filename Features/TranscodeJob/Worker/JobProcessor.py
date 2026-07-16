import os
import threading
from datetime import datetime, timezone
from Core.Logging.LoggingService import LoggingService
from Core.Path import Path, Worker
from Core.WorkerContext import WorkerContext
from Core.Path.LocalPath import LocalBasename, LocalDirname, LocalExists, LocalJoin, LocalSplitExt
from Features.AudioNormalization.Services import AudioPreEncodeFacade
from Features.ServiceControl.JobPhase import JobPhase
from Features.TranscodeJob.Emit.OutputFilenameBuilder import OutputFilenameBuilder
from Features.TranscodeJob.Worker.JobResult import JobResult

# directive: audio-dialog-boost-real | # see audio-normalization.C8
_AUDIO_EMIT_MODES = frozenset(('Transcode', 'Remux', 'AudioFix', 'Quick', 'SubtitleFix'))


# directive: transcode-worker-unification | # see worker-loop.C2
class JobProcessor:
    """Template Method: unified orchestration for every ProcessingMode; mode-specific BuildCommand + HandleResult delegated to ITranscodeJobStrategy."""

    # directive: transcode-worker-unification | # see worker-loop.C2
    def __init__(self, QueueService, Registry):
        # see worker-loop.C2
        self.QueueService = QueueService
        self.Registry = Registry

    # directive: transcode-worker-unification | # see worker-loop.C2
    def Process(self, Job, MediaFile=None) -> JobResult:
        # see worker-loop.C2
        WorkerContext.Bind()
        Strategy = self.Registry.Get(Job.ProcessingMode, QueueService=self.QueueService)
        ActiveJobId = None
        TranscodeAttemptId = None
        TargetLocalPath = None
        TemporaryFilePathId = None
        OwnershipTransferred = False
        Mode = Job.ProcessingMode
        try:
            LoggingService.LogInfo(f"Starting {Mode} job processing for job ID: {Job.Id}", "JobProcessor", "Process")

            ActiveJobId = self.QueueService.ActiveJobRepository.CreateActiveJob(
                ServiceName="TranscodeService", JobType=Mode, QueueId=Job.Id,
                ProcessId=os.getpid(), ThreadId=threading.get_ident(),
                WorkerName=self.QueueService.WorkerName
            )
            if ActiveJobId == 0:
                self.QueueService.HandleJobFailure(Job, f"Failed to create active job record for {Mode}", None, ActiveJobId)
                return JobResult(Success=False, ErrorMessage=f"ActiveJob creation failed for {Mode}")

            self.QueueService.DatabaseManager.UpdateTranscodeQueueStatus(Job.Id, "Running")

            if not MediaFile:
                MediaFile = self.QueueService.GetMediaFileData(Job)
            if not MediaFile:
                self.QueueService.HandleJobFailure(Job, f"Failed to get media file data for {Mode}", None, ActiveJobId)
                return JobResult(Success=False, ErrorMessage="MediaFile load failed")

            LocalSourcePath = Path(Job.StorageRootId, Job.RelativePath).Resolve(Worker.Current(Db=self.QueueService.DatabaseManager.DatabaseService))
            if not LocalExists(LocalSourcePath):
                ErrMsg = f"Source file missing on disk: {LocalSourcePath}"
                LoggingService.LogWarning(ErrMsg, "JobProcessor", "Process")
                self.QueueService._MarkMediaFileSourceMissing(MediaFile.Id, ErrMsg)
                self.QueueService.DatabaseManager.DeleteTranscodeQueueItem(Job.Id)
                if ActiveJobId:
                    self.QueueService.ActiveJobRepository.DeleteActiveJob(ActiveJobId)
                return JobResult(Success=False, ErrorMessage=ErrMsg)

            TranscodeAttemptId = self.QueueService.CreateTranscodeAttempt(Job, None, None, None)
            if not TranscodeAttemptId:
                self.QueueService.HandleJobFailure(Job, f"Failed to create transcode attempt record for {Mode}", None, ActiveJobId)
                return JobResult(Success=False, ErrorMessage="TranscodeAttempt creation failed")

            self.QueueService.UpdateTranscodeProgress(TranscodeAttemptId, "Preparing Files", 0.0, f"Preparing files for {Mode}...")
            self.QueueService._LastSetupError = None
            EffectiveInputPath = self.QueueService.SetupFilePreparation(Job, MediaFile, TranscodeAttemptId)
            if not EffectiveInputPath:
                Detail = self.QueueService._LastSetupError or "unknown"
                self.QueueService.HandleJobFailure(Job, f"Failed to setup file preparation for {Mode}: {Detail}", TranscodeAttemptId, ActiveJobId)
                return JobResult(Success=False, ErrorMessage=f"File prep failed: {Detail}")

            BaseName, _ = LocalSplitExt(LocalBasename(EffectiveInputPath))
            BaseName = OutputFilenameBuilder().CollapseMvSuffix(BaseName)
            TargetLocalPath = LocalJoin(LocalDirname(EffectiveInputPath), BaseName + '-mv.mp4.inprogress')

            # directive: transcode-flow-canonical -- skip Demucs when source lacks confirmed English audio; Dialog Boost premix is English-vocal-model only
            if getattr(MediaFile, 'HasExplicitEnglishAudio', None) is not True:
                LoggingService.LogInfo(
                    f"Skipping PreEncodeAudio (Demucs Dialog Boost) for {MediaFile.FileName}: HasExplicitEnglishAudio != True (languages={getattr(MediaFile, 'AudioLanguages', None)})",
                    "JobProcessor", "Process",
                )
                PreAudio = None
            else:
                self.QueueService.DatabaseManager.SetJobPhase(ActiveJobId, JobPhase.PreEncode)
                PreAudio = self._RunPreEncodeAudio(Mode, EffectiveInputPath, Job, TranscodeAttemptId)
            AudioPreEncodeFacade.PersistSourceLoudness(MediaFile.Id, MediaFile, PreAudio)
            self.QueueService.UpdateTranscodeProgress(TranscodeAttemptId, "Building Command", 0.0, f"Building {Mode} command...")
            CommandResult = Strategy.BuildCommand(
                Job, MediaFile,
                Context={
                    'QueueService': self.QueueService,
                    'InputPath': EffectiveInputPath,
                    'OutputPath': TargetLocalPath,
                    'FFmpegPath': self.QueueService.FFmpegPath,
                    'FFprobePath': self.QueueService.FFprobePath,
                    'OutputDirectory': LocalDirname(EffectiveInputPath),
                    'TranscodeAttemptId': TranscodeAttemptId,
                    'DemucsPremixPath': (PreAudio or {}).get('DemucsPremixPath'),
                    'VocalsRmsDbfs': (PreAudio or {}).get('VocalsRmsDbfs'),
                    'PremixMeasuredI': (PreAudio or {}).get('PremixMeasuredI'),
                    'PremixMeasuredLra': (PreAudio or {}).get('PremixMeasuredLra'),
                    'PremixMeasuredTp': (PreAudio or {}).get('PremixMeasuredTp'),
                    'PremixMeasuredThresh': (PreAudio or {}).get('PremixMeasuredThresh'),
                },
            )
            if not CommandResult:
                self.QueueService.HandleJobFailure(Job, f"Failed to build {Mode} command", TranscodeAttemptId, ActiveJobId)
                return JobResult(Success=False, ErrorMessage="Command build failed")

            SrcId, SrcRel, OutId, OutRel = self.QueueService._ResolveTfpPathParts(Job, CommandResult.OutputPath)
            TemporaryFilePathId = self.QueueService.PrivateCreateTemporaryFilePathRecord(
                TranscodeAttemptId, SrcId, SrcRel, OutId, OutRel)

            # directive: transcode-flow-canonical | # see transcode.ST5
            ProfileName = Strategy.DefaultProfileName(Job)
            self.QueueService.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                'FilePath': Job.FilePath,
                'AttemptDate': datetime.now(timezone.utc),
                'OldSizeBytes': Job.SizeBytes,
                'NewSizeBytes': 0,
                'Success': None,
                'FfpmpegCommand': CommandResult.Command,
                'ProfileName': ProfileName,
                'VMAF': None,
            })

            self.QueueService.UpdateTranscodeProgress(TranscodeAttemptId, Mode, 0.0, f"Running {Mode}...")
            TranscodeResult = self.QueueService.ExecuteTranscoding(
                Job, CommandResult.Command, TranscodeAttemptId, MediaFile, ActiveJobId
            )
            if not TranscodeResult.get("Success", False):
                self.QueueService._DeleteInProgressFile(CommandResult.OutputPath)
                self.QueueService.HandleJobFailure(Job, f"{Mode} failed: {TranscodeResult.get('ErrorMessage', 'Unknown error')}", TranscodeAttemptId, ActiveJobId)
                return JobResult(Success=False, ErrorMessage="FFmpeg exec failed")

            if not self.QueueService._VerifyInProgressFile(CommandResult.OutputPath):
                self.QueueService._DeleteInProgressFile(CommandResult.OutputPath)
                self.QueueService.HandleJobFailure(Job, f"{Mode} output failed FFprobe verification", TranscodeAttemptId, ActiveJobId)
                return JobResult(Success=False, ErrorMessage="Output verification failed")

            # # see local-staging.S4 -- when local-staging is active, ship .inprogress back to canonical before disposition
            FinalOutputPath = CommandResult.OutputPath
            _LocalSrc, LocalOut = self.QueueService._GetLocalStagingPathsIfActive(EffectiveInputPath, CommandResult.OutputPath)
            if LocalOut:
                CanonicalOut = self.QueueService._ResolveCanonicalOutputPath(OutId, OutRel)
                if not CanonicalOut or not self.QueueService._CopyBackStagedOutput(LocalOut, CanonicalOut, MediaFile.Id):
                    self.QueueService._DeleteInProgressFile(CommandResult.OutputPath)
                    self.QueueService.HandleJobFailure(Job, f"{Mode}: local-staging copy-back to canonical failed", TranscodeAttemptId, ActiveJobId)
                    return JobResult(Success=False, ErrorMessage="Copy-back failed")
                FinalOutputPath = CanonicalOut

            try:
                # directive: transcode-flow-canonical | # see transcode.ST5
                from Features.AudioNormalization.Services.PostEncodeMeasurementService import PostEncodeMeasurementService
                PostEncodeMeasurementService(
                    FFmpegPath=self.QueueService.FFmpegPath,
                    FFprobePath=self.QueueService.FFprobePath,
                ).Probe(TranscodeAttemptId, FinalOutputPath, QueueId=Job.Id)
            except Exception as MeasureEx:
                LoggingService.LogException(f"PostEncodeMeasurement failed for attempt {TranscodeAttemptId}", MeasureEx, "JobProcessor", "Process")

            self._PersistPreEncodeMeta(TranscodeAttemptId, PreAudio)

            self.QueueService.UpdateTranscodeProgress(TranscodeAttemptId, "Finalizing", 0.0, "Finalizing...")
            OwnershipTransferred = True
            Strategy.HandleResult(Job, TranscodeResult, TranscodeAttemptId, ActiveJobId, FinalOutputPath, QueueService=self.QueueService)

            self.QueueService.CleanupOrContinue(Job)
            LoggingService.LogInfo(f"Completed {Mode} job processing for job ID: {Job.Id}", "JobProcessor", "Process")
            return JobResult(Success=True, AttemptId=TranscodeAttemptId, ErrorMessage=None)

        except Exception as Ex:
            LoggingService.LogException(f"Exception processing {Mode} job {Job.Id}", Ex, "JobProcessor", "Process")
            self.QueueService.HandleJobFailure(Job, f"Exception during {Mode}: {str(Ex)}", TranscodeAttemptId, ActiveJobId)
            return JobResult(Success=False, ErrorMessage=str(Ex))
        finally:
            self._CleanupPreEncodeScratch(locals().get('PreAudio'))
            if not OwnershipTransferred:
                if TargetLocalPath:
                    try:
                        self.QueueService._DeleteInProgressFile(TargetLocalPath)
                    except Exception:
                        pass
                if TemporaryFilePathId and TranscodeAttemptId:
                    try:
                        self.QueueService.DatabaseManager.DeleteTemporaryFilePath(TranscodeAttemptId)
                    except Exception:
                        pass

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def _RunPreEncodeAudio(self, Mode, InputPath, Job, TranscodeAttemptId):
        """One-source-of-truth Demucs pre-encode via AudioPreEncodeFacade. Fires for every ProcessingMode that ships audio."""
        if Mode not in _AUDIO_EMIT_MODES:
            return None
        def Reporter(Phase, Percent, Info):
            try:
                self.QueueService.UpdateTranscodeProgress(TranscodeAttemptId, Phase, Percent, Info)
            except Exception:
                pass
        return AudioPreEncodeFacade.Prepare(
            FfmpegPath=self.QueueService.FFmpegPath,
            InputPath=InputPath,
            JobId=getattr(Job, 'Id', 'unknown'),
            ProgressReporter=Reporter,
        )

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def _PersistPreEncodeMeta(self, TranscodeAttemptId, PreAudio):
        AudioPreEncodeFacade.PersistMeta(TranscodeAttemptId, PreAudio)

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def _CleanupPreEncodeScratch(self, PreAudio):
        AudioPreEncodeFacade.Cleanup(self.QueueService.FFmpegPath, PreAudio)
