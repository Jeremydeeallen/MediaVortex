from dataclasses import dataclass
from typing import Optional, Any

@dataclass(frozen=True)
# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C2
class Disposition:
    """Frozen value object: outcome of a post-transcode disposition decision."""
    Action: str
    Reason: str
    NextRegime: Optional[str] = None
    NextKnob: Optional[Any] = None
