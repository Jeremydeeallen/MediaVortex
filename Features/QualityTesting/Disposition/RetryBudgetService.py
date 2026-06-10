from typing import Optional


# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C7
class RetryBudgetService:
    """Decides if a MediaFile has retry budget remaining per PostTranscodeGateConfig.MaxRequeueAttempts (DB-fresh per call)."""

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C7
    def __init__(self, AttemptRepository, GateConfigRepository):
        """Inject the attempt + gate-config repositories (DIP)."""
        self.AttemptRepository = AttemptRepository
        self.GateConfigRepository = GateConfigRepository

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C7
    def HasBudgetRemaining(self, MediaFileId: int) -> bool:
        """True iff prior Requeue-eligible attempts (Success=True, VMAF<gate) < MaxRequeueAttempts."""
        GateConfig = self.GateConfigRepository.Get()
        MaxAttempts = int(GateConfig.MaxRequeueAttempts)
        MinThreshold = float(GateConfig.VmafAutoReplaceMinThreshold)
        FailedCount = self._CountFailedVmafAttempts(MediaFileId, MinThreshold)
        return FailedCount < MaxAttempts

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C7
    def _CountFailedVmafAttempts(self, MediaFileId: int, MinThreshold: float) -> int:
        """Return count of prior successful encodes whose VMAF fell below the gate threshold."""
        Attempts = self.AttemptRepository.GetTranscodeAttemptsByMediaFileId(MediaFileId) or []
        Count = 0
        for A in Attempts:
            Success = getattr(A, 'Success', None)
            if not Success:
                continue
            Vmaf = getattr(A, 'VMAF', None)
            if Vmaf is None:
                continue
            try:
                if float(Vmaf) < MinThreshold:
                    Count += 1
            except (TypeError, ValueError):
                continue
        return Count
