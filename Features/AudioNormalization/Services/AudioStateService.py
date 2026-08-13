from typing import Optional, Tuple, List, Any

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


MARK_COMPLETE_SQL = (
    "UPDATE MediaFiles "
    "SET AudioComplete = TRUE, "
    "AudioCompletedAt = NOW(), "
    "AudioCorruptReason = CASE "
    "WHEN AudioCorruptReason = %s THEN AudioCorruptReason "
    "ELSE NULL "
    "END "
    "WHERE Id = %s"
)


RESET_COMPLETE_SQL = (
    "UPDATE MediaFiles "
    "SET AudioComplete = FALSE, "
    "AudioCompletedAt = NULL, "
    "AudioCorruptReason = NULL "
    "WHERE Id = ANY(%s) "
    "AND AudioCorruptSuspect = FALSE"
)


MARK_SUSPECT_SQL = (
    "UPDATE MediaFiles "
    "SET AudioCorruptSuspect = TRUE, "
    "AudioCorruptReason = %s "
    "WHERE Id = %s"
)


# directive: audio-vertical-dialog-boost-enforcement
class AudioStateService:
    """Audio-state machine on MediaFile: AudioComplete flag, suspect routing, normalize-history detection."""

    REASON_BELOW_BITRATE_FLOOR = 'below_bitrate_floor'

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S2
    @staticmethod
    def DetectNormalizationInCommand(FFmpegCommand: Optional[str]) -> bool:
        """True iff the command string contains 'loudnorm' (case-insensitive)."""
        if not FFmpegCommand:
            return False
        return 'loudnorm' in FFmpegCommand.lower()

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S2
    @staticmethod
    def DetectNormalizationMode(FFmpegCommand: Optional[str]) -> Optional[str]:
        """Return 'linear' / 'dynamic' / None for the loudnorm mode in this command."""
        if not FFmpegCommand:
            return None
        Lower = FFmpegCommand.lower()
        if 'loudnorm' not in Lower:
            return None
        return 'linear' if 'linear=true' in Lower else 'dynamic'

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S2
    @staticmethod
    def ShouldStreamCopyAudio(MediaFile: Any) -> bool:
        """True when the next encode must emit -c:a copy; consults AudioCorruptSuspect + AudioComplete."""
        if MediaFile is None:
            return False
        if bool(getattr(MediaFile, 'AudioCorruptSuspect', False)):
            return True
        return getattr(MediaFile, 'AudioComplete', None) is True

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S2
    @staticmethod
    def MarkAudioComplete(MediaFileId: int) -> bool:
        """Idempotent setter: AudioComplete=TRUE, AudioCompletedAt=NOW(); clears below-floor reason."""
        try:
            DatabaseService().ExecuteNonQuery(
                MARK_COMPLETE_SQL,
                (AudioStateService.REASON_BELOW_BITRATE_FLOOR, MediaFileId),
            )
            return True
        except Exception as Ex:
            LoggingService.LogException(
                f"MarkAudioComplete failed for MediaFileId={MediaFileId}",
                Ex, "AudioStateService", "MarkAudioComplete",
            )
            return False

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S2
    @staticmethod
    def ResetAudioComplete(MediaFileIds: List[int]) -> int:
        """Force re-normalize on next encode; returns rowcount; spares AudioCorruptSuspect rows."""
        if not MediaFileIds:
            return 0
        try:
            Db = DatabaseService()
            Conn = Db.GetConnection()
            try:
                Cur = Conn.cursor()
                Cur.execute(RESET_COMPLETE_SQL, (list(MediaFileIds),))
                RowCount = Cur.rowcount
                Conn.commit()
                return RowCount
            finally:
                Db.CloseConnection(Conn)
        except Exception as Ex:
            LoggingService.LogException(
                f"ResetAudioComplete failed for {len(MediaFileIds)} ids",
                Ex, "AudioStateService", "ResetAudioComplete",
            )
            return 0

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S2
    @staticmethod
    def MarkAudioCorruptSuspect(MediaFileId: int, Reason: str) -> bool:
        """Flag a file as suspect with a structured reason; called when audio path encounters a blocking codec."""
        try:
            DatabaseService().ExecuteNonQuery(MARK_SUSPECT_SQL, (Reason, MediaFileId))
            return True
        except Exception as Ex:
            LoggingService.LogException(
                f"MarkAudioCorruptSuspect failed for MediaFileId={MediaFileId}",
                Ex, "AudioStateService", "MarkAudioCorruptSuspect",
            )
            return False
