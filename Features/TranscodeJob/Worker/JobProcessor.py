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
from Features.TranscodeJob.Emit.Plan import PlanFactory
from Features.TranscodeJob.Worker.JobResult import JobResult
from Features.TranscodeJob.Worker import PartialCompletion

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

            self.QueueService.DatabaseManager.SetJobPhase(ActiveJobId, JobPhase.PreEncode)
            PreAudio = self._RunPreEncodeAudio(MediaFile, EffectiveInputPath, Job, TranscodeAttemptId)
            AudioPreEncodeFacade.PersistSourceLoudness(MediaFile.Id, MediaFile, PreAudio)
            self.QueueService.UpdateTranscodeProgress(TranscodeAttemptId, "Building Command", 0.0, f"Building {Mode} command...")
            # directive: ffmpeg-stderr-deadlock -- FfmpegLogLevel is required by CommandComposer for every ProcessingMode (Remux/Quick/AudioFix/SubtitleFix); read fresh per invocation.
            FfmpegLogLevel = self.QueueService.SystemSettingsRepository.GetSystemSetting('FfmpegLogLevel')
            if FfmpegLogLevel is None:
                raise ValueError("FfmpegLogLevel setting missing from SystemSettings. Run Scripts/SQLScripts/AddFfmpegLogLevelSetting_2026_08_05.py")
            CommandResult = Strategy.BuildCommand(
                Job, MediaFile,
                Context={
                    'QueueService': self.QueueService,
                    'InputPath': EffectiveInputPath,
                    'OutputPath': TargetLocalPath,
                    'FFmpegPath': self.QueueService.FFmpegPath,
                    'FFprobePath': self.QueueService.FFprobePath,
                    'FfmpegLogLevel': FfmpegLogLevel,
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

            # directive: e2e-bug-fixes | # see e2e-bug-fixes.C32 -- AttemptDate is immutable after CreateTranscodeAttempt; only FfpmpegCommand is new information here (built post-BuildCommand). Every other field is already set at INSERT.
            self.QueueService.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                'FfpmpegCommand': CommandResult.Command,
            })

            self.QueueService.UpdateTranscodeProgress(TranscodeAttemptId, Mode, 0.0, f"Running {Mode}...")
            TranscodeResult = self.QueueService.ExecuteTranscoding(
                Job, CommandResult.Command, TranscodeAttemptId, MediaFile, ActiveJobId
            )
            CopiedSlot = None
            if not TranscodeResult.get("Success", False):
                # directive: partial-pipeline-completion | # see transcode.D13
                FallbackOutcome = self._TryPartialFallback(
                    Job, MediaFile, Strategy, TranscodeAttemptId, ActiveJobId,
                    CommandResult, TranscodeResult, PreAudio,
                )
                if FallbackOutcome is None:
                    self.QueueService._DeleteInProgressFile(CommandResult.OutputPath)
                    self.QueueService.HandleJobFailure(Job, f"{Mode} failed: {TranscodeResult.get('ErrorMessage', 'Unknown error')}", TranscodeAttemptId, ActiveJobId)
                    return JobResult(Success=False, ErrorMessage="FFmpeg exec failed")
                CommandResult, TranscodeResult, CopiedSlot = FallbackOutcome

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
            if CopiedSlot is not None:
                # directive: partial-pipeline-completion | # see transcode.D13
                self._PreCommitPartialDisposition(TranscodeAttemptId, CopiedSlot)
                self._EnqueuePartialFollowup(Job, MediaFile, TranscodeAttemptId, CopiedSlot)
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

    # directive: plan-factory-driven-by-compliance-flags | # see transcode.D2 -- gate is compliance-driven (AudioSlot decides Reencode vs Copy from AudioCompliant); Demucs skipped for audiocompliant files
    def _RunPreEncodeAudio(self, MediaFile, InputPath, Job, TranscodeAttemptId):
        """Demucs pre-encode via AudioPreEncodeFacade; skipped when AudioSlot will Copy (audiocompliant=TRUE)."""
        if getattr(MediaFile, 'AudioCompliant', None) is True:
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

    # directive: partial-pipeline-completion | # see transcode.D13
    def _TryPartialFallback(self, Job, MediaFile, Strategy, TranscodeAttemptId, ActiveJobId,
                            OriginalCommandResult, OriginalTranscodeResult, PreAudio):
        """Attempt up to two ordered fallbacks (audio-copy / video-copy). Return (CommandResult, TranscodeResult, CopiedSlot) on success, None on both-fallbacks-fail or when disabled."""
        if getattr(Job, 'ParentTranscodeAttemptId', None) is not None:
            PartialCompletion.LogPartialRetryExhausted(
                MediaFile.Id, Job.ParentTranscodeAttemptId,
                OriginalTranscodeResult.get('ErrorMessage', ''),
            )
            self.QueueService.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                'Disposition': 'Reject',
                'DispositionReason': 'PartialRetryExhausted',
                'DispositionDecidedAt': datetime.now(timezone.utc),
            })
            return None

        OriginalStderr = OriginalTranscodeResult.get('ErrorMessage', '') or ''
        FirstSide = PartialCompletion.SniffFirstFallback(OriginalStderr)
        PartialCompletion.LogSniff(MediaFile.Id, OriginalStderr, FirstSide)
        SecondSide = PartialCompletion.OppositeSlot(FirstSide)

        OriginalPlan = PlanFactory().FromComplianceState(MediaFile)
        Attempt1Stderr = None
        for AttemptNumber, Side in enumerate((FirstSide, SecondSide), start=1):
            self.QueueService._DeleteInProgressFile(OriginalCommandResult.OutputPath)
            PartialCompletion.LogFallbackAttempt(MediaFile.Id, AttemptNumber, Side)
            FallbackPlan = OriginalPlan.WithSlotForcedToCopy(Side)
            FallbackCommand = self._BuildFallbackCommand(Job, MediaFile, Strategy, TranscodeAttemptId, PreAudio, FallbackPlan)
            if FallbackCommand is None:
                Attempt1Stderr = "BuildCommand returned None on fallback"
                continue
            FallbackResult = self.QueueService.ExecuteTranscoding(
                Job, FallbackCommand.Command, TranscodeAttemptId, MediaFile, ActiveJobId
            )
            if FallbackResult.get('Success', False) and self.QueueService._VerifyInProgressFile(FallbackCommand.OutputPath):
                PartialCompletion.LogFallbackSuccess(MediaFile.Id, AttemptNumber, Side)
                return (FallbackCommand, FallbackResult, Side)
            if AttemptNumber == 1:
                Attempt1Stderr = FallbackResult.get('ErrorMessage', '')

        PartialCompletion.LogBothFallbacksFailed(
            MediaFile.Id, OriginalStderr, Attempt1Stderr or '',
            FallbackResult.get('ErrorMessage', '') if 'FallbackResult' in locals() else '',
        )
        return None

    # directive: partial-pipeline-completion | # see transcode.D13
    def _BuildFallbackCommand(self, Job, MediaFile, Strategy, TranscodeAttemptId, PreAudio, FallbackPlan):
        """Re-invoke BuildCommand with PlanOverride injected."""
        LocalSourcePath = Path(Job.StorageRootId, Job.RelativePath).Resolve(Worker.Current(Db=self.QueueService.DatabaseManager.DatabaseService))
        BaseName, _ = LocalSplitExt(LocalBasename(LocalSourcePath))
        BaseName = OutputFilenameBuilder().CollapseMvSuffix(BaseName)
        TargetLocalPath = LocalJoin(LocalDirname(LocalSourcePath), BaseName + '-mv.mp4.inprogress')
        FfmpegLogLevel = self.QueueService.SystemSettingsRepository.GetSystemSetting('FfmpegLogLevel') or 'error'
        return Strategy.BuildCommand(
            Job, MediaFile,
            Context={
                'QueueService': self.QueueService,
                'InputPath': LocalSourcePath,
                'OutputPath': TargetLocalPath,
                'FFmpegPath': self.QueueService.FFmpegPath,
                'FFprobePath': self.QueueService.FFprobePath,
                'FfmpegLogLevel': FfmpegLogLevel,
                'OutputDirectory': LocalDirname(LocalSourcePath),
                'TranscodeAttemptId': TranscodeAttemptId,
                'DemucsPremixPath': (PreAudio or {}).get('DemucsPremixPath'),
                'VocalsRmsDbfs': (PreAudio or {}).get('VocalsRmsDbfs'),
                'PremixMeasuredI': (PreAudio or {}).get('PremixMeasuredI'),
                'PremixMeasuredLra': (PreAudio or {}).get('PremixMeasuredLra'),
                'PremixMeasuredTp': (PreAudio or {}).get('PremixMeasuredTp'),
                'PremixMeasuredThresh': (PreAudio or {}).get('PremixMeasuredThresh'),
                'PlanOverride': FallbackPlan,
            },
        )

    # directive: partial-pipeline-completion | # see transcode.D13
    def _PreCommitPartialDisposition(self, TranscodeAttemptId, CopiedSlot):
        """Write partial-success DispositionReason so DispositionDispatcher's cached-check honors it."""
        Reason = PartialCompletion.DispositionReasonForCopiedSlot(CopiedSlot)
        self.QueueService.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
            'Disposition': 'Replace',
            'DispositionReason': Reason,
            'DispositionDecidedAt': datetime.now(timezone.utc),
        })

    # directive: partial-pipeline-completion | # see transcode.D13
    def _EnqueuePartialFollowup(self, Job, MediaFile, ParentAttemptId, CopiedSlot):
        """Enqueue the retry job for the slot that had to be copied."""
        from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
        FollowupPlan = PartialCompletion.FollowupPlanForCopiedSlot(CopiedSlot)
        QueueManagementBusinessService().EnqueuePartialCompletionFollowup(
            MediaFileId=MediaFile.Id,
            ProcessingMode=FollowupPlan['ProcessingMode'],
            AudioSlotOverride=FollowupPlan['AudioSlotOverride'],
            ParentTranscodeAttemptId=ParentAttemptId,
        )
