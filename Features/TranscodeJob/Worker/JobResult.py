from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
# directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C1
class JobResult:
    """Frozen value object: outcome of one JobProcessor.Process call."""
    Success: bool
    AttemptId: Optional[int] = None
    ErrorMessage: Optional[str] = None
