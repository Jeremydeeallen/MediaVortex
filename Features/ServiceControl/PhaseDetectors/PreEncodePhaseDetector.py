from datetime import datetime, timezone

from Core.DateTimeHelpers import AsAwareUtc
from Core.Logging.LoggingService import LoggingService


DEFAULT_FROZEN_THRESHOLD_MIN = 5


# directive: preencode-detector-progress-based-not-wallclock | # see stuck-job-detection.C3 -- PreEncode Demucs pipeline ticks TranscodeProgress.LastProgressUpdate per substep (SourceMeasure/Downmix/Demucs/Premix/LoudnormMeasure); detector reads that signal, mirroring EncodingPhaseDetector's frame-advance shape.
class PreEncodePhaseDetector:
    """PreEncode phase: Demucs pipeline. Liveness = TranscodeProgress.LastProgressUpdate staleness, NOT elapsed wall-clock time. Same signal shape as EncodingPhaseDetector."""

    def __init__(self, DatabaseManager, SystemSettingsRepositoryFactory=None):
        self.DatabaseManager = DatabaseManager
        self._SystemSettingsRepositoryFactory = SystemSettingsRepositoryFactory

    def Detect(self, Job, ActiveJob, PhaseTransitionedAt) -> "tuple[bool, str]":
        Query = (
            "SELECT tp.LastProgressUpdate, tp.CurrentPhase, tp.ProgressPercent "
            "FROM TranscodeProgress tp "
            "INNER JOIN TranscodeAttempts ta ON tp.TranscodeAttemptId = ta.Id "
            "WHERE ta.StorageRootId = %s AND ta.RelativePath = %s AND ta.Success IS NULL "
            "ORDER BY tp.LastProgressUpdate DESC "
            "LIMIT 1"
        )
        try:
            Rows = self.DatabaseManager.DatabaseService.ExecuteQuery(Query, (Job.StorageRootId, Job.RelativePath))
        # fail-loud-ok: query failure returns not-stuck to keep monitoring loop alive; false-positive kills are worse than skipped check
        except Exception as Ex:
            LoggingService.LogException(
                "PreEncodePhaseDetector progress query failed",
                Ex, "PreEncodePhaseDetector", "Detect",
            )
            return False, f"Progress query error: {Ex}"

        if not Rows:
            return False, "No TranscodeProgress row yet"

        Row = Rows[0]
        LastProgressUpdate = Row.get('LastProgressUpdate') or Row.get('lastprogressupdate')
        if LastProgressUpdate is None:
            return False, "LastProgressUpdate not yet recorded"

        if isinstance(LastProgressUpdate, str):
            LastProgressUpdate = datetime.strptime(LastProgressUpdate, "%Y-%m-%d %H:%M:%S")
        MinutesSince = (datetime.now(timezone.utc) - AsAwareUtc(LastProgressUpdate)).total_seconds() / 60.0
        Threshold = self._ReadThreshold()
        if MinutesSince >= Threshold:
            return True, (
                f"PreEncode stuck: no progress tick for {MinutesSince:.1f} min "
                f"(threshold: {Threshold}min). "
                f"Last phase: {Row.get('CurrentPhase') or Row.get('currentphase')!r}, "
                f"percent: {Row.get('ProgressPercent') or Row.get('progresspercent')}"
            )
        return False, f"PreEncode ticker fresh ({MinutesSince:.1f} min since last tick)"

    def _ReadThreshold(self) -> int:
        try:
            if self._SystemSettingsRepositoryFactory is None:
                from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
                Repo = SystemSettingsRepository()
            else:
                Repo = self._SystemSettingsRepositoryFactory()
            Value = Repo.GetSystemSetting('FrozenProgressThresholdMin')
            if Value is None:
                return DEFAULT_FROZEN_THRESHOLD_MIN
            return max(1, int(Value))
        # fail-loud-ok: threshold read swallow keeps monitoring loop alive; default preserves detection
        except Exception as Ex:
            LoggingService.LogException(
                "PreEncodePhaseDetector threshold read failed; using default",
                Ex, "PreEncodePhaseDetector", "_ReadThreshold",
            )
            return DEFAULT_FROZEN_THRESHOLD_MIN
