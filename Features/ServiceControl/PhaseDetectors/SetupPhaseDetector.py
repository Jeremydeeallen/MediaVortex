from datetime import datetime, timezone

from Core.DateTimeHelpers import AsAwareUtc
from Core.Logging.LoggingService import LoggingService


DEFAULT_TIMEOUT_MIN = 30


# directive: transcode-flow-canonical
class SetupPhaseDetector:
    """Setup phase: path resolve + audio pre-pass (demucs). Timeout much longer than encoding-phase (default 30 min)."""

    # directive: transcode-flow-canonical
    def __init__(self, SystemSettingsRepositoryFactory=None):
        self._SystemSettingsRepositoryFactory = SystemSettingsRepositoryFactory

    # directive: transcode-flow-canonical
    def Detect(self, Job, ActiveJob, PhaseTransitionedAt) -> "tuple[bool, str]":
        if PhaseTransitionedAt is None:
            return False, "Phase transition timestamp missing"
        MinutesInPhase = (datetime.now(timezone.utc) - AsAwareUtc(PhaseTransitionedAt)).total_seconds() / 60.0
        Threshold = self._ReadThreshold()
        if MinutesInPhase >= Threshold:
            return True, (
                f"Setup phase stuck: elapsed {MinutesInPhase:.1f} min in Setup "
                f"(threshold: {Threshold}min)"
            )
        return False, f"Setup in-progress ({MinutesInPhase:.1f} min elapsed)"

    # directive: transcode-flow-canonical
    def _ReadThreshold(self) -> int:
        try:
            if self._SystemSettingsRepositoryFactory is None:
                from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
                Repo = SystemSettingsRepository()
            else:
                Repo = self._SystemSettingsRepositoryFactory()
            Value = Repo.GetSystemSetting('SetupPhaseTimeoutMin')
            if Value is None:
                return DEFAULT_TIMEOUT_MIN
            return max(1, int(Value))
        # fail-loud-ok: threshold read swallow keeps monitoring loop alive; default preserves detection
        except Exception as Ex:
            LoggingService.LogException(
                "SetupPhaseDetector threshold read failed; using default",
                Ex, "SetupPhaseDetector", "_ReadThreshold",
            )
            return DEFAULT_TIMEOUT_MIN
