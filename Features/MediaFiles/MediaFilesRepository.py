import re
from typing import Optional, List, Dict, Any
from Core.Database.BaseRepository import BaseRepository
from Core.Database.DatabaseService import EscapeLikePattern
from Core.Logging.LoggingService import LoggingService
from Core.Path.Path import Path, PathError
from Core.Path.PathStorageRoots import GetStorageRoots, GetPrefixMap
# directive: path-schema-migration | # see path.S8
from Core.Path.LocalPath import LocalSplitExt
from Models.MediaFileModel import MediaFileModel
from Models.SeasonModel import SeasonModel


# directive: path-schema-migration | # see path.S8
_FULL_SELECT_COLS = (
    "Id, SeasonId, StorageRootId, RelativePath, FileName, SizeMB, FileSize, "
    "VideoBitrateKbps, AudioBitrateKbps, "
    "Resolution, Codec, DurationMinutes, FrameRate, LastScannedDate, "
    "CompressionPotential, AssignedProfile, IsInterlaced, ResolutionCategory, "
    "FileModificationTime, LastModifiedDate, TotalFrames, CodecProfile, ColorRange, FieldOrder, "
    "HasBFrames, RefFrames, PixelFormat, Level, AudioChannels, AudioSampleRate, "
    "AudioSampleFormat, AudioChannelLayout, AudioCodec, AudioLanguages, HasExplicitEnglishAudio, "
    "SubtitleFormats, ContainerFormat, OverallBitrate, TranscodedByMediaVortex, "
    "AudioComplete, AudioCorruptSuspect, AudioCorruptReason, "
    "SourceIntegratedLufs, SourceLoudnessRangeLU, SourceTruePeakDbtp, "
    "SourceIntegratedThresholdLufs, AdmissionDeferReason, "
    "LoudnessMeasurementFailureReason, AudioNormalizationMode"
)


# directive: path-schema-migration | # see path.S8
def _ParsePath(CanonicalString: str) -> Optional[Path]:
    """Parse a canonical FilePath string to a Path via Path.FromLegacyString; None on parse failure."""
    if not CanonicalString:
        return None
    try:
        return Path.FromLegacyString(CanonicalString, GetStorageRoots())
    except PathError:
        return None


# directive: path-schema-migration | # see path.S8
class MediaFilesRepository(BaseRepository):
    """SQL for MediaFiles, MediaFilesArchive, and Seasons; typed pair (StorageRootId, RelativePath) is canonical."""

    # directive: path-schema-migration | # see path.S8
    def _MapRowToMediaFile(self, row: Dict[str, Any]) -> MediaFileModel:
        """Construct MediaFileModel from a row dict; FilePath is computed by the model's @property."""
        return MediaFileModel(
            Id=row.get('Id') or row.get('id'),
            SeasonId=row.get('SeasonId') or row.get('seasonid'),
            StorageRootId=row.get('StorageRootId') or row.get('storagerootid'),
            RelativePath=(row.get('RelativePath') or row.get('relativepath') or ''),
            FileName=(row.get('FileName') or row.get('filename') or ''),
            SizeMB=(row.get('SizeMB') or row.get('sizemb') or 0.0),
            FileSize=(row.get('FileSize') or row.get('filesize')),
            VideoBitrateKbps=(row.get('VideoBitrateKbps') or row.get('videobitratekbps')),
            AudioBitrateKbps=(row.get('AudioBitrateKbps') or row.get('audiobitratekbps')),
            Resolution=(row.get('Resolution') or row.get('resolution')),
            Codec=(row.get('Codec') or row.get('codec')),
            DurationMinutes=(row.get('DurationMinutes') or row.get('durationminutes')),
            FrameRate=(row.get('FrameRate') or row.get('framerate')),
            LastScannedDate=(row.get('LastScannedDate') or row.get('lastscanneddate')),
            CompressionPotential=(row.get('CompressionPotential') or row.get('compressionpotential')),
            AssignedProfile=(row.get('AssignedProfile') or row.get('assignedprofile')),
            IsInterlaced=row.get('IsInterlaced') if 'IsInterlaced' in row else row.get('isinterlaced'),
            ResolutionCategory=(row.get('ResolutionCategory') or row.get('resolutioncategory')),
            FileModificationTime=(row.get('FileModificationTime') or row.get('filemodificationtime')),
            LastModifiedDate=(row.get('LastModifiedDate') or row.get('lastmodifieddate')),
            TotalFrames=(row.get('TotalFrames') or row.get('totalframes')),
            CodecProfile=(row.get('CodecProfile') or row.get('codecprofile')),
            ColorRange=(row.get('ColorRange') or row.get('colorrange')),
            FieldOrder=(row.get('FieldOrder') or row.get('fieldorder')),
            HasBFrames=(row.get('HasBFrames') or row.get('hasbframes')),
            RefFrames=(row.get('RefFrames') or row.get('refframes')),
            PixelFormat=(row.get('PixelFormat') or row.get('pixelformat')),
            Level=(row.get('Level') or row.get('level')),
            AudioChannels=(row.get('AudioChannels') or row.get('audiochannels')),
            AudioSampleRate=(row.get('AudioSampleRate') or row.get('audiosamplerate')),
            AudioSampleFormat=(row.get('AudioSampleFormat') or row.get('audiosampleformat')),
            AudioChannelLayout=(row.get('AudioChannelLayout') or row.get('audiochannellayout')),
            AudioCodec=(row.get('AudioCodec') or row.get('audiocodec')),
            AudioLanguages=(row.get('AudioLanguages') or row.get('audiolanguages')),
            HasExplicitEnglishAudio=row.get('HasExplicitEnglishAudio') if 'HasExplicitEnglishAudio' in row else row.get('hasexplicitenglishaudio'),
            SubtitleFormats=(row.get('SubtitleFormats') or row.get('subtitleformats')),
            ContainerFormat=(row.get('ContainerFormat') or row.get('containerformat')),
            OverallBitrate=(row.get('OverallBitrate') or row.get('overallbitrate')),
            TranscodedByMediaVortex=row.get('TranscodedByMediaVortex') if 'TranscodedByMediaVortex' in row else row.get('transcodedbymediavortex'),
            AudioComplete=row.get('AudioComplete') if 'AudioComplete' in row else row.get('audiocomplete'),
            AudioCorruptSuspect=row.get('AudioCorruptSuspect') if 'AudioCorruptSuspect' in row else row.get('audiocorruptsuspect'),
            AudioCorruptReason=(row.get('AudioCorruptReason') or row.get('audiocorruptreason')),
            SourceIntegratedLufs=(row.get('SourceIntegratedLufs') or row.get('sourceintegratedlufs')),
            SourceLoudnessRangeLU=(row.get('SourceLoudnessRangeLU') or row.get('sourceloudnessrangelu')),
            SourceTruePeakDbtp=(row.get('SourceTruePeakDbtp') or row.get('sourcetruepeakdbtp')),
            SourceIntegratedThresholdLufs=(row.get('SourceIntegratedThresholdLufs') or row.get('sourceintegratedthresholdlufs')),
            AdmissionDeferReason=(row.get('AdmissionDeferReason') or row.get('admissiondeferreason')),
            LoudnessMeasurementFailureReason=(row.get('LoudnessMeasurementFailureReason') or row.get('loudnessmeasurementfailurereason')),
            AudioNormalizationMode=(row.get('AudioNormalizationMode') or row.get('audionormalizationmode')),
        )

    # directive: path-schema-migration | # see path.S8
    def GetAllMediaFiles(self) -> List[MediaFileModel]:
        """Return every MediaFiles row."""
        query = f"SELECT {_FULL_SELECT_COLS} FROM MediaFiles"
        rows = self.DatabaseService.ExecuteQuery(query)
        return [self._MapRowToMediaFile(r) for r in rows]

    # directive: path-schema-migration | # see path.S8
    def GetMediaFileById(self, MediaFileId: int) -> Optional[MediaFileModel]:
        """Return one MediaFiles row by Id."""
        query = f"SELECT {_FULL_SELECT_COLS} FROM MediaFiles WHERE Id = %s"
        rows = self.DatabaseService.ExecuteQuery(query, (MediaFileId,))
        return self._MapRowToMediaFile(rows[0]) if rows else None

    # directive: path-schema-migration | # see path.S8
    def GetMediaFileByPath(self, PathArg) -> Optional[MediaFileModel]:
        """Look up by Path object or canonical-string FilePath; exact-match typed-pair WHERE."""
        P = PathArg if isinstance(PathArg, Path) else _ParsePath(PathArg)
        if P is None:
            return None
        query = f"SELECT {_FULL_SELECT_COLS} FROM MediaFiles WHERE StorageRootId = %s AND RelativePath = %s LIMIT 1"
        rows = self.DatabaseService.ExecuteQuery(query, (P.StorageRootId, P.RelativePath))
        return self._MapRowToMediaFile(rows[0]) if rows else None

    # directive: path-schema-migration | # see path.S8
    def DeleteMediaFileByPath(self, PathArg) -> bool:
        """Delete by Path object or canonical-string FilePath; exact-match typed-pair DELETE."""
        P = PathArg if isinstance(PathArg, Path) else _ParsePath(PathArg)
        if P is None:
            return False
        affected = self.DatabaseService.ExecuteNonQuery(
            "DELETE FROM MediaFiles WHERE StorageRootId = %s AND RelativePath = %s",
            (P.StorageRootId, P.RelativePath)
        )
        return affected > 0

    # directive: path-schema-migration | # see path.S8
    def DeleteMediaFile(self, MediaFileId: int) -> bool:
        """Delete by Id."""
        affected = self.DatabaseService.ExecuteNonQuery(
            "DELETE FROM MediaFiles WHERE Id = %s", (MediaFileId,)
        )
        return affected > 0

    # directive: path-schema-migration | # see path.S8
    def SaveMediaFile(self, MediaFile: MediaFileModel) -> int:
        """Insert or update by Id when set; else dedupe on typed pair; returns the row Id."""
        if MediaFile.StorageRootId is None or not MediaFile.RelativePath:
            raise PathError(f"SaveMediaFile: MediaFile missing typed pair (StorageRootId={MediaFile.StorageRootId}, RelativePath={MediaFile.RelativePath!r})")
        connection = self.DatabaseService.GetConnection()
        try:
            cursor = connection.cursor()
            if MediaFile.Id is None:
                cursor.execute(
                    "SELECT Id FROM MediaFiles WHERE StorageRootId = %s AND RelativePath = %s LIMIT 1",
                    (MediaFile.StorageRootId, MediaFile.RelativePath),
                )
                existing = cursor.fetchone()
                if existing:
                    MediaFile.Id = existing['Id']
                    return self._UpdateMediaFile(cursor, connection, MediaFile)
                cursor.execute(
                    "INSERT INTO MediaFiles "
                    "(SeasonId, StorageRootId, RelativePath, FileName, SizeMB, FileSize, "
                    " VideoBitrateKbps, AudioBitrateKbps, Resolution, ResolutionCategory, IsInterlaced, "
                    " Codec, DurationMinutes, FrameRate, LastScannedDate, "
                    " CompressionPotential, AssignedProfile, FileModificationTime, LastModifiedDate, "
                    " TotalFrames, CodecProfile, ColorRange, FieldOrder, HasBFrames, RefFrames, "
                    " PixelFormat, Level, AudioChannels, AudioSampleRate, AudioSampleFormat, "
                    " AudioChannelLayout, AudioCodec, AudioLanguages, HasExplicitEnglishAudio, "
                    " SubtitleFormats, ContainerFormat, OverallBitrate, TranscodedByMediaVortex, "
                    " AudioNormalizationMode) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "RETURNING Id",
                    (
                        MediaFile.SeasonId, MediaFile.StorageRootId, MediaFile.RelativePath,
                        MediaFile.FileName, MediaFile.SizeMB, MediaFile.FileSize,
                        MediaFile.VideoBitrateKbps, MediaFile.AudioBitrateKbps, MediaFile.Resolution,
                        MediaFile.ResolutionCategory, MediaFile.IsInterlaced,
                        MediaFile.Codec, MediaFile.DurationMinutes, MediaFile.FrameRate,
                        MediaFile.LastScannedDate, MediaFile.CompressionPotential, MediaFile.AssignedProfile,
                        MediaFile.FileModificationTime, MediaFile.LastModifiedDate,
                        MediaFile.TotalFrames, MediaFile.CodecProfile,
                        MediaFile.ColorRange, MediaFile.FieldOrder, MediaFile.HasBFrames, MediaFile.RefFrames,
                        MediaFile.PixelFormat, MediaFile.Level, MediaFile.AudioChannels, MediaFile.AudioSampleRate,
                        MediaFile.AudioSampleFormat, MediaFile.AudioChannelLayout, MediaFile.AudioCodec,
                        MediaFile.AudioLanguages, MediaFile.HasExplicitEnglishAudio,
                        MediaFile.SubtitleFormats, MediaFile.ContainerFormat,
                        MediaFile.OverallBitrate, MediaFile.TranscodedByMediaVortex,
                        MediaFile.AudioNormalizationMode,
                    ),
                )
                newId = cursor.fetchone()[0]
                connection.commit()
                return newId
            return self._UpdateMediaFile(cursor, connection, MediaFile)
        finally:
            self.DatabaseService.CloseConnection(connection)

    # directive: path-schema-migration | # see path.S8
    def _UpdateMediaFile(self, cursor, connection, MediaFile: MediaFileModel) -> int:
        """Issue the UPDATE statement for a MediaFile row with known Id."""
        cursor.execute(
            "UPDATE MediaFiles "
            "SET SeasonId = %s, StorageRootId = %s, RelativePath = %s, "
            "    FileName = %s, SizeMB = %s, "
            "    FileSize = COALESCE(%s, FileSize), "
            "    VideoBitrateKbps = %s, AudioBitrateKbps = %s, Resolution = %s, "
            "    ResolutionCategory = COALESCE(%s, ResolutionCategory), "
            "    IsInterlaced = COALESCE(%s, IsInterlaced), "
            "    Codec = %s, DurationMinutes = %s, FrameRate = %s, LastScannedDate = %s, "
            "    CompressionPotential = %s, AssignedProfile = %s, FileModificationTime = %s, "
            "    LastModifiedDate = COALESCE(%s, LastModifiedDate), "
            "    TotalFrames = %s, CodecProfile = %s, ColorRange = %s, FieldOrder = %s, "
            "    HasBFrames = %s, RefFrames = %s, PixelFormat = %s, Level = %s, "
            "    AudioChannels = %s, AudioSampleRate = %s, AudioSampleFormat = %s, "
            "    AudioChannelLayout = %s, AudioCodec = %s, "
            "    AudioLanguages = COALESCE(%s, AudioLanguages), "
            "    HasExplicitEnglishAudio = COALESCE(%s, HasExplicitEnglishAudio), "
            "    SubtitleFormats = %s, ContainerFormat = %s, OverallBitrate = %s, "
            "    TranscodedByMediaVortex = %s, "
            "    AudioNormalizationMode = COALESCE(%s, AudioNormalizationMode) "
            "WHERE Id = %s",
            (
                MediaFile.SeasonId, MediaFile.StorageRootId, MediaFile.RelativePath,
                MediaFile.FileName, MediaFile.SizeMB, MediaFile.FileSize,
                MediaFile.VideoBitrateKbps, MediaFile.AudioBitrateKbps, MediaFile.Resolution,
                MediaFile.ResolutionCategory, MediaFile.IsInterlaced,
                MediaFile.Codec, MediaFile.DurationMinutes, MediaFile.FrameRate,
                MediaFile.LastScannedDate, MediaFile.CompressionPotential, MediaFile.AssignedProfile,
                MediaFile.FileModificationTime, MediaFile.LastModifiedDate,
                MediaFile.TotalFrames, MediaFile.CodecProfile,
                MediaFile.ColorRange, MediaFile.FieldOrder, MediaFile.HasBFrames, MediaFile.RefFrames,
                MediaFile.PixelFormat, MediaFile.Level, MediaFile.AudioChannels, MediaFile.AudioSampleRate,
                MediaFile.AudioSampleFormat, MediaFile.AudioChannelLayout, MediaFile.AudioCodec,
                MediaFile.AudioLanguages, MediaFile.HasExplicitEnglishAudio,
                MediaFile.SubtitleFormats, MediaFile.ContainerFormat,
                MediaFile.OverallBitrate, MediaFile.TranscodedByMediaVortex,
                MediaFile.AudioNormalizationMode, MediaFile.Id,
            ),
        )
        connection.commit()
        return MediaFile.Id

    # directive: path-schema-migration | # see path.S8
    def CleanupDuplicateMediaFiles(self) -> Dict[str, Any]:
        """Dedupe by typed pair, keeping the best record; ensure unique index on (StorageRootId, RelativePath)."""
        import psycopg2.extras
        connection = self.DatabaseService.GetConnection()
        try:
            cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(
                "SELECT StorageRootId, RelativePath, COUNT(*) AS cnt "
                "FROM MediaFiles "
                "WHERE StorageRootId IS NOT NULL AND RelativePath IS NOT NULL "
                "GROUP BY StorageRootId, RelativePath "
                "HAVING COUNT(*) > 1"
            )
            groups = cursor.fetchall()
            if not groups:
                cursor.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_mediafiles_typedpair_unique "
                    "ON MediaFiles (StorageRootId, RelativePath)"
                )
                connection.commit()
                return {'Success': True, 'DuplicatesRemoved': 0, 'Message': 'No duplicates'}
            cursor.execute("SELECT DISTINCT MediaFileId FROM TranscodeAttempts WHERE MediaFileId IS NOT NULL")
            transcoded = {r['mediafileid'] for r in cursor.fetchall()}
            metaCols = [
                'sizemb', 'videobitratekbps', 'audiobitratekbps', 'resolution', 'codec',
                'durationminutes', 'framerate', 'compressionpotential', 'assignedprofile',
                'totalframes', 'codecprofile', 'colorrange', 'fieldorder', 'hasbframes',
                'refframes', 'pixelformat', 'level', 'audiochannels', 'audiosamplerate',
                'audiosampleformat', 'audiochannellayout', 'containerformat', 'overallbitrate',
            ]
            removed = 0
            for g in groups:
                cursor.execute(
                    "SELECT * FROM MediaFiles WHERE StorageRootId = %s AND RelativePath = %s ORDER BY Id",
                    (g['storagerootid'], g['relativepath'])
                )
                records = cursor.fetchall()
                if len(records) < 2:
                    continue
                best = None
                bestKey = None
                for rec in records:
                    key = (
                        1 if rec['id'] in transcoded else 0,
                        rec.get('lastscanneddate') or '',
                        sum(1 for c in metaCols if rec.get(c) is not None),
                    )
                    if bestKey is None or key > bestKey:
                        best = rec
                        bestKey = key
                keptId = best['id']
                deleteIds = [r['id'] for r in records if r['id'] != keptId]
                if not deleteIds:
                    continue
                placeholders = ','.join(['%s'] * len(deleteIds))
                cursor.execute(
                    f"UPDATE MediaFilesArchive SET Id = %s WHERE Id IN ({placeholders})",
                    [keptId] + deleteIds
                )
                cursor.execute(
                    f"DELETE FROM MediaFiles WHERE Id IN ({placeholders})",
                    deleteIds
                )
                removed += len(deleteIds)
            connection.commit()
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_mediafiles_typedpair_unique "
                "ON MediaFiles (StorageRootId, RelativePath)"
            )
            connection.commit()
            return {'Success': True, 'DuplicatesRemoved': removed, 'DuplicateGroups': len(groups)}
        finally:
            self.DatabaseService.CloseConnection(connection)

    # directive: path-schema-migration | # see path.S8
    def GetMediaFilesByRootFolder(self, RootFolderPath: str) -> List[MediaFileModel]:
        """All MediaFiles whose RelativePath starts with the prefix derived from RootFolderPath."""
        P = _ParsePath(RootFolderPath)
        if P is None:
            return []
        prefix = (P.RelativePath or '').rstrip('/').rstrip('\\')
        escaped = EscapeLikePattern(prefix)
        likePattern = f"{escaped}%" if not prefix else f"{escaped}/%"
        query = (
            f"SELECT {_FULL_SELECT_COLS} FROM MediaFiles "
            "WHERE StorageRootId = %s AND RelativePath LIKE %s ESCAPE '!'"
        )
        rows = self.DatabaseService.ExecuteQuery(query, (P.StorageRootId, likePattern))
        return [self._MapRowToMediaFile(r) for r in rows]

    # directive: path-schema-migration | # see path.S8
    def GetMediaFilesByRootFolderId(self, RootFolderId: int) -> List[MediaFileModel]:
        """All MediaFiles for a RootFolders row by Id."""
        rfRows = self.DatabaseService.ExecuteQuery(
            "SELECT RootFolder FROM RootFolders WHERE Id = %s", (RootFolderId,)
        )
        if not rfRows:
            return []
        return self.GetMediaFilesByRootFolder(rfRows[0]['RootFolder'])

    # directive: path-schema-migration | # see path.S8
    def UpdateMediaFilesProfileByRootFolder(self, RootFolderPath: str, ProfileId: int) -> int:
        """Bulk-assign profile name to all MediaFiles whose RelativePath starts with the root prefix."""
        profileRows = self.DatabaseService.ExecuteQuery(
            "SELECT ProfileName FROM Profiles WHERE Id = %s", (ProfileId,)
        )
        profileName = profileRows[0]['ProfileName'] if profileRows else f"ProfileId_{ProfileId}"
        P = _ParsePath(RootFolderPath)
        if P is None:
            LoggingService.LogWarning(
                f"UpdateMediaFilesProfileByRootFolder: could not parse {RootFolderPath!r}",
                "MediaFilesRepository", "UpdateMediaFilesProfileByRootFolder"
            )
            return 0
        prefix = (P.RelativePath or '').rstrip('/').rstrip('\\')
        escaped = EscapeLikePattern(prefix)
        likePattern = f"{escaped}%" if not prefix else f"{escaped}/%"
        return self.DatabaseService.ExecuteNonQuery(
            "UPDATE MediaFiles SET AssignedProfile = %s "
            "WHERE StorageRootId = %s AND RelativePath LIKE %s ESCAPE '!'",
            (profileName, P.StorageRootId, likePattern)
        )

    # directive: path-schema-migration | # see path.S8
    def GetMediaFileByFileName(self, FileName: str) -> Optional[Dict[str, Any]]:
        """3-tier filename match (exact, no-extension, fuzzy-episode-prefix); returns a summary dict or None."""
        cols = (
            "Id, FileName, StorageRootId, RelativePath, ContainerFormat, Codec, AudioCodec, "
            "TranscodedByMediaVortex, SubtitleFormats"
        )
        rows = self.DatabaseService.ExecuteQuery(
            f"SELECT {cols} FROM MediaFiles WHERE LOWER(FileName) = LOWER(%s) LIMIT 1", (FileName,)
        )
        if rows:
            return self._MapSummaryRow(rows[0], "exact")
        nameNoExt = LocalSplitExt(FileName)[0]
        likeSql = (
            f"SELECT {cols} FROM MediaFiles "
            "WHERE LOWER(FileName) LIKE LOWER(%s) ESCAPE '!' LIMIT 1"
        )
        rows = self.DatabaseService.ExecuteQuery(likeSql, (EscapeLikePattern(nameNoExt) + '%',))
        if rows:
            return self._MapSummaryRow(rows[0], "no_ext")
        epPrefix = self._ExtractEpisodePrefix(FileName)
        if epPrefix and epPrefix != nameNoExt:
            rows = self.DatabaseService.ExecuteQuery(likeSql, (EscapeLikePattern(epPrefix) + '%',))
            if rows:
                return self._MapSummaryRow(rows[0], "fuzzy")
        return None

    # directive: path-schema-migration | # see path.S8
    def _MapSummaryRow(self, row, matchType: str) -> Dict[str, Any]:
        """Project a row to a small summary dict; FilePath computed via Path.CanonicalDisplay."""
        sid = row.get('StorageRootId') or row.get('storagerootid')
        rel = row.get('RelativePath') or row.get('relativepath') or ''
        filePath = ''
        if sid is not None:
            try:
                filePath = Path(sid, rel).CanonicalDisplay(GetPrefixMap())
            except PathError:
                filePath = ''
        return {
            "Id": row.get('Id') or row.get('id'),
            "FileName": row.get('FileName') or row.get('filename'),
            "FilePath": filePath,
            "StorageRootId": sid,
            "RelativePath": rel,
            "ContainerFormat": row.get('ContainerFormat') or row.get('containerformat'),
            "Codec": row.get('Codec') or row.get('codec'),
            "AudioCodec": row.get('AudioCodec') or row.get('audiocodec'),
            "TranscodedByMediaVortex": row.get('TranscodedByMediaVortex') if 'TranscodedByMediaVortex' in row else row.get('transcodedbymediavortex'),
            "SubtitleFormats": row.get('SubtitleFormats') or row.get('subtitleformats'),
            "MatchType": matchType,
        }

    # directive: path-schema-migration | # see path.S8
    def _ExtractEpisodePrefix(self, FileName: str) -> Optional[str]:
        """Extract a 'Show - S<N>E<N>' or 'Show - <S>x<EE>' fuzzy prefix for retry matching."""
        m = re.search(r'(.*?S\d{1,2}E\d{1,2})', FileName, re.IGNORECASE)
        if m:
            return m.group(1).strip(' -_.')
        m = re.search(r'(.*?\d{1,2}x\d{2})', FileName, re.IGNORECASE)
        if m:
            return m.group(1).strip(' -_.')
        return None

    # directive: path-schema-migration | # see path.S8
    def GetFullMediaFileByFileName(self, FileName: str) -> Optional[MediaFileModel]:
        """Full MediaFileModel by filename with the same 3-tier matching as GetMediaFileByFileName."""
        cols = _FULL_SELECT_COLS
        rows = self.DatabaseService.ExecuteQuery(
            f"SELECT {cols} FROM MediaFiles WHERE LOWER(FileName) = LOWER(%s) LIMIT 1", (FileName,)
        )
        if not rows:
            nameNoExt = LocalSplitExt(FileName)[0]
            likeSql = (
                f"SELECT {cols} FROM MediaFiles "
                "WHERE LOWER(FileName) LIKE LOWER(%s) ESCAPE '!' LIMIT 1"
            )
            rows = self.DatabaseService.ExecuteQuery(likeSql, (EscapeLikePattern(nameNoExt) + '%',))
            if not rows:
                epPrefix = self._ExtractEpisodePrefix(FileName)
                if epPrefix and epPrefix != nameNoExt:
                    rows = self.DatabaseService.ExecuteQuery(likeSql, (EscapeLikePattern(epPrefix) + '%',))
        return self._MapRowToMediaFile(rows[0]) if rows else None

    # directive: path-schema-migration | # see path.S8
    def GetAllSeasons(self) -> List[SeasonModel]:
        """Return every Seasons row."""
        rows = self.DatabaseService.ExecuteQuery(
            "SELECT Id, RootFolderId, SeasonName FROM Seasons ORDER BY RootFolderId, SeasonName"
        )
        return [SeasonModel(Id=r['Id'], RootFolderId=r['RootFolderId'], SeasonName=r['SeasonName']) for r in rows]

    # directive: path-schema-migration | # see path.S8
    def GetSeasonById(self, SeasonId: int) -> Optional[SeasonModel]:
        """Return one Seasons row by Id."""
        rows = self.DatabaseService.ExecuteQuery(
            "SELECT Id, RootFolderId, SeasonName FROM Seasons WHERE Id = %s", (SeasonId,)
        )
        if not rows:
            return None
        r = rows[0]
        return SeasonModel(Id=r['Id'], RootFolderId=r['RootFolderId'], SeasonName=r['SeasonName'])

    # directive: path-schema-migration | # see path.S8
    def GetSeasonsByRootFolder(self, RootFolderId: int) -> List[SeasonModel]:
        """All Seasons rows for a RootFolders row by Id."""
        rows = self.DatabaseService.ExecuteQuery(
            "SELECT Id, RootFolderId, SeasonName FROM Seasons WHERE RootFolderId = %s ORDER BY SeasonName",
            (RootFolderId,)
        )
        return [SeasonModel(Id=r['Id'], RootFolderId=r['RootFolderId'], SeasonName=r['SeasonName']) for r in rows]

    # directive: path-schema-migration | # see path.S8
    def SaveSeason(self, Season: SeasonModel) -> int:
        """Insert or update a Seasons row by Id; return the row Id."""
        if Season.Id is None:
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()
                cursor.execute(
                    "INSERT INTO Seasons (RootFolderId, SeasonName) VALUES (%s, %s) RETURNING Id",
                    (Season.RootFolderId, Season.SeasonName)
                )
                newId = cursor.fetchone()[0]
                connection.commit()
                return newId
            finally:
                self.DatabaseService.CloseConnection(connection)
        self.DatabaseService.ExecuteNonQuery(
            "UPDATE Seasons SET RootFolderId = %s, SeasonName = %s WHERE Id = %s",
            (Season.RootFolderId, Season.SeasonName, Season.Id)
        )
        return Season.Id

    # directive: path-schema-migration | # see path.S8
    def DeleteSeason(self, SeasonId: int) -> bool:
        """Delete a Seasons row by Id."""
        affected = self.DatabaseService.ExecuteNonQuery(
            "DELETE FROM Seasons WHERE Id = %s", (SeasonId,)
        )
        return affected > 0

    # directive: work-transcode-unified | # see work-bucket.G1
    def PropagateSeriesProfile(self, Identity, ProfileName: str) -> int:
        """UPDATE MediaFiles.AssignedProfile for every untranscoded file in the series. Returns rowcount."""
        Affected = self.DatabaseService.ExecuteNonQuery(
            "UPDATE MediaFiles "
            "   SET AssignedProfile = %s, "
            "       AssignedProfileSource = 'series', "
            "       LastModifiedDate = NOW() "
            " WHERE StorageRootId = %s "
            "   AND split_part(RelativePath, '/', 1) = %s "
            "   AND TranscodedByMediaVortex IS NOT TRUE",
            (ProfileName, Identity.StorageRootId, Identity.RelativePath),
        )
        return int(Affected) if Affected is not None else 0
