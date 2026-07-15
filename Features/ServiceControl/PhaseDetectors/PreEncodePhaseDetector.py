from datetime import datetime, timezone

from Core.DateTimeHelpers import AsAwareUtc
from Core.Logging.LoggingService import LoggingService


DEFAULT_TIMEOUT_MIN = 20


# directive: transcode-flow-canonical -- PreEncode covers Demucs subprocess pipeline; no ffmpeg frame counter yet, only phase-age + subprocess-liveness signals.
class PreEncodePhaseDetector:
    """PreEncode phase: Demucs pipeline (downmix/isolate/premix/measure). Timeout via SystemSettings.PreEncodePhaseTimeoutMin (default 20)."""

    def __init__(self, SystemSettingsRepositoryFactory=None):
        self._SystemSettingsRepositoryFactory = SystemSettingsRepositoryFactory

    def Detect(self, Job, ActiveJob, PhaseTransitionedAt) -> "tuple[bool, str]":
        if PhaseTransitionedAt is None:
            return False, "Phase transition timestamp missing"
        MinutesInPhase = (datetime.now(timezone.utc) - AsAwareUtc(PhaseTransitionedAt)).total_seconds() / 60.0
        Threshold = self._ReadThreshold()
        if MinutesInPhase >= Threshold:
            return True, (
                f"PreEncode phase stuck: elapsed {MinutesInPhase:.1f} min in Demucs pipeline "
                f"(threshold: {Threshold}min)"
            )
        return False, f"PreEncode in-progress ({MinutesInPhase:.1f} min elapsed)"

    def _ReadThreshold(self) -> int:
        try:
            if self._SystemSettingsRepositoryFactory is None:
                from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
                Repo = SystemSettingsRepository()
            else:
                Repo = self._SystemSettingsRepositoryFactory()
            Value = Repo.GetSystemSetting('PreEncodePhaseTimeoutMin')
            if Value is None:
                return DEFAULT_TIMEOUT_MIN
            return max(1, int(Value))
        # fail-loud-ok: threshold read swallow keeps monitoring loop alive; default preserves detection
        except Exception as Ex:
            LoggingService.LogException(
                "PreEncodePhaseDetector threshold read failed; using default",
                Ex, "PreEncodePhaseDetector", "_ReadThreshold",
            )
            return DEFAULT_TIMEOUT_MIN
