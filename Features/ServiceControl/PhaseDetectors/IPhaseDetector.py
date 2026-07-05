from typing import Protocol


# directive: transcode-flow-canonical
class IPhaseDetector(Protocol):
    """Contract for phase-specific stuck-detection strategy."""

    # directive: transcode-flow-canonical
    def Detect(self, Job, ActiveJob, PhaseTransitionedAt) -> "tuple[bool, str]":
        """Return (IsStuck, Reason) for a job in the detector's owned phase."""
        ...
