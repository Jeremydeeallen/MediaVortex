# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C4

from abc import ABC, abstractmethod
from typing import Dict, Any
from Features.TranscodeJob.Adjustments.KnobOverrides import KnobOverrides


# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C4
class AdjustmentCalculator(ABC):
    """Strategy: compute knob overrides for the next transcode attempt given prior VMAF gap."""

    @abstractmethod
    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C4
    def Calculate(self, PreviousAttempt: Dict[str, Any], ProfileSettings: Dict[str, Any], GateThreshold: float) -> KnobOverrides:
        """Return KnobOverrides for the next attempt based on prior attempt + profile + gate threshold."""
        raise NotImplementedError
