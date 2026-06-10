# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C4

from Features.TranscodeJob.Adjustments.AdjustmentCalculator import AdjustmentCalculator
from Features.TranscodeJob.Adjustments.CrfAdjustmentCalculator import CrfAdjustmentCalculator


# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C4
class AdjustmentRegistry:
    """Strategy registry: RateControlMode -> AdjustmentCalculator. NVENC ('vbr') slot reserved for Phase 2."""

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C4
    def __init__(self):
        """Wire the default strategies; 'cq' active in Phase 1, 'vbr' raises KeyError until Phase 2."""
        self._Strategies = {
            'cq': CrfAdjustmentCalculator(),
        }

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C4
    def Get(self, RateControlMode: str) -> AdjustmentCalculator:
        """Return calculator for the given RateControlMode; raises KeyError if no strategy registered."""
        return self._Strategies[RateControlMode]
