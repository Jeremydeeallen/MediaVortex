from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C3
class KnobOverrides:
    """Frozen value object: ffmpeg knob overrides for the next attempt."""
    CRF: Optional[int] = None
    BitrateKbps: Optional[int] = None
    MaxrateKbps: Optional[int] = None
