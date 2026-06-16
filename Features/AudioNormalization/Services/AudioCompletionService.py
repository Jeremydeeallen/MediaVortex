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


# directive: audio-vertical-compliance-and-activity | # see audio-normalization.C22
class AudioCompletionService:
    """Per-file audio-completion state -- AudioComplete flag, suspect routing, normalize-history detection; absorbed into the audio-normalization vertical 2026-06-16."""

    MP4_COMPAT_AUDIO_CODECS = ('aac', 'ac3', 'eac3', 'mp3')

    REASON_NO_AUDIO_STREAM = 'no_audio_stream'
    REASON_BELOW_BITRATE_FLOOR = 'below_bitrate_floor'
    REASON_INCOMPATIBLE_CODEC_UNSUPPORTED = 'incompatible_codec_unsupported'
    REASON_ALREADY_AT_TARGET_LOUDNESS = 'already_at_target_loudness'

    TARGET_LUFS = -23.0
    TARGET_LUFS_TOLERANCE = 1.0

    # directive: audio-vertical-compliance-and-activity | # see audio-normalization.C22
    @staticmethod
    def DetectNormalizationInCommand(FFmpegCommand: Optional[str]) -> bool:
        """True iff the command string contains 'loudnorm' (case-insensitive)."""
        if not FFmpegCommand:
            return False
        return 'loudnorm' in FFmpegCommand.lower()

    # directive: audio-vertical-compliance-and-activity | # see audio-normalization.C22
    @staticmethod
    def DetectNormalizationMode(FFmpegCommand: Optional[str]) -> Optional[str]:
        """Return 'linear' / 'dynamic' / None for the loudnorm mode in this command."""
        if not FFmpegCommand:
            return None
        Lower = FFmpegCommand.lower()
        if 'loudnorm' not in Lower:
            return None
        return 'linear' if 'linear=true' in Lower else 'dynamic'

    # directive: audio-vertical-compliance-and-activity | # see audio-normalization.C22
    @staticmethod
    def ShouldStreamCopyAudio(MediaFile: Any) -> bool:
        """True when the next encode must emit -c:a copy; consults AudioCorruptSuspect + AudioComplete."""
        if MediaFile is None:
            return False
        if bool(getattr(MediaFile, 'AudioCorruptSuspect', False)):
            return True
        return getattr(MediaFile, 'AudioComplete', None) is True

    # directive: audio-vertical-compliance-and-activity | # see audio-normalization.C22
    @classmethod
    def FloorForChannels(cls, Channels: Optional[int], FloorCfg: Any) -> int:
        """Resolve the bitrate floor (kbps) for the channel count; defaults to Stereo when unknown."""
        if not Channels or Channels < 1:
            return int(getattr(FloorCfg, 'MinAudioBitrateKbpsStereo', 96))
        if Channels == 1:
            return int(getattr(FloorCfg, 'MinAudioBitrateKbpsMono', 64))
        if Channels == 2:
            return int(getattr(FloorCfg, 'MinAudioBitrateKbpsStereo', 96))
        return int(getattr(FloorCfg, 'MinAudioBitrateKbpsSurround', 128))

    # directive: audio-vertical-compliance-and-activity | # see audio-normalization.C22
    @classmethod
    def EvaluateInitialAudioState(cls, Row, FloorCfg, HasLoudnormHistory):
        """Pure cascade returning (AudioComplete, AudioCorruptSuspect, AudioCorruptReason) from probe metadata."""
        HasProbed = Row.get('HasExplicitEnglishAudio') is not None
        if not HasProbed:
            return (None, False, None)

        AudioCodec = (Row.get('AudioCodec') or '').strip().lower()
        Resolution = Row.get('Resolution')
        if not AudioCodec and Resolution:
            return (None, True, cls.REASON_NO_AUDIO_STREAM)

        if HasLoudnormHistory:
            return (True, False, None)

        SourceLufs = Row.get('SourceIntegratedLufs')
        if SourceLufs is not None and AudioCodec in cls.MP4_COMPAT_AUDIO_CODECS:
            if abs(float(SourceLufs) - cls.TARGET_LUFS) <= cls.TARGET_LUFS_TOLERANCE:
                return (True, False, cls.REASON_ALREADY_AT_TARGET_LOUDNESS)

        AudioBitrate = Row.get('AudioBitrateKbps')
        Channels = Row.get('AudioChannels')
        if AudioBitrate is not None and AudioCodec in cls.MP4_COMPAT_AUDIO_CODECS:
            Floor = cls.FloorForChannels(Channels, FloorCfg)
            if int(AudioBitrate) <= Floor:
                return (True, False, cls.REASON_BELOW_BITRATE_FLOOR)

        return (False, False, None)

    # directive: audio-vertical-compliance-and-activity | # see audio-normalization.C22
    @staticmethod
    def MarkAudioComplete(MediaFileId: int) -> bool:
        """Idempotent setter: AudioComplete=TRUE, AudioCompletedAt=NOW(); clears below-floor reason."""
        try:
            DatabaseService().ExecuteNonQuery(
                MARK_COMPLETE_SQL,
                (AudioCompletionService.REASON_BELOW_BITRATE_FLOOR, MediaFileId),
            )
            return True
        except Exception as Ex:
            LoggingService.LogException(
                f"MarkAudioComplete failed for MediaFileId={MediaFileId}",
                Ex, "AudioCompletionService", "MarkAudioComplete",
            )
            return False

    # directive: audio-vertical-compliance-and-activity | # see audio-normalization.C22
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
                Ex, "AudioCompletionService", "ResetAudioComplete",
            )
            return 0

    # directive: audio-vertical-compliance-and-activity | # see audio-normalization.C22
    @staticmethod
    def MarkAudioCorruptSuspect(MediaFileId: int, Reason: str) -> bool:
        """Flag a file as suspect with a structured reason; called when audio path encounters a blocking codec."""
        try:
            DatabaseService().ExecuteNonQuery(MARK_SUSPECT_SQL, (Reason, MediaFileId))
            return True
        except Exception as Ex:
            LoggingService.LogException(
                f"MarkAudioCorruptSuspect failed for MediaFileId={MediaFileId}",
                Ex, "AudioCompletionService", "MarkAudioCorruptSuspect",
            )
            return False
