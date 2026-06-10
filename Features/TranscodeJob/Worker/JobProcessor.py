from abc import ABC, abstractmethod
from Features.TranscodeJob.Worker.JobResult import JobResult


# directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C2
class JobProcessor(ABC):
    """Strategy: take a claimed Job (and pre-resolved MediaFile) and run it to terminal state."""

    @abstractmethod
    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C2
    def Process(self, Job, MediaFile) -> JobResult:
        """Execute the job; return JobResult capturing success + attempt id."""
        raise NotImplementedError
