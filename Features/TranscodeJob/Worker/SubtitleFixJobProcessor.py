from Core.Logging.LoggingService import LoggingService
from Features.TranscodeJob.Worker.JobProcessor import JobProcessor
from Features.TranscodeJob.Worker.JobResult import JobResult


# directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C5
class SubtitleFixJobProcessor(JobProcessor):
    """JobProcessor strategy for ProcessingMode='SubtitleFix'; delegates to ProcessTranscodeQueueService.ProcessSubtitleFixJob."""

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C5
    def __init__(self, QueueService):
        """Inject the existing ProcessTranscodeQueueService."""
        self.QueueService = QueueService

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C5
    def Process(self, Job, MediaFile=None) -> JobResult:
        """Delegate to QueueService.ProcessSubtitleFixJob."""
        try:
            self.QueueService.ProcessSubtitleFixJob(Job)
            return JobResult(Success=True, AttemptId=None)
        except Exception as Ex:
            LoggingService.LogException(f"SubtitleFixJobProcessor.Process failed for job {getattr(Job, 'Id', None)}", Ex, "SubtitleFixJobProcessor", "Process")
            return JobResult(Success=False, ErrorMessage=str(Ex))
