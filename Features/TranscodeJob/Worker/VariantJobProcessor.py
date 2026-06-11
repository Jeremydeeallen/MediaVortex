import os
import threading
from Core.Logging.LoggingService import LoggingService
from Core.Path import Path, Worker
from Core.Path.LocalPath import LocalExists
from Features.TranscodeJob.Worker.JobProcessor import JobProcessor
from Features.TranscodeJob.Worker.JobResult import JobResult


# directive: worker-loop-method-extraction | # see worker-loop.C5
class VariantJobProcessor(JobProcessor):
    """Self-contained JobProcessor strategy for test-variant jobs (Job.IsTestMode=True); absorbs ProcessTranscodeQueueService.ProcessTestVariantJob orchestration."""

    # directive: worker-loop-method-extraction | # see worker-loop.C5
    def __init__(self, QueueService):
        """Inject the QueueService that retains shared variant helpers (_ProcessSingleVariant, _CleanupTestQueueRow)."""
        self.QueueService = QueueService

    # directive: worker-loop-method-extraction | # see worker-loop.C5
    def Process(self, Job, MediaFile=None) -> JobResult:
        """Run the TestVariant orchestration to terminal state; return JobResult."""
        try:
            self._ProcessImpl(Job)
            return JobResult(Success=True)
        except Exception as Ex:
            LoggingService.LogException(f"VariantJobProcessor.Process failed for job {getattr(Job, 'Id', None)}", Ex, "VariantJobProcessor", "Process")
            return JobResult(Success=False, ErrorMessage=str(Ex))

    # directive: worker-loop-method-extraction | # see worker-loop.C5
    def _ProcessImpl(self, Job):
        """Port of ProcessTranscodeQueueService.ProcessTestVariantJob with self.<X> rewritten to self.QueueService.<X>."""
        ActiveJobId = None
        try:
            LoggingService.LogInfo(
                f"Starting test-variant job processing for queue ID: {Job.Id} (variant set {Job.TestVariantSetId})",
                "VariantJobProcessor", "_ProcessImpl",
            )

            VariantSet = self.QueueService.TranscodeQueueRepository.GetTestVariantSet(Job.TestVariantSetId)
            if not VariantSet or not VariantSet.get('Variants'):
                self.QueueService.HandleJobFailure(Job, f"TestVariantSet {Job.TestVariantSetId} not found or empty", None, None)
                return
            Variants = VariantSet['Variants']
            LoggingService.LogInfo(
                f"Test set {VariantSet.get('Name')!r} has {len(Variants)} variants",
                "VariantJobProcessor", "_ProcessImpl",
            )

            ActiveJobId = self.QueueService.ActiveJobRepository.CreateActiveJob(
                ServiceName="TranscodeService",
                JobType="TestVariant",
                QueueId=Job.Id,
                ProcessId=os.getpid(),
                ThreadId=threading.get_ident(),
                WorkerName=self.QueueService.WorkerName,
            )
            if ActiveJobId == 0:
                self.QueueService.HandleJobFailure(Job, "Failed to create active job (test mode)", None, None)
                return

            self.QueueService.DatabaseManager.UpdateTranscodeQueueStatus(Job.Id, "Running")

            MediaFile = self.QueueService.GetMediaFileData(Job)
            if not MediaFile:
                self.QueueService.HandleJobFailure(Job, "Failed to get media file data (test mode)", None, ActiveJobId)
                return

            LocalSourcePath = Path(MediaFile.StorageRootId, MediaFile.RelativePath).Resolve(Worker.Current(Db=self.QueueService.DatabaseManager.DatabaseService))
            if not LocalExists(LocalSourcePath):
                ErrMsg = f"Source file missing on disk: {LocalSourcePath}"
                LoggingService.LogWarning(ErrMsg, "VariantJobProcessor", "_ProcessImpl")
                self.QueueService._MarkMediaFileSourceMissing(MediaFile.Id, ErrMsg)
                self.QueueService._CleanupTestQueueRow(Job, ActiveJobId)
                return

            SuccessCount = 0
            FailureCount = 0
            for V in Variants:
                Name = V.get('Name', '?')
                Label = V.get('Label', Name)
                LoggingService.LogInfo(
                    f"  Variant {Name}: {Label} (CRF={V.get('Crf')}, FG={V.get('FilmGrain')})",
                    "VariantJobProcessor", "_ProcessImpl",
                )
                try:
                    AttemptId = self.QueueService._ProcessSingleVariant(Job, MediaFile, V, ActiveJobId)
                    if AttemptId:
                        SuccessCount += 1
                    else:
                        FailureCount += 1
                except Exception as VEx:
                    FailureCount += 1
                    LoggingService.LogException(
                        f"Variant {Name} threw exception",
                        VEx, "VariantJobProcessor", "_ProcessImpl",
                    )

            LoggingService.LogInfo(
                f"Test variant job {Job.Id} complete: {SuccessCount} succeeded, {FailureCount} failed ({len(Variants)} variants total)",
                "VariantJobProcessor", "_ProcessImpl",
            )

            self.QueueService._CleanupTestQueueRow(Job, ActiveJobId)

        except Exception as e:
            LoggingService.LogException(
                f"Exception processing test variant job {Job.Id}",
                e, "VariantJobProcessor", "_ProcessImpl",
            )
            self.QueueService.HandleJobFailure(Job, f"Exception during test variant processing: {str(e)}", None, ActiveJobId)
