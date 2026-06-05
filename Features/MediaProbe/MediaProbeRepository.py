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
        "FFprobeFailureCount, LastFFprobeError, LastFFprobeAttemptDate, "
        "NeedsQuick, NeedsTranscode"
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
            NeedsQuick=Row.get('NeedsQuick'),
            NeedsTranscode=Row.get('NeedsTranscode'),
        )

    # ─── Query Methods ─────────────────────────────────────────────────

    # directive: path-schema-migration | # see path.S8
    def GetFilesNeedingProbe(self, RootFolderId: Optional[int] = None, MaxFailures: int = 3) -> List[MediaFileModel]:
        """Files that need FFprobe metadata; optionally filtered by RootFolderId (typed-pair filter on StorageRootId + RelativePath prefix)."""
        try:
            Conditions = [
                "(NeedsReprobe = TRUE OR Resolution IS NULL OR TotalFrames IS NULL OR AudioCodec IS NULL)",
                "COALESCE(FFprobeFailureCount, 0) < %s"
            ]
            Params: List[Any] = [MaxFailures]

            if RootFolderId is not None:
                RootQuery = "SELECT RootFolder FROM RootFolders WHERE Id = %s"
                RootRows = self.ExecuteQuery(RootQuery, (RootFolderId,))
                if not RootRows:
                    return []
                RootPath = RootRows[0]['RootFolder']
                try:
                    Parsed = Path.FromLegacyString(RootPath, GetStorageRoots())
                except PathError:
                    LoggingService.LogWarning(
                        "GetFilesNeedingProbe: RootFolder did not match any StorageRoot prefix: " + str(RootPath),
                        "MediaProbeRepository", "GetFilesNeedingProbe",
                    )
                    return []
                Conditions.append("StorageRootId = %s AND LEFT(RelativePath, %s) = %s")
                Params.extend([Parsed.StorageRootId, len(Parsed.RelativePath), Parsed.RelativePath])

            WhereClause = " AND ".join(Conditions)
            Query = (
                "SELECT " + self._MEDIA_FILE_SELECT_COLS + " FROM MediaFiles WHERE "
                + WhereClause
                + " ORDER BY COALESCE(LastFFprobeAttemptDate, '1970-01-01') ASC"
            )
            Rows = self.ExecuteQuery(Query, tuple(Params))
            return [self._MapRowToMediaFile(Row) for Row in Rows]

        except Exception as Ex:
            LoggingService.LogException("Error getting files needing probe", Ex, "MediaProbeRepository", "GetFilesNeedingProbe")
            return []

    # directive: path-schema-migration | # see path.S8
    def GetFilesNeedingProbeCount(self, RootFolderId: Optional[int] = None, MaxFailures: int = 3) -> int:
        """Count of files matching GetFilesNeedingProbe; typed-pair filter on StorageRootId + RelativePath prefix when RootFolderId is set."""
        try:
            Conditions = [
                "(NeedsReprobe = TRUE OR Resolution IS NULL OR TotalFrames IS NULL OR AudioCodec IS NULL)",
                "COALESCE(FFprobeFailureCount, 0) < %s",
            ]
            Params: List[Any] = [MaxFailures]
            if RootFolderId is not None:
                RootRows = self.ExecuteQuery("SELECT RootFolder FROM RootFolders WHERE Id = %s", (RootFolderId,))
                if not RootRows:
                    return 0
                RootPath = RootRows[0]['RootFolder']
                try:
                    Parsed = Path.FromLegacyString(RootPath, GetStorageRoots())
                except PathError:
                    LoggingService.LogWarning(
                        "GetFilesNeedingProbeCount: RootFolder did not match any StorageRoot prefix: " + str(RootPath),
                        "MediaProbeRepository", "GetFilesNeedingProbeCount",
                    )
                    return 0
                Conditions.append("StorageRootId = %s AND LEFT(RelativePath, %s) = %s")
                Params.extend([Parsed.StorageRootId, len(Parsed.RelativePath), Parsed.RelativePath])
            WhereClause = " AND ".join(Conditions)
            Rows = self.ExecuteQuery(
                "SELECT COUNT(*) AS N FROM MediaFiles WHERE " + WhereClause,
                tuple(Params),
            )
            return int(Rows[0]['N']) if Rows else 0
        except Exception as Ex:
            LoggingService.LogException("Error counting files needing probe", Ex, "MediaProbeRepository", "GetFilesNeedingProbeCount")
            return 0

    def GetPermanentlyFailedFiles(self, MaxFailures: int = 3) -> List[MediaFileModel]:
        """Get files that have exceeded the max failure threshold."""
        try:
            Query = f"""SELECT {self._MEDIA_FILE_SELECT_COLS} FROM MediaFiles
                        WHERE COALESCE(FFprobeFailureCount, 0) >= %s
                        ORDER BY LastFFprobeAttemptDate DESC"""
            Rows = self.ExecuteQuery(Query, (MaxFailures,))
            return [self._MapRowToMediaFile(Row) for Row in Rows]
        except Exception as Ex:
            LoggingService.LogException("Error getting permanently failed files", Ex, "MediaProbeRepository", "GetPermanentlyFailedFiles")
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

    def UpdateMetadata(self, MediaFile: MediaFileModel):
        """Update only the metadata columns and failure tracking for a media file."""
        try:
            Query = """UPDATE MediaFiles SET
                        VideoBitrateKbps = %s, AudioBitrateKbps = %s, Resolution = %s,
                        Codec = %s, DurationMinutes = %s, FrameRate = %s,
                        TotalFrames = %s, CodecProfile = %s, ColorRange = %s,
                        FieldOrder = %s, HasBFrames = %s, RefFrames = %s,
                        PixelFormat = %s, Level = %s, AudioChannels = %s,
                        AudioSampleRate = %s, AudioSampleFormat = %s, AudioChannelLayout = %s,
                        AudioCodec = %s, SubtitleFormats = %s, ContainerFormat = %s,
                        OverallBitrate = %s, AudioLanguages = %s, HasExplicitEnglishAudio = %s,
                        ResolutionCategory = %s,
                        FFprobeFailureCount = %s,
                        LastFFprobeError = %s, LastFFprobeAttemptDate = %s,
                        NeedsReprobe = COALESCE(%s, FALSE)
                       WHERE Id = %s"""
            Params = (
                MediaFile.VideoBitrateKbps, MediaFile.AudioBitrateKbps, MediaFile.Resolution,
                MediaFile.Codec, MediaFile.DurationMinutes, MediaFile.FrameRate,
                MediaFile.TotalFrames, MediaFile.CodecProfile, MediaFile.ColorRange,
                MediaFile.FieldOrder, MediaFile.HasBFrames, MediaFile.RefFrames,
                MediaFile.PixelFormat, MediaFile.Level, MediaFile.AudioChannels,
                MediaFile.AudioSampleRate, MediaFile.AudioSampleFormat, MediaFile.AudioChannelLayout,
                MediaFile.AudioCodec, MediaFile.SubtitleFormats, MediaFile.ContainerFormat,
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

    def RecordProbeFailure(self, MediaFileId: int, ErrorMessage: str):
        """Increment FFprobe failure count and record the error."""
        try:
            Query = """UPDATE MediaFiles SET
                        FFprobeFailureCount = COALESCE(FFprobeFailureCount, 0) + 1,
                        LastFFprobeError = %s,
                        LastFFprobeAttemptDate = %s
                       WHERE Id = %s"""
            self.ExecuteNonQuery(Query, (ErrorMessage, datetime.now(timezone.utc), MediaFileId))
        except Exception as Ex:
            LoggingService.LogException(f"Error recording probe failure for file ID {MediaFileId}", Ex, "MediaProbeRepository", "RecordProbeFailure")

    def ResetProbeFailures(self, MediaFileId: int):
        """Reset FFprobe failure tracking for a file so it can be retried."""
        try:
            Query = """UPDATE MediaFiles SET
                        FFprobeFailureCount = 0,
                        LastFFprobeError = NULL,
                        LastFFprobeAttemptDate = NULL
                       WHERE Id = %s"""
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
