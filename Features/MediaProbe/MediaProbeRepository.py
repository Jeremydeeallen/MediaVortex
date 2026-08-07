from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from Core.Database.BaseRepository import BaseRepository
from Core.Models.MediaFileModel import MediaFileModel
from Core.Logging.LoggingService import LoggingService
from Core.Path.Path import Path, PathError
from Core.Path.PathStorageRoots import GetStorageRoots


class MediaProbeRepository(BaseRepository):
    """Repository for MediaProbe-related database operations."""

    _MEDIA_FILE_SELECT_COLS = (
        "Id, SeasonId, StorageRootId, RelativePath, FileName, "
        "SizeMB, VideoBitrateKbps, AudioBitrateKbps, "
        "Resolution, Codec, DurationMinutes, FrameRate, LastScannedDate, "
        "CompressionPotential, AssignedProfile, IsInterlaced, ResolutionCategory, "
        "FileModificationTime, TotalFrames, CodecProfile, ColorRange, FieldOrder, "
        "HasBFrames, RefFrames, PixelFormat, Level, AudioChannels, AudioSampleRate, "
        "AudioSampleFormat, AudioChannelLayout, AudioCodec, SubtitleFormats, "
        "ContainerFormat, OverallBitrate, TranscodedByMediaVortex, "
        "FFprobeFailureCount, LastFFprobeError, LastFFprobeAttemptDate"
    )

    # directive: path-schema-migration | # see path.S8
    def _MapRowToMediaFile(self, Row) -> MediaFileModel:
        """Map a database row to a MediaFileModel; FilePath is a derived property, never a constructor kwarg."""
        return MediaFileModel(
            Id=Row['Id'], SeasonId=Row['SeasonId'],
            StorageRootId=Row.get('StorageRootId'),
            RelativePath=Row.get('RelativePath') or '',
            FileName=Row['FileName'], SizeMB=Row['SizeMB'],
            VideoBitrateKbps=Row['VideoBitrateKbps'], AudioBitrateKbps=Row['AudioBitrateKbps'],
            Resolution=Row['Resolution'], Codec=Row['Codec'],
            DurationMinutes=Row['DurationMinutes'], FrameRate=Row['FrameRate'],
            LastScannedDate=Row['LastScannedDate'], CompressionPotential=Row['CompressionPotential'],
            AssignedProfile=Row['AssignedProfile'], IsInterlaced=Row['IsInterlaced'],
            ResolutionCategory=Row['ResolutionCategory'], FileModificationTime=Row['FileModificationTime'],
            TotalFrames=Row['TotalFrames'], CodecProfile=Row['CodecProfile'],
            ColorRange=Row['ColorRange'], FieldOrder=Row['FieldOrder'],
            HasBFrames=Row['HasBFrames'], RefFrames=Row['RefFrames'],
            PixelFormat=Row['PixelFormat'], Level=Row['Level'],
            AudioChannels=Row['AudioChannels'], AudioSampleRate=Row['AudioSampleRate'],
            AudioSampleFormat=Row['AudioSampleFormat'], AudioChannelLayout=Row['AudioChannelLayout'],
            AudioCodec=Row['AudioCodec'], SubtitleFormats=Row['SubtitleFormats'],
            ContainerFormat=Row['ContainerFormat'], OverallBitrate=Row['OverallBitrate'],
            TranscodedByMediaVortex=Row['TranscodedByMediaVortex'],
            FFprobeFailureCount=Row.get('FFprobeFailureCount', 0),
            LastFFprobeError=Row.get('LastFFprobeError'),
            LastFFprobeAttemptDate=Row.get('LastFFprobeAttemptDate'),
        )

    # ─── Query Methods ─────────────────────────────────────────────────

    # directive: probe-worker-decoupled -- GetFilesNeedingProbe + GetFilesNeedingProbeCount retired. ProbeWorker inlines its own SKIP-LOCKED fetch in WorkerService/ProbeWorker.py._FetchBatch. No callers of these repository methods remain.

    # directive: probe-fail-loud-no-retry-cap | # see probe.C7 -- returns every row with recorded probe failure; MaxFailures arg kept for signature compat, ignored
    def GetPermanentlyFailedFiles(self, MaxFailures: int = 0) -> List[MediaFileModel]:
        try:
            Query = (
                f"SELECT {self._MEDIA_FILE_SELECT_COLS} FROM MediaFiles "
                "WHERE LastFFprobeError IS NOT NULL "
                "ORDER BY LastFFprobeAttemptDate DESC"
            )
            Rows = self.ExecuteQuery(Query)
            return [self._MapRowToMediaFile(Row) for Row in Rows]
        except Exception as Ex:
            LoggingService.LogException("Error getting failed files", Ex, "MediaProbeRepository", "GetPermanentlyFailedFiles")
            return []

    def GetMediaFileById(self, MediaFileId: int) -> Optional[MediaFileModel]:
        """Get a single media file by ID."""
        Query = f"SELECT {self._MEDIA_FILE_SELECT_COLS} FROM MediaFiles WHERE Id = %s"
        Rows = self.ExecuteQuery(Query, (MediaFileId,))
        if not Rows:
            return None
        return self._MapRowToMediaFile(Rows[0])

    def GetProbeStatistics(self) -> Dict[str, Any]:
        """Get statistics about probe status across all files."""
        try:
            Query = """
                SELECT
                    COUNT(*) AS TotalFiles,
                    COUNT(*) FILTER (WHERE Resolution IS NOT NULL AND TotalFrames IS NOT NULL) AS FilesWithMetadata,
                    COUNT(*) FILTER (WHERE Resolution IS NULL OR TotalFrames IS NULL) AS FilesNeedingProbe,
                    COUNT(*) FILTER (WHERE COALESCE(FFprobeFailureCount, 0) >= 3) AS PermanentlyFailed,
                    COUNT(*) FILTER (WHERE COALESCE(FFprobeFailureCount, 0) > 0
                                     AND COALESCE(FFprobeFailureCount, 0) < 3) AS PartiallyFailed
                FROM MediaFiles
            """
            Rows = self.ExecuteQuery(Query)
            if Rows:
                Row = Rows[0]
                return {
                    'TotalFiles': Row['TotalFiles'],
                    'FilesWithMetadata': Row['FilesWithMetadata'],
                    'FilesNeedingProbe': Row['FilesNeedingProbe'],
                    'PermanentlyFailed': Row['PermanentlyFailed'],
                    'PartiallyFailed': Row['PartiallyFailed']
                }
            return {'TotalFiles': 0, 'FilesWithMetadata': 0, 'FilesNeedingProbe': 0, 'PermanentlyFailed': 0, 'PartiallyFailed': 0}
        except Exception as Ex:
            LoggingService.LogException("Error getting probe statistics", Ex, "MediaProbeRepository", "GetProbeStatistics")
            return {'TotalFiles': 0, 'FilesWithMetadata': 0, 'FilesNeedingProbe': 0, 'PermanentlyFailed': 0, 'PartiallyFailed': 0}

    # ─── Update Methods ────────────────────────────────────────────────

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C5b
    def UpdateMetadata(self, MediaFile: MediaFileModel):
        """Update only the metadata columns and failure tracking for a media file."""
        try:
            Query = (
                "UPDATE MediaFiles SET "
                "VideoBitrateKbps = %s, AudioBitrateKbps = %s, Resolution = %s, "
                "Codec = %s, DurationMinutes = %s, FrameRate = %s, "
                "TotalFrames = %s, CodecProfile = %s, ColorRange = %s, "
                "FieldOrder = %s, HasBFrames = %s, RefFrames = %s, "
                "PixelFormat = %s, Level = %s, AudioChannels = %s, "
                "AudioSampleRate = %s, AudioSampleFormat = %s, AudioChannelLayout = %s, "
                "AudioCodec = %s, SubtitleFormats = %s, HasForcedSubtitles = %s, ContainerFormat = %s, "
                "OverallBitrate = %s, AudioLanguages = %s, HasExplicitEnglishAudio = %s, "
                "ResolutionCategory = %s, "
                "FFprobeFailureCount = %s, "
                "LastFFprobeError = %s, LastFFprobeAttemptDate = %s, "
                "NeedsReprobe = COALESCE(%s, FALSE) "
                "WHERE Id = %s"
            )
            Params = (
                MediaFile.VideoBitrateKbps, MediaFile.AudioBitrateKbps, MediaFile.Resolution,
                MediaFile.Codec, MediaFile.DurationMinutes, MediaFile.FrameRate,
                MediaFile.TotalFrames, MediaFile.CodecProfile, MediaFile.ColorRange,
                MediaFile.FieldOrder, MediaFile.HasBFrames, MediaFile.RefFrames,
                MediaFile.PixelFormat, MediaFile.Level, MediaFile.AudioChannels,
                MediaFile.AudioSampleRate, MediaFile.AudioSampleFormat, MediaFile.AudioChannelLayout,
                MediaFile.AudioCodec, MediaFile.SubtitleFormats, MediaFile.HasForcedSubtitles, MediaFile.ContainerFormat,
                MediaFile.OverallBitrate, MediaFile.AudioLanguages, MediaFile.HasExplicitEnglishAudio,
                MediaFile.ResolutionCategory,
                MediaFile.FFprobeFailureCount,
                MediaFile.LastFFprobeError, MediaFile.LastFFprobeAttemptDate,
                getattr(MediaFile, 'NeedsReprobe', False),
                MediaFile.Id
            )
            self.ExecuteNonQuery(Query, Params)
        except Exception as Ex:
            LoggingService.LogException(f"Error updating metadata for file ID {MediaFile.Id}", Ex, "MediaProbeRepository", "UpdateMetadata")
            raise

    # directive: probe-fail-loud-no-retry-cap -- failure also clears NeedsReprobe so operator's one-shot command is consumed; prevents re-fetch loop on persistent-fail sources
    def RecordProbeFailure(self, MediaFileId: int, ErrorMessage: str):
        try:
            Query = (
                "UPDATE MediaFiles SET "
                "FFprobeFailureCount = COALESCE(FFprobeFailureCount, 0) + 1, "
                "LastFFprobeError = %s, "
                "LastFFprobeAttemptDate = %s, "
                "NeedsReprobe = FALSE "
                "WHERE Id = %s"
            )
            self.ExecuteNonQuery(Query, (ErrorMessage, datetime.now(timezone.utc), MediaFileId))
        except Exception as Ex:
            LoggingService.LogException(f"Error recording probe failure for file ID {MediaFileId}", Ex, "MediaProbeRepository", "RecordProbeFailure")

    # directive: probe-fail-loud-no-retry-cap -- operator-facing reset; sets NeedsReprobe=TRUE so the row is picked up next tick
    def ResetProbeFailures(self, MediaFileId: int):
        try:
            Query = (
                "UPDATE MediaFiles SET "
                "FFprobeFailureCount = 0, "
                "LastFFprobeError = NULL, "
                "LastFFprobeAttemptDate = NULL, "
                "NeedsReprobe = TRUE "
                "WHERE Id = %s"
            )
            self.ExecuteNonQuery(Query, (MediaFileId,))
        except Exception as Ex:
            LoggingService.LogException(f"Error resetting probe failures for file ID {MediaFileId}", Ex, "MediaProbeRepository", "ResetProbeFailures")

    def ResetAllProbeFailures(self):
        """Reset FFprobe failure tracking for all files."""
        try:
            Query = """UPDATE MediaFiles SET
                        FFprobeFailureCount = 0,
                        LastFFprobeError = NULL,
                        LastFFprobeAttemptDate = NULL
                       WHERE COALESCE(FFprobeFailureCount, 0) > 0"""
            AffectedRows = self.ExecuteNonQuery(Query)
            return AffectedRows
        except Exception as Ex:
            LoggingService.LogException("Error resetting all probe failures", Ex, "MediaProbeRepository", "ResetAllProbeFailures")
            return 0
