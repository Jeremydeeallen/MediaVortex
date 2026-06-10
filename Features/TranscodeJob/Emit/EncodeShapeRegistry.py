# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C15
from typing import Dict
from Features.TranscodeJob.Emit.EncodeShape import EncodeShape


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C15
class EncodeShapeRegistry:
    """Composition-root registry: ProcessingMode -> EncodeShape strategy. Phase 3 lifts to WorkerCompositionRoot."""

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C15
    def __init__(self, Strategies: Dict[str, EncodeShape]):
        """Wire injected strategies keyed by ProcessingMode ('Transcode', 'Remux', 'SubtitleFix')."""
        self._Strategies = Strategies

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C15
    def Get(self, ProcessingMode: str) -> EncodeShape:
        """Return the strategy for the given ProcessingMode; raises KeyError for unknown."""
        return self._Strategies[ProcessingMode]
