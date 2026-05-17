"""AudioCompletionService -- owns per-file audio-completion state.

Pure-logic service plus three DB-write sinks (MarkAudioComplete,
ResetAudioComplete, MarkAudioCorruptSuspect). All reads go through the
caller's data-loading path -- this service does not cache.

See:
- Features/AudioCompletion/audio-completion.feature.md (criteria 6-7)
- Features/AudioCompletion/audio-completion.flow.md (state lifecycle)
"""

from typing import Optional, Tuple, List, Any

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


class AudioCompletionService:
    """Stateless service. Construct per call or reuse -- both safe."""

    MP4_COMPAT_AUDIO_CODECS = ('aac', 'ac3', 'eac3', 'mp3')

    REASON_NO_AUDIO_STREAM = 'no_audio_stream'
    REASON_BELOW_BITRATE_FLOOR = 'below_bitrate_floor'
    REASON_INCOMPATIBLE_CODEC_UNSUPPORTED = 'incompatible_codec_unsupported'

    @staticmethod
    def DetectNormalizationInCommand(FFmpegCommand: Optional[str]) -> bool:
        """True if the command contains the loudnorm filter (case-insensitive).

        Used in three places:
        - Backfill: scan TranscodeAttempts history per MediaFile.
        - Post-flight FileReplacement: just-finished attempt's command.
        - Test harness.
        """
        if not FFmpegCommand:
            return False
        return 'loudnorm' in FFmpegCommand.lower()

    @staticmethod
    def ShouldStreamCopyAudio(MediaFile: Any) -> bool:
        """True when the next encode must emit -c:a copy (no audio re-encode).

        AudioComplete=true means we've already done the one-shot pass.
        AudioCorruptSuspect=true means we cannot mechanically fix the audio
        and must not try -- if a suspect file ever reaches an encode path
        despite the queue gate, stream-copy is the least-damaging option.
        """
        if MediaFile is None:
            return False
        if bool(getattr(MediaFile, 'AudioCorruptSuspect', False)):
            return True
        return getattr(MediaFile, 'AudioComplete', None) is True

    @classmethod
    def FloorForChannels(cls, Channels: Optional[int], FloorCfg: Any) -> int:
        """Resolve the bitrate floor (kbps) for the given channel count.

        FloorCfg is a QueueAdmissionConfigModel (or any object with the
        three MinAudioBitrateKbps* attributes).

        Channel-count tiers:
            1   -> Mono
            2   -> Stereo
            3+  -> Surround
            None / 0 -> Stereo (conservative default; most-common case)
        """
        if not Channels or Channels < 1:
            return int(getattr(FloorCfg, 'MinAudioBitrateKbpsStereo', 96))
        if Channels == 1:
            return int(getattr(FloorCfg, 'MinAudioBitrateKbpsMono', 64))
        if Channels == 2:
            return int(getattr(FloorCfg, 'MinAudioBitrateKbpsStereo', 96))
        return int(getattr(FloorCfg, 'MinAudioBitrateKbpsSurround', 128))

    @classmethod
    def EvaluateInitialAudioState(
        cls,
        Row: dict,
        FloorCfg: Any,
        HasLoudnormHistory: bool,
    ) -> Tuple[Optional[bool], bool, Optional[str]]:
        """Pure derivation. Returns (AudioComplete, AudioCorruptSuspect, AudioCorruptReason).

        Used by the backfill script and by RecomputeForFiles when seeding
        a row that hasn't been touched by an encode pass yet.

        Cascade (first match wins):
          a. Not yet probed (HasExplicitEnglishAudio IS NULL)
             -> (None, False, None) -- undecidable, leave NULL
          b. Probed and zero audio streams (HasExplicitEnglishAudio IS NOT NULL
             AND AudioCodec IS NULL AND Resolution IS NOT NULL)
             -> (None, True, 'no_audio_stream') -- Suspect, hard block
          c. Loudnorm in historical successful attempt
             -> (True, False, None) -- already normalized, stream-copy forever
          d. AudioBitrateKbps at or below channel-tier floor (and MP4-compat codec)
             -> (True, False, 'below_bitrate_floor') -- skip the pass permanently
          e. Otherwise (probed file with decodable audio that needs normalization
             and/or codec conversion)
             -> (False, False, None) -- eligible for one-shot pass next encode

        DTS / TrueHD / FLAC / PCM / Vorbis / Opus fall through to (e). The
        one-shot pass converts them via BuildAudioCodecArgs (EAC3 fallback)
        in the same FFmpeg invocation that applies loudnorm.
        """
        HasProbed = Row.get('HasExplicitEnglishAudio') is not None
        if not HasProbed:
            return (None, False, None)

        AudioCodec = (Row.get('AudioCodec') or '').strip().lower()
        Resolution = Row.get('Resolution')
        if not AudioCodec and Resolution:
            return (None, True, cls.REASON_NO_AUDIO_STREAM)

        if HasLoudnormHistory:
            return (True, False, None)

        AudioBitrate = Row.get('AudioBitrateKbps')
        Channels = Row.get('AudioChannels')
        if AudioBitrate is not None and AudioCodec in cls.MP4_COMPAT_AUDIO_CODECS:
            Floor = cls.FloorForChannels(Channels, FloorCfg)
            if int(AudioBitrate) <= Floor:
                return (True, False, cls.REASON_BELOW_BITRATE_FLOOR)

        return (False, False, None)

    @staticmethod
    def MarkAudioComplete(MediaFileId: int) -> bool:
        """Idempotent setter -- AudioComplete=true, AudioCompletedAt=NOW().

        Called from FileReplacement post-flight when the just-finished
        FFmpeg command contained loudnorm. Also exposed via
        POST /api/AudioCompletion/MarkComplete for operator overrides
        ("trust this source").
        """
        try:
            Db = DatabaseService()
            Db.ExecuteNonQuery(
                """
                UPDATE MediaFiles
                SET AudioComplete = TRUE,
                    AudioCompletedAt = NOW(),
                    AudioCorruptReason = CASE
                        WHEN AudioCorruptReason = %s THEN AudioCorruptReason
                        ELSE NULL
                    END
                WHERE Id = %s
                """,
                (AudioCompletionService.REASON_BELOW_BITRATE_FLOOR, MediaFileId),
            )
            return True
        except Exception as Ex:
            LoggingService.LogException(
                f"MarkAudioComplete failed for MediaFileId={MediaFileId}",
                Ex, "AudioCompletionService", "MarkAudioComplete",
            )
            return False

    @staticmethod
    def ResetAudioComplete(MediaFileIds: List[int]) -> int:
        """Force a re-normalize on next encode. Returns rows updated.

        Sets AudioComplete=false, AudioCompletedAt=NULL. Does NOT touch
        AudioCorruptSuspect -- a suspect file stays suspect until
        explicitly cleared via a separate code path.
        """
        if not MediaFileIds:
            return 0
        try:
            Db = DatabaseService()
            Conn = Db.GetConnection()
            try:
                Cur = Conn.cursor()
                Cur.execute(
                    """
                    UPDATE MediaFiles
                    SET AudioComplete = FALSE,
                        AudioCompletedAt = NULL,
                        AudioCorruptReason = NULL
                    WHERE Id = ANY(%s)
                      AND AudioCorruptSuspect = FALSE
                    """,
                    (list(MediaFileIds),),
                )
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

    @staticmethod
    def MarkAudioCorruptSuspect(MediaFileId: int, Reason: str) -> bool:
        """Flag a file as suspect with a structured reason.

        Called from BuildRemuxCommand when an AudioComplete=true file
        unexpectedly has a non-MP4-compat codec (logic error case).
        """
        try:
            Db = DatabaseService()
            Db.ExecuteNonQuery(
                """
                UPDATE MediaFiles
                SET AudioCorruptSuspect = TRUE,
                    AudioCorruptReason = %s
                WHERE Id = %s
                """,
                (Reason, MediaFileId),
            )
            return True
        except Exception as Ex:
            LoggingService.LogException(
                f"MarkAudioCorruptSuspect failed for MediaFileId={MediaFileId}",
                Ex, "AudioCompletionService", "MarkAudioCorruptSuspect",
            )
            return False
