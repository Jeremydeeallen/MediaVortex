from Core.Logging.LoggingService import LoggingService
from Features.TranscodeJob.Worker.JobProcessor import JobProcessor
from Features.TranscodeJob.Worker.JobResult import JobResult


# directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C3
class TranscodeJobProcessor(JobProcessor):
    """JobProcessor strategy for ProcessingMode='Transcode'; delegates to the retained ProcessTranscodeQueueService.ProcessJob method until full extraction lands."""

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C3
    def __init__(self, QueueService):
        """Inject the existing ProcessTranscodeQueueService instance that holds the orchestration methods."""
        self.QueueService = QueueService

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C3
    def Process(self, Job, MediaFile=None) -> JobResult:
        """Delegate to QueueService.ProcessJob; return JobResult capturing the outcome."""
        try:
            self.QueueService.ProcessJob(Job)
            return JobResult(Success=True, AttemptId=None)
        except Exception as Ex:
            LoggingService.LogException(f"TranscodeJobProcessor.Process failed for job {getattr(Job, 'Id', None)}", Ex, "TranscodeJobProcessor", "Process")
            return JobResult(Success=False, ErrorMessage=str(Ex))
