from typing import Dict
from Features.TranscodeJob.Worker.JobProcessor import JobProcessor


# directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C7
class JobProcessorRegistry:
    """Composition-root registry: ProcessingMode -> JobProcessor strategy."""

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C7
    def __init__(self, Strategies: Dict[str, JobProcessor]):
        """Wire injected strategies keyed by ProcessingMode."""
        self._Strategies = Strategies

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C7
    def Get(self, ProcessingMode: str) -> JobProcessor:
        """Return the strategy for the given ProcessingMode; KeyError if unknown."""
        return self._Strategies[ProcessingMode]
