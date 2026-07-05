import socket
from datetime import datetime, timezone

from Core.DateTimeHelpers import AsAwareUtc
from Core.Logging.LoggingService import LoggingService


DEFAULT_FROZEN_THRESHOLD_MIN = 5


# directive: transcode-flow-canonical
class EncodingPhaseDetector:
    """Encoding phase: main ffmpeg subprocess. Two signals -- frame-advance staleness AND FFmpegPid liveness."""

    # directive: transcode-flow-canonical
    def __init__(self, DatabaseManager, ProcessInspector, SystemSettingsRepositoryFactory=None, LocalHostnameFn=None):
        self.DatabaseManager = DatabaseManager
        self.ProcessInspector = ProcessInspector
        self._SystemSettingsRepositoryFactory = SystemSettingsRepositoryFactory
        self._LocalHostnameFn = LocalHostnameFn or socket.gethostname

    # directive: transcode-flow-canonical
    def Detect(self, Job, ActiveJob, PhaseTransitionedAt) -> "tuple[bool, str]":
        FrozenStuck, FrozenReason = self._CheckFrameAdvanceStale(Job)
        if FrozenStuck:
            return True, FrozenReason

        PidStuck, PidReason = self._CheckFFmpegPidAlive(ActiveJob)
        if PidStuck:
            return True, PidReason

        return False, "Encoding in-progress (frame advance fresh; ffmpeg process alive)"

    # directive: transcode-flow-canonical
    def _CheckFrameAdvanceStale(self, Job) -> "tuple[bool, str]":
        Query = (
            "SELECT tp.LastFrameAdvance, tp.LastProgressUpdate, tp.ProgressPercent, tp.CurrentFPS, tp.CurrentFrame "
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
                "EncodingPhaseDetector frame-advance query failed",
                Ex, "EncodingPhaseDetector", "_CheckFrameAdvanceStale",
            )
            return False, f"Frame-advance query error: {Ex}"

        if not Rows:
            return False, "No TranscodeProgress row yet"

        Row = Rows[0]
        LastFrameAdvance = Row.get('LastFrameAdvance')
        if LastFrameAdvance is None:
            return False, "LastFrameAdvance not yet recorded"

        if isinstance(LastFrameAdvance, str):
            LastFrameAdvance = datetime.strptime(LastFrameAdvance, "%Y-%m-%d %H:%M:%S")
        MinutesSince = (datetime.now(timezone.utc) - AsAwareUtc(LastFrameAdvance)).total_seconds() / 60.0
        Threshold = self._ReadFrozenThreshold()
        if MinutesSince >= Threshold:
            return True, (
                f"FFmpeg alive but frozen -- no frame advance for {MinutesSince:.1f} min "
                f"(threshold: {Threshold}min). "
                f"Last progress: {Row.get('ProgressPercent')}%, FPS: {Row.get('CurrentFPS')}, "
                f"Frame: {Row.get('CurrentFrame')}"
            )
        return False, f"Frame advanced {MinutesSince:.1f} min ago"

    # directive: transcode-flow-canonical
    def _CheckFFmpegPidAlive(self, ActiveJob) -> "tuple[bool, str]":
        FFmpegPid = ActiveJob.get('FFmpegPid') if ActiveJob else None
        if not FFmpegPid:
            return False, "FFmpegPid not recorded (early Encoding phase)"

        WorkerName = ActiveJob.get('WorkerName') if ActiveJob else None
        LocalHostname = self._LocalHostnameFn()
        if WorkerName and WorkerName != LocalHostname:
            return False, "Cross-host job -- PID liveness only checked on owning host"

        Name = self.ProcessInspector.GetProcessName(FFmpegPid)
        if Name is None:
            return True, f"FFmpeg PID {FFmpegPid} recorded but process is no longer alive"
        if not self.ProcessInspector.IsFFmpegProcessName(Name):
            return True, (
                f"FFmpeg PID {FFmpegPid} recorded but process name is {Name!r} "
                f"(not ffmpeg/shell) -- PID reused"
            )
        return False, f"FFmpeg PID {FFmpegPid} alive"

    # directive: transcode-flow-canonical
    def _ReadFrozenThreshold(self) -> int:
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
                "EncodingPhaseDetector threshold read failed; using default",
                Ex, "EncodingPhaseDetector", "_ReadFrozenThreshold",
            )
            return DEFAULT_FROZEN_THRESHOLD_MIN
