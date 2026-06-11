import os
import threading
from datetime import datetime, timezone
from Core.Logging.LoggingService import LoggingService
from Core.Path.LocalPath import LocalDirname
from Features.TranscodeJob.Worker.JobProcessor import JobProcessor
from Features.TranscodeJob.Worker.JobResult import JobResult


# directive: worker-loop-method-extraction | # see worker-loop.C5
class SubtitleFixJobProcessor(JobProcessor):
    """Self-contained JobProcessor strategy for ProcessingMode='SubtitleFix'; absorbs ProcessTranscodeQueueService.ProcessSubtitleFixJob orchestration."""

    # directive: worker-loop-method-extraction | # see worker-loop.C5
    def __init__(self, QueueService):
        """Inject the QueueService that retains shared helpers."""
        self.QueueService = QueueService

    # directive: worker-loop-method-extraction | # see worker-loop.C5
    def Process(self, Job, MediaFile=None) -> JobResult:
        """Run the SubtitleFix orchestration to terminal state; return JobResult."""
        try:
            self._ProcessImpl(Job)
            return JobResult(Success=True)
        except Exception as Ex:
            LoggingService.LogException(f"SubtitleFixJobProcessor.Process failed for job {getattr(Job, 'Id', None)}", Ex, "SubtitleFixJobProcessor", "Process")
            return JobResult(Success=False, ErrorMessage=str(Ex))

    # directive: worker-loop-method-extraction | # see worker-loop.C5
    def _ProcessImpl(self, Job):
        """Port of ProcessTranscodeQueueService.ProcessSubtitleFixJob with self.<X> rewritten to self.QueueService.<X>."""
        ActiveJobId = None
        TranscodeAttemptId = None
        try:
            LoggingService.LogInfo(f"Starting subtitle fix job processing for job ID: {Job.Id}", "SubtitleFixJobProcessor", "_ProcessImpl")

            ActiveJobId = self.QueueService.ActiveJobRepository.CreateActiveJob(
                ServiceName="TranscodeService",
                JobType="SubtitleFix",
                QueueId=Job.Id,
                ProcessId=os.getpid(),
                ThreadId=threading.get_ident(),
                WorkerName=self.QueueService.WorkerName
            )
            if ActiveJobId == 0:
                self.QueueService.HandleJobFailure(Job, "Failed to create active job record for subtitle fix", None, ActiveJobId)
                return

            self.QueueService.DatabaseManager.UpdateTranscodeQueueStatus(Job.Id, "Running")

            TranscodeAttemptId = self.QueueService.CreateTranscodeAttempt(Job, None, None, None)
            if not TranscodeAttemptId:
                self.QueueService.HandleJobFailure(Job, "Failed to create transcode attempt record for subtitle fix", None, ActiveJobId)
                return

            self.QueueService.UpdateTranscodeProgress(TranscodeAttemptId, "Initializing", 0.0, "Starting subtitle fix (ASS/SSA -> mov_text)...")

            MediaFile = self.QueueService.GetMediaFileData(Job)
            if not MediaFile:
                self.QueueService.HandleJobFailure(Job, "Failed to get media file data for subtitle fix", TranscodeAttemptId, ActiveJobId)
                return

            self.QueueService.UpdateTranscodeProgress(TranscodeAttemptId, "Preparing Files", 0.0, "Preparing source file...")
            self.QueueService._LastSetupError = None
            EffectiveInputPath = self.QueueService.SetupFilePreparation(Job, MediaFile, TranscodeAttemptId)
            if not EffectiveInputPath:
                Detail = self.QueueService._LastSetupError or "unknown"
                self.QueueService.HandleJobFailure(Job, f"Failed to setup file preparation for subtitle fix: {Detail}", TranscodeAttemptId, ActiveJobId)
                return

            self.QueueService.UpdateTranscodeProgress(TranscodeAttemptId, "Building Command", 0.0, "Building subtitle fix command...")
            _Spec = self.QueueService.EncodeShapeRegistry.Get(Job.ProcessingMode).Build(
                MediaFile, Job,
                Context={
                    'InputPath': EffectiveInputPath,
                    'FFmpegPath': self.QueueService.FFmpegPath,
                    'FFprobePath': self.QueueService.FFprobePath,
                    'OutputDirectory': LocalDirname(EffectiveInputPath),
                },
            )
            CommandResult = {'Command': _Spec.Command, 'OutputPath': _Spec.OutputPath} if _Spec else None
            if not CommandResult:
                self.QueueService.HandleJobFailure(Job, "Failed to build subtitle fix command", TranscodeAttemptId, ActiveJobId)
                return

            SubFixCommand = CommandResult['Command']
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
                'FfpmpegCommand': SubFixCommand,
                'ProfileName': 'SubtitleFix',
                'VMAF': None
            })

            self.QueueService.UpdateTranscodeProgress(TranscodeAttemptId, "Fixing Subtitles", 0.0, "Converting subtitles to mov_text...")
            TranscodeResult = self.QueueService.ExecuteTranscoding(Job, SubFixCommand, TranscodeAttemptId, MediaFile, ActiveJobId)
            if not TranscodeResult.get("Success", False):
                self.QueueService._DeleteInProgressFile(OutputPath)
                self.QueueService.HandleJobFailure(Job, f"Subtitle fix failed: {TranscodeResult.get('ErrorMessage', 'Unknown error')}", TranscodeAttemptId, ActiveJobId)
                return

            if not self.QueueService._VerifyInProgressFile(OutputPath):
                self.QueueService._DeleteInProgressFile(OutputPath)
                self.QueueService.HandleJobFailure(Job, f"Subtitle fix output failed FFprobe verification: {OutputPath}", TranscodeAttemptId, ActiveJobId)
                return

            self.QueueService.UpdateTranscodeProgress(TranscodeAttemptId, "Finalizing", 0.0, "Finalizing subtitle fix...")
            self.QueueService.HandleRemuxResult(Job, TranscodeResult, TranscodeAttemptId, ActiveJobId, OutputPath)
            self.QueueService.CleanupOrContinue(Job)

            LoggingService.LogInfo(f"Completed subtitle fix job processing for job ID: {Job.Id}", "SubtitleFixJobProcessor", "_ProcessImpl")

        except Exception as e:
            LoggingService.LogException(f"Exception processing subtitle fix job {Job.Id}", e, "SubtitleFixJobProcessor", "_ProcessImpl")
            self.QueueService.HandleJobFailure(Job, f"Exception during subtitle fix: {str(e)}", TranscodeAttemptId, ActiveJobId)
