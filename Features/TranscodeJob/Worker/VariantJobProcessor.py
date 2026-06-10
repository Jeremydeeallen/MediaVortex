from Core.Logging.LoggingService import LoggingService
from Features.TranscodeJob.Worker.JobProcessor import JobProcessor
from Features.TranscodeJob.Worker.JobResult import JobResult


# directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C6
class VariantJobProcessor(JobProcessor):
    """JobProcessor strategy for test-variant jobs (Job.IsTestMode=True); delegates to ProcessTranscodeQueueService.ProcessTestVariantJob."""

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C6
    def __init__(self, QueueService):
        """Inject the existing ProcessTranscodeQueueService."""
        self.QueueService = QueueService

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C6
    def Process(self, Job, MediaFile=None) -> JobResult:
        """Delegate to QueueService.ProcessTestVariantJob."""
        try:
            self.QueueService.ProcessTestVariantJob(Job)
            return JobResult(Success=True, AttemptId=None)
        except Exception as Ex:
            LoggingService.LogException(f"VariantJobProcessor.Process failed for job {getattr(Job, 'Id', None)}", Ex, "VariantJobProcessor", "Process")
            return JobResult(Success=False, ErrorMessage=str(Ex))
