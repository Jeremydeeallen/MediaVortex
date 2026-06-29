import os
import threading
from datetime import datetime, timezone
from Core.Logging.LoggingService import LoggingService
from Core.Path import Path, Worker
from Core.Path.LocalPath import LocalBasename, LocalDirname, LocalExists, LocalJoin, LocalSplitExt
from Features.TranscodeJob.Emit.OutputFilenameBuilder import OutputFilenameBuilder
from Features.TranscodeJob.Worker.JobResult import JobResult


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
                },
            )
            if not CommandResult:
                self.QueueService.HandleJobFailure(Job, f"Failed to build {Mode} command", TranscodeAttemptId, ActiveJobId)
                return JobResult(Success=False, ErrorMessage="Command build failed")

            SrcId, SrcRel, OutId, OutRel = self.QueueService._ResolveTfpPathParts(Job, CommandResult.OutputPath)
            TemporaryFilePathId = self.QueueService.PrivateCreateTemporaryFilePathRecord(
                TranscodeAttemptId, SrcId, SrcRel, OutId, OutRel)

            ProfileName = Job.AssignedProfile if Mode == 'Transcode' and hasattr(Job, 'AssignedProfile') else Mode
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

            # PostEncode measurement runs for every mode (non-fatal)
            try:
                from Features.AudioNormalization.Services.PostEncodeMeasurementService import PostEncodeMeasurementService
                PostEncodeMeasurementService().Measure(CommandResult.OutputPath, TranscodeAttemptId)
            except Exception as MeasureEx:
                LoggingService.LogException(f"PostEncodeMeasurement failed for attempt {TranscodeAttemptId}", MeasureEx, "JobProcessor", "Process")

            self.QueueService.UpdateTranscodeProgress(TranscodeAttemptId, "Finalizing", 0.0, "Finalizing...")
            OwnershipTransferred = True
            Strategy.HandleResult(Job, TranscodeResult, TranscodeAttemptId, ActiveJobId, CommandResult.OutputPath, QueueService=self.QueueService)

            self.QueueService.CleanupOrContinue(Job)
            LoggingService.LogInfo(f"Completed {Mode} job processing for job ID: {Job.Id}", "JobProcessor", "Process")
            return JobResult(Success=True, AttemptId=TranscodeAttemptId, ErrorMessage=None)

        except Exception as Ex:
            LoggingService.LogException(f"Exception processing {Mode} job {Job.Id}", Ex, "JobProcessor", "Process")
            self.QueueService.HandleJobFailure(Job, f"Exception during {Mode}: {str(Ex)}", TranscodeAttemptId, ActiveJobId)
            return JobResult(Success=False, ErrorMessage=str(Ex))
        finally:
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
