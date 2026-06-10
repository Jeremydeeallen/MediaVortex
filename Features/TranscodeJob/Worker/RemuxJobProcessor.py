from Core.Logging.LoggingService import LoggingService
from Features.TranscodeJob.Worker.JobProcessor import JobProcessor
from Features.TranscodeJob.Worker.JobResult import JobResult


# directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C4
class RemuxJobProcessor(JobProcessor):
    """JobProcessor strategy for ProcessingMode IN ('Remux', 'Quick', 'AudioFix'); replaces ProcessRemuxQueueService entirely (closes BUG-0051 -- duplicate composition root deleted)."""

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C4
    def __init__(self, QueueService):
        """Inject the existing ProcessTranscodeQueueService that holds the ProcessRemuxJob method."""
        self.QueueService = QueueService

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C4
    def Process(self, Job, MediaFile=None) -> JobResult:
        """Delegate to QueueService.ProcessRemuxJob; no separate composition root means no AttributeError surface."""
        try:
            self.QueueService.ProcessRemuxJob(Job)
            return JobResult(Success=True, AttemptId=None)
        except Exception as Ex:
            LoggingService.LogException(f"RemuxJobProcessor.Process failed for job {getattr(Job, 'Id', None)}", Ex, "RemuxJobProcessor", "Process")
            return JobResult(Success=False, ErrorMessage=str(Ex))
