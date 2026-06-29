from typing import Tuple, Optional, Dict, Any
from Core.Logging.LoggingService import LoggingService


# directive: transcode-worker-unification | # see disposition.W5
class RetranscodeDecider:
    """Decides whether to re-transcode based on the prior attempt's VMAF outcome."""

    # directive: transcode-worker-unification | # see disposition.W5
    def __init__(self, AttemptRepository, GateConfigRepository=None):
        """Stash the injected attempt repository and optional gate-config repo (DIP)."""
        self.AttemptRepository = AttemptRepository
        self.GateConfigRepository = GateConfigRepository

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C6
    def Decide(self, MediaFileId: int) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Decide (ShouldRetranscode, PreviousAttempt) using MediaFileId only by construction."""
        try:
            PreviousAttempt = self.AttemptRepository.GetLatestTranscodeAttemptWithVMAF(MediaFileId)

            if not PreviousAttempt:
                LoggingService.LogDebug(
                    f"No previous attempt for MediaFileId={MediaFileId}, should transcode",
                    "RetranscodeDecider", "Decide",
                )
                return True, None

            IsPreferred = PreviousAttempt.get('PreferredAttempt', False)
            if IsPreferred:
                LoggingService.LogInfo(
                    f"Previous attempt for MediaFileId={MediaFileId} is preferred, skipping",
                    "RetranscodeDecider", "Decide",
                )
                return False, PreviousAttempt

            Vmaf = PreviousAttempt.get('VMAF')
            if Vmaf is None:
                LoggingService.LogDebug(
                    f"Previous attempt for MediaFileId={MediaFileId} has no VMAF, should transcode",
                    "RetranscodeDecider", "Decide",
                )
                return True, PreviousAttempt

            VmafThreshold = (self.GateConfigRepository.Get().RetranscodeVmafThreshold
                             if self.GateConfigRepository else 80)
            if Vmaf >= VmafThreshold:
                LoggingService.LogInfo(
                    f"VMAF {Vmaf:.2f} >= {VmafThreshold}, skipping",
                    "RetranscodeDecider", "Decide",
                )
                return False, PreviousAttempt

            LoggingService.LogDebug(
                f"VMAF {Vmaf:.2f} below threshold, should retranscode",
                "RetranscodeDecider", "Decide",
            )
            return True, PreviousAttempt

        except Exception as Ex:
            LoggingService.LogException(
                f"Decide failed for MediaFileId={MediaFileId}",
                Ex, "RetranscodeDecider", "Decide",
            )
            return True, None
