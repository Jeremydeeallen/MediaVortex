import os
import threading
from datetime import datetime, timezone
from Core.Logging.LoggingService import LoggingService
from Core.Path import Path, Worker
from Core.Path.LocalPath import LocalBasename, LocalDirname, LocalExists, LocalJoin, LocalSplitExt
from Features.TranscodeJob.Emit.OutputFilenameBuilder import OutputFilenameBuilder
from Features.TranscodeJob.Worker.JobProcessor import JobProcessor
from Features.TranscodeJob.Worker.JobResult import JobResult


# directive: worker-loop-method-extraction | # see worker-loop.C5
class RemuxJobProcessor(JobProcessor):
    """Self-contained JobProcessor strategy for ProcessingMode IN ('Remux','Quick','AudioFix'); absorbs ProcessTranscodeQueueService.ProcessRemuxJob orchestration."""

    # directive: worker-loop-method-extraction | # see worker-loop.C5
    def __init__(self, QueueService):
        """Inject the QueueService that retains shared helpers."""
        self.QueueService = QueueService

    # directive: worker-loop-method-extraction | # see worker-loop.C5
    def Process(self, Job, MediaFile=None) -> JobResult:
        """Run the Remux orchestration to terminal state; return JobResult."""
        try:
            self._ProcessImpl(Job)
            return JobResult(Success=True)
        except Exception as Ex:
            LoggingService.LogException(f"RemuxJobProcessor.Process failed for job {getattr(Job, 'Id', None)}", Ex, "RemuxJobProcessor", "Process")
            return JobResult(Success=False, ErrorMessage=str(Ex))

    # directive: worker-loop-method-extraction | # see worker-loop.C5
    def _ProcessImpl(self, Job):
        """Port of ProcessTranscodeQueueService.ProcessRemuxJob with self.<X> rewritten to self.QueueService.<X>."""
        ActiveJobId = None
        TranscodeAttemptId = None
        TargetLocalPath = None
        TemporaryFilePathId = None
        OwnershipTransferred = False
        Mode = Job.ProcessingMode or 'Remux'
        Lower = Mode.lower()
        try:
            LoggingService.LogInfo(f"Starting {Lower} job processing for job ID: {Job.Id}", "RemuxJobProcessor", "_ProcessImpl")

            ActiveJobId = self.QueueService.ActiveJobRepository.CreateActiveJob(
                ServiceName="TranscodeService",
                JobType=Mode,
                QueueId=Job.Id,
                ProcessId=os.getpid(),
                ThreadId=threading.get_ident(),
                WorkerName=self.QueueService.WorkerName
            )
            if ActiveJobId == 0:
                self.QueueService.HandleJobFailure(Job, f"Failed to create active job record for {Lower}", None, ActiveJobId)
                return

            self.QueueService.DatabaseManager.UpdateTranscodeQueueStatus(Job.Id, "Running")

            MediaFile = self.QueueService.GetMediaFileData(Job)
            if not MediaFile:
                self.QueueService.HandleJobFailure(Job, f"Failed to get media file data for {Lower}", None, ActiveJobId)
                return

            LocalSourcePath = Path(Job.StorageRootId, Job.RelativePath).Resolve(Worker.Current(Db=self.QueueService.DatabaseManager.DatabaseService))
            if not LocalExists(LocalSourcePath):
                ErrMsg = f"Source file missing on disk: {LocalSourcePath}"
                LoggingService.LogWarning(ErrMsg, "RemuxJobProcessor", "_ProcessImpl")
                self.QueueService._MarkMediaFileSourceMissing(MediaFile.Id, ErrMsg)
                try:
                    self.QueueService.DatabaseManager.DeleteTranscodeQueueItem(Job.Id)
                except Exception as DelEx:
                    LoggingService.LogException("Failed to delete queue item for missing source", DelEx, "RemuxJobProcessor", "_ProcessImpl")
                if ActiveJobId:
                    try:
                        self.QueueService.ActiveJobRepository.DeleteActiveJob(ActiveJobId)
                    except Exception as DelEx:
                        LoggingService.LogException("Failed to delete active job for missing source", DelEx, "RemuxJobProcessor", "_ProcessImpl")
                return

            TranscodeAttemptId = self.QueueService.CreateTranscodeAttempt(Job, None, None, None)
            if not TranscodeAttemptId:
                self.QueueService.HandleJobFailure(Job, f"Failed to create transcode attempt record for {Lower}", None, ActiveJobId)
                return

            self.QueueService.UpdateTranscodeProgress(TranscodeAttemptId, "Initializing", 0.0, f"Starting {Lower}...")

            self.QueueService.UpdateTranscodeProgress(TranscodeAttemptId, "Preparing Files", 0.0, "Preparing source file...")
            self.QueueService._LastSetupError = None
            EffectiveInputPath = self.QueueService.SetupFilePreparation(Job, MediaFile, TranscodeAttemptId)
            if not EffectiveInputPath:
                Detail = self.QueueService._LastSetupError or "unknown"
                self.QueueService.HandleJobFailure(Job, f"Failed to setup file preparation for {Lower}: {Detail}", TranscodeAttemptId, ActiveJobId)
                return

            BaseName, _ = LocalSplitExt(LocalBasename(EffectiveInputPath))
            BaseName = OutputFilenameBuilder().CollapseMvSuffix(BaseName)
            TargetLocalPath = LocalJoin(LocalDirname(EffectiveInputPath), BaseName + '-mv.mp4.inprogress')

            self.QueueService.UpdateTranscodeProgress(TranscodeAttemptId, "Building Command", 0.0, f"Building {Lower} command...")
            _Spec = self.QueueService.EncodeShapeRegistry.Get(Job.ProcessingMode).Build(
                MediaFile, Job,
                Context={
                    'InputPath': EffectiveInputPath,
                    'OutputPath': TargetLocalPath,
                    'FFmpegPath': self.QueueService.FFmpegPath,
                    'FFprobePath': self.QueueService.FFprobePath,
                    'OutputDirectory': LocalDirname(EffectiveInputPath),
                },
            )
            CommandResult = {'Command': _Spec.Command, 'OutputPath': _Spec.OutputPath} if _Spec else None
            if not CommandResult:
                self.QueueService.HandleJobFailure(Job, f"Failed to build {Lower} command", TranscodeAttemptId, ActiveJobId)
                return

            RemuxCommand = CommandResult['Command']
            OutputPath = CommandResult['OutputPath']

            SrcId, SrcRel, OutId, OutRel = self.QueueService._ResolveTfpPathParts(Job, OutputPath)
            TemporaryFilePathId = self.QueueService.PrivateCreateTemporaryFilePathRecord(
                TranscodeAttemptId, SrcId, SrcRel, OutId, OutRel)

            self.QueueService.DatabaseManager.UpdateTranscodeAttempt(TranscodeAttemptId, {
                'FilePath': Job.FilePath,
                'AttemptDate': datetime.now(timezone.utc),
                'Quality': 0,
                'OldSizeBytes': Job.SizeBytes,
                'NewSizeBytes': 0,
                'Success': None,
                'FfpmpegCommand': RemuxCommand,
                'ProfileName': Mode,
                'VMAF': None
            })

            self.QueueService.UpdateTranscodeProgress(TranscodeAttemptId, Mode, 0.0, f"Running {Lower}...")
            TranscodeResult = self.QueueService.ExecuteTranscoding(Job, RemuxCommand, TranscodeAttemptId, MediaFile, ActiveJobId)
            if not TranscodeResult.get("Success", False):
                self.QueueService._DeleteInProgressFile(TargetLocalPath)
                self.QueueService.HandleJobFailure(Job, f"{Mode} failed: {TranscodeResult.get('ErrorMessage', 'Unknown error')}", TranscodeAttemptId, ActiveJobId)
                return

            if not self.QueueService._VerifyInProgressFile(TargetLocalPath):
                self.QueueService._DeleteInProgressFile(TargetLocalPath)
                self.QueueService.HandleJobFailure(Job, f"{Mode} output failed FFprobe verification: {TargetLocalPath}", TranscodeAttemptId, ActiveJobId)
                return

            self.QueueService.UpdateTranscodeProgress(TranscodeAttemptId, "Finalizing", 0.0, f"Finalizing {Lower}...")
            OwnershipTransferred = True
            self.QueueService.HandleRemuxResult(Job, TranscodeResult, TranscodeAttemptId, ActiveJobId, OutputPath)
            self.QueueService.CleanupOrContinue(Job)

            LoggingService.LogInfo(f"Completed {Lower} job processing for job ID: {Job.Id}", "RemuxJobProcessor", "_ProcessImpl")

        except Exception as e:
            LoggingService.LogException(f"Exception processing {Lower} job {Job.Id}", e, "RemuxJobProcessor", "_ProcessImpl")
            self.QueueService.HandleJobFailure(Job, f"Exception during {Lower}: {str(e)}", TranscodeAttemptId, ActiveJobId)
        finally:
            if not OwnershipTransferred:
                if TargetLocalPath:
                    try:
                        self.QueueService._DeleteInProgressFile(TargetLocalPath)
                    except Exception as CleanupEx:
                        LoggingService.LogException(f"Worker-owned .inprogress cleanup failed for {Lower} job {Job.Id}", CleanupEx, "RemuxJobProcessor", "_ProcessImpl")
                if TemporaryFilePathId and TranscodeAttemptId:
                    try:
                        self.QueueService.DatabaseManager.DeleteTemporaryFilePath(TranscodeAttemptId)
                    except Exception as TfpEx:
                        LoggingService.LogException(f"Worker-owned TFP cleanup failed for {Lower} job {Job.Id}", TfpEx, "RemuxJobProcessor", "_ProcessImpl")
