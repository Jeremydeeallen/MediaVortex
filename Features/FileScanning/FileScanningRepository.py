import os
import re
from typing import Optional, List, Dict, Any
from Core.Database.BaseRepository import BaseRepository
from Core.Logging.LoggingService import LoggingService
from Core.Models.MediaFileModel import MediaFileModel
from Features.FileScanning.Models.RootFolderModel import RootFolderModel
from Features.FileScanning.Models.SeasonModel import SeasonModel


class FileScanningRepository(BaseRepository):
    """Repository for FileScanning-related database operations."""

    # ─── Root Folder Methods ───────────────────────────────────────────

    def GetAllRootFolders(self, SortColumn='RootFolder', SortOrder='ASC') -> List[RootFolderModel]:
        ValidColumns = ['Id', 'RootFolder', 'LastScannedDate', 'TotalSizeGB']
        if SortColumn not in ValidColumns:
            SortColumn = 'RootFolder'
        if SortOrder.upper() not in ['ASC', 'DESC']:
            SortOrder = 'ASC'
        query = f"SELECT Id, RootFolder, LastScannedDate, TotalSizeGB FROM RootFolders ORDER BY {SortColumn} {SortOrder.upper()}"
        rows = self.ExecuteQuery(query)
        rootFolders = []
        for row in rows:
            rootFolder = RootFolderModel(Id=row['Id'], RootFolder=row['RootFolder'], LastScannedDate=row['LastScannedDate'], TotalSizeGB=row['TotalSizeGB'])
            rootFolders.append(rootFolder)
        return rootFolders

    def GetRootFolderById(self, RootFolderId: int) -> Optional[RootFolderModel]:
        query = "SELECT Id, RootFolder, LastScannedDate, TotalSizeGB FROM RootFolders WHERE Id = %s"
        rows = self.ExecuteQuery(query, (RootFolderId,))
        if not rows:
            return None
        row = rows[0]
        return RootFolderModel(Id=row['Id'], RootFolder=row['RootFolder'], LastScannedDate=row['LastScannedDate'], TotalSizeGB=row['TotalSizeGB'])

    def SaveRootFolder(self, RootFolder: RootFolderModel) -> int:
        try:
            RootFolder.RootFolder = self.NormalizePathToFilesystemCase(RootFolder.RootFolder)
            LoggingService.LogFunctionEntry("SaveRootFolder", 'FileScanningRepository', f"RootFolder: {RootFolder.RootFolder}, Size: {RootFolder.TotalSizeGB}GB")
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()
                if RootFolder.Id is None:
                    LoggingService.LogInfo("Inserting new root folder...")
                    query = """INSERT INTO RootFolders (RootFolder, LastScannedDate, TotalSizeGB) VALUES (%s, %s, %s) RETURNING Id"""
                    parameters = (RootFolder.RootFolder, RootFolder.LastScannedDate, RootFolder.TotalSizeGB)
                    LoggingService.LogInfo("Insert root folder parameters: {}", "FileScanningRepository", "SaveRootFolder", parameters)
                    cursor.execute(query, parameters)
                    rootFolderId = cursor.fetchone()[0]
                    connection.commit()
                    LoggingService.LogInfo("Root folder inserted with ID: {}", "FileScanningRepository", "SaveRootFolder", rootFolderId)
                    return rootFolderId
                else:
                    LoggingService.LogInfo("Updating existing root folder with ID: {}", "FileScanningRepository", "SaveRootFolder", RootFolder.Id)
                    query = """UPDATE RootFolders SET RootFolder = %s, LastScannedDate = %s, TotalSizeGB = %s WHERE Id = %s"""
                    parameters = (RootFolder.RootFolder, RootFolder.LastScannedDate, RootFolder.TotalSizeGB, RootFolder.Id)
                    LoggingService.LogInfo(f"Update root folder parameters: {parameters}", "FileScanningRepository", "SaveRootFolder")
                    cursor.execute(query, parameters)
                    connection.commit()
                    affectedRows = cursor.rowcount
                    LoggingService.LogInfo("Root folder update affected {} rows", "FileScanningRepository", "SaveRootFolder", affectedRows)
                    return RootFolder.Id
            finally:
                self.DatabaseService.CloseConnection(connection)
        except Exception as e:
            LoggingService.LogException("Exception in SaveRootFolder", e, "FileScanningRepository", "SaveRootFolder")
            raise

    def DeleteRootFolder(self, RootFolderId: int) -> bool:
        try:
            self.ExecuteNonQuery("DELETE FROM MediaFiles WHERE Id IN (SELECT Id FROM MediaFiles WHERE LOWER(FilePath) LIKE LOWER((SELECT RootFolder FROM RootFolders WHERE Id = %s)) || '%%' ESCAPE '!')", (RootFolderId,))
            affectedRows = self.ExecuteNonQuery("DELETE FROM RootFolders WHERE Id = %s", (RootFolderId,))
            return affectedRows > 0
        except Exception:
            return False

    # ─── Media File Methods ────────────────────────────────────────────

    def _MapRowToMediaFile(self, row) -> MediaFileModel:
        """Map a database row to a MediaFileModel instance."""
        return MediaFileModel(
            Id=row['Id'], SeasonId=row['SeasonId'], FilePath=row['FilePath'],
            FileName=row['FileName'], SizeMB=row['SizeMB'],
            VideoBitrateKbps=row['VideoBitrateKbps'], AudioBitrateKbps=row['AudioBitrateKbps'],
            Resolution=row['Resolution'], Codec=row['Codec'],
            DurationMinutes=row['DurationMinutes'], FrameRate=row['FrameRate'],
            LastScannedDate=row['LastScannedDate'], CompressionPotential=row['CompressionPotential'],
            AssignedProfile=row['AssignedProfile'], IsInterlaced=row['IsInterlaced'],
            ResolutionCategory=row['ResolutionCategory'], FileModificationTime=row['FileModificationTime'],
            TotalFrames=row['TotalFrames'], CodecProfile=row['CodecProfile'],
            ColorRange=row['ColorRange'], FieldOrder=row['FieldOrder'],
            HasBFrames=row['HasBFrames'], RefFrames=row['RefFrames'],
            PixelFormat=row['PixelFormat'], Level=row['Level'],
            AudioChannels=row['AudioChannels'], AudioSampleRate=row['AudioSampleRate'],
            AudioSampleFormat=row['AudioSampleFormat'], AudioChannelLayout=row['AudioChannelLayout'],
            AudioCodec=row['AudioCodec'], SubtitleFormats=row['SubtitleFormats'],
            ContainerFormat=row['ContainerFormat'], OverallBitrate=row['OverallBitrate'],
            TranscodedByMediaVortex=row['TranscodedByMediaVortex']
        )

    _MEDIA_FILE_SELECT_COLS = """Id, SeasonId, FilePath, FileName, SizeMB, VideoBitrateKbps, AudioBitrateKbps,
                   Resolution, Codec, DurationMinutes, FrameRate, LastScannedDate,
                   CompressionPotential, AssignedProfile, IsInterlaced, ResolutionCategory,
                   FileModificationTime, TotalFrames, CodecProfile, ColorRange, FieldOrder,
                   HasBFrames, RefFrames, PixelFormat, Level, AudioChannels, AudioSampleRate,
                   AudioSampleFormat, AudioChannelLayout, AudioCodec, SubtitleFormats,
                   ContainerFormat, OverallBitrate, TranscodedByMediaVortex"""

    def GetAllMediaFiles(self) -> List[MediaFileModel]:
        query = f"SELECT {self._MEDIA_FILE_SELECT_COLS} FROM MediaFiles"
        rows = self.ExecuteQuery(query)
        return [self._MapRowToMediaFile(row) for row in rows]

    def GetMediaFileById(self, MediaFileId: int) -> Optional[MediaFileModel]:
        query = f"SELECT {self._MEDIA_FILE_SELECT_COLS} FROM MediaFiles WHERE Id = %s"
        rows = self.ExecuteQuery(query, (MediaFileId,))
        if not rows:
            return None
        return self._MapRowToMediaFile(rows[0])

    def GetMediaFileByPath(self, FilePath: str) -> Optional[MediaFileModel]:
        query = f"SELECT {self._MEDIA_FILE_SELECT_COLS} FROM MediaFiles WHERE LOWER(FilePath) = LOWER(%s)"
        rows = self.ExecuteQuery(query, (FilePath,))
        if not rows:
            return None
        return self._MapRowToMediaFile(rows[0])

    def GetMediaFilesByRootFolder(self, RootFolderPath: str) -> List[MediaFileModel]:
        query = f"SELECT {self._MEDIA_FILE_SELECT_COLS} FROM MediaFiles WHERE LOWER(FilePath) LIKE LOWER(%s) ESCAPE '!'"
        rows = self.ExecuteQuery(query, (f"{RootFolderPath}%",))
        return [self._MapRowToMediaFile(row) for row in rows]

    def GetMediaFilesByRootFolderId(self, RootFolderId: int) -> List[MediaFileModel]:
        rootFolder = self.GetRootFolderById(RootFolderId)
        if not rootFolder:
            return []
        return self.GetMediaFilesByRootFolder(rootFolder.RootFolder)

    def SaveMediaFile(self, MediaFile: MediaFileModel) -> int:
        try:
            MediaFile.FilePath = self.NormalizePathToFilesystemCase(MediaFile.FilePath)
            LoggingService.LogFunctionEntry("SaveMediaFile", 'FileScanningRepository', f"File: {MediaFile.FileName}, Path: {MediaFile.FilePath}")
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()
                if MediaFile.Id is None:
                    checkQuery = "SELECT Id FROM MediaFiles WHERE LOWER(FilePath) = LOWER(%s)"
                    cursor.execute(checkQuery, (MediaFile.FilePath,))
                    existingRow = cursor.fetchone()
                    if existingRow:
                        MediaFile.Id = existingRow['Id']
                        LoggingService.LogInfo(f"Duplicate prevented: file already exists with ID {MediaFile.Id}, converting to update: {MediaFile.FilePath}", "FileScanningRepository", "SaveMediaFile")
                        # Fall through to update branch
                    else:
                        # Insert
                        query = """INSERT INTO MediaFiles (SeasonId, FilePath, FileName, SizeMB, VideoBitrateKbps, AudioBitrateKbps, Resolution, Codec, DurationMinutes, FrameRate, LastScannedDate, CompressionPotential, AssignedProfile, FileModificationTime, TotalFrames, CodecProfile, ColorRange, FieldOrder, HasBFrames, RefFrames, PixelFormat, Level, AudioChannels, AudioSampleRate, AudioSampleFormat, AudioChannelLayout, AudioCodec, SubtitleFormats, ContainerFormat, OverallBitrate, TranscodedByMediaVortex) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING Id"""
                        parameters = (MediaFile.SeasonId, MediaFile.FilePath, MediaFile.FileName, MediaFile.SizeMB, MediaFile.VideoBitrateKbps, MediaFile.AudioBitrateKbps, MediaFile.Resolution, MediaFile.Codec, MediaFile.DurationMinutes, MediaFile.FrameRate, MediaFile.LastScannedDate, MediaFile.CompressionPotential, MediaFile.AssignedProfile, MediaFile.FileModificationTime, MediaFile.TotalFrames, MediaFile.CodecProfile, MediaFile.ColorRange, MediaFile.FieldOrder, MediaFile.HasBFrames, MediaFile.RefFrames, MediaFile.PixelFormat, MediaFile.Level, MediaFile.AudioChannels, MediaFile.AudioSampleRate, MediaFile.AudioSampleFormat, MediaFile.AudioChannelLayout, MediaFile.AudioCodec, MediaFile.SubtitleFormats, MediaFile.ContainerFormat, MediaFile.OverallBitrate, MediaFile.TranscodedByMediaVortex)
                        cursor.execute(query, parameters)
                        mediaFileId = cursor.fetchone()[0]
                        connection.commit()
                        return mediaFileId
                # Update (either explicit update or duplicate converted to update)
                if MediaFile.Id is not None:
                    query = """UPDATE MediaFiles SET SeasonId = %s, FilePath = %s, FileName = %s, SizeMB = %s, VideoBitrateKbps = %s, AudioBitrateKbps = %s, Resolution = %s, Codec = %s, DurationMinutes = %s, FrameRate = %s, LastScannedDate = %s, CompressionPotential = %s, AssignedProfile = %s, FileModificationTime = %s, TotalFrames = %s, CodecProfile = %s, ColorRange = %s, FieldOrder = %s, HasBFrames = %s, RefFrames = %s, PixelFormat = %s, Level = %s, AudioChannels = %s, AudioSampleRate = %s, AudioSampleFormat = %s, AudioChannelLayout = %s, AudioCodec = %s, SubtitleFormats = %s, ContainerFormat = %s, OverallBitrate = %s, TranscodedByMediaVortex = %s WHERE Id = %s"""
                    parameters = (MediaFile.SeasonId, MediaFile.FilePath, MediaFile.FileName, MediaFile.SizeMB, MediaFile.VideoBitrateKbps, MediaFile.AudioBitrateKbps, MediaFile.Resolution, MediaFile.Codec, MediaFile.DurationMinutes, MediaFile.FrameRate, MediaFile.LastScannedDate, MediaFile.CompressionPotential, MediaFile.AssignedProfile, MediaFile.FileModificationTime, MediaFile.TotalFrames, MediaFile.CodecProfile, MediaFile.ColorRange, MediaFile.FieldOrder, MediaFile.HasBFrames, MediaFile.RefFrames, MediaFile.PixelFormat, MediaFile.Level, MediaFile.AudioChannels, MediaFile.AudioSampleRate, MediaFile.AudioSampleFormat, MediaFile.AudioChannelLayout, MediaFile.AudioCodec, MediaFile.SubtitleFormats, MediaFile.ContainerFormat, MediaFile.OverallBitrate, MediaFile.TranscodedByMediaVortex, MediaFile.Id)
                    cursor.execute(query, parameters)
                    connection.commit()
                    return MediaFile.Id
            finally:
                self.DatabaseService.CloseConnection(connection)
        except Exception as e:
            LoggingService.LogException("Exception in SaveMediaFile", e, "FileScanningRepository", "SaveMediaFile")
            raise

    def DeleteMediaFile(self, MediaFileId: int) -> bool:
        affectedRows = self.ExecuteNonQuery("DELETE FROM MediaFiles WHERE Id = %s", (MediaFileId,))
        return affectedRows > 0

    def DeleteMediaFileByPath(self, FilePath: str) -> bool:
        affectedRows = self.ExecuteNonQuery("DELETE FROM MediaFiles WHERE LOWER(FilePath) = LOWER(%s)", (FilePath,))
        return affectedRows > 0

    def GetTotalMediaFileCount(self) -> int:
        query = "SELECT COUNT(*) as Count FROM MediaFiles"
        rows = self.ExecuteQuery(query)
        return rows[0]['Count'] if rows else 0

    def CleanupDuplicateMediaFiles(self) -> Dict[str, Any]:
        """Remove duplicate MediaFiles rows, keeping the best record for each FilePath.

        Selection priority (highest to lowest):
        1. Has a matching TranscodeAttempts record (linked to transcode history)
        2. Most recent LastScannedDate (reflects current file state post-transcode)
        3. Most non-NULL metadata columns (most complete probe data)

        Updates MediaFilesArchive references to point to the kept record before
        deleting duplicates.
        """
        try:
            connection = self.DatabaseService.GetConnection()
            try:
                import psycopg2.extras
                cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

                # Find all duplicate groups (FilePaths with more than one record)
                cursor.execute("""
                    SELECT LOWER(FilePath) as normalizedpath, COUNT(*) as cnt
                    FROM MediaFiles
                    GROUP BY LOWER(FilePath)
                    HAVING COUNT(*) > 1
                """)
                DuplicateGroups = cursor.fetchall()

                if not DuplicateGroups:
                    LoggingService.LogInfo("No duplicate media files found", "FileScanningRepository", "CleanupDuplicateMediaFiles")
                    return {
                        'Success': True,
                        'DuplicatesRemoved': 0,
                        'Message': 'No duplicates found'
                    }

                # Build a set of FilePaths that have TranscodeAttempts records
                cursor.execute("SELECT DISTINCT FilePath FROM TranscodeAttempts")
                TranscodedPaths = {row['filepath'] for row in cursor.fetchall()}

                MetadataColumns = [
                    'SeasonId', 'SizeMB', 'VideoBitrateKbps', 'AudioBitrateKbps',
                    'Resolution', 'Codec', 'DurationMinutes', 'FrameRate',
                    'CompressionPotential', 'AssignedProfile', 'TotalFrames',
                    'CodecProfile', 'ColorRange', 'FieldOrder', 'HasBFrames',
                    'RefFrames', 'PixelFormat', 'Level', 'AudioChannels',
                    'AudioSampleRate', 'AudioSampleFormat', 'AudioChannelLayout',
                    'ContainerFormat', 'OverallBitrate'
                ]

                TotalRemoved = 0

                for group in DuplicateGroups:
                    NormalizedPath = group['normalizedpath']

                    # Get all records for this path
                    cursor.execute("""
                        SELECT * FROM MediaFiles WHERE LOWER(FilePath) = %s
                        ORDER BY Id
                    """, (NormalizedPath,))
                    Records = cursor.fetchall()

                    if len(Records) < 2:
                        continue

                    # Score each record with a tuple for natural ordering:
                    # (has_transcode_link, scan_date, metadata_completeness)
                    BestRecord = None
                    BestKey = None

                    for record in Records:
                        HasTranscodeLink = 1 if record['filepath'] in TranscodedPaths else 0
                        ScanDate = record['lastscanneddate'] or ''
                        MetadataScore = sum(1 for col in MetadataColumns if record.get(col.lower()) is not None)

                        Key = (HasTranscodeLink, ScanDate, MetadataScore)

                        if BestKey is None or Key > BestKey:
                            BestKey = Key
                            BestRecord = record

                    KeptId = BestRecord['id']
                    DeleteIds = [r['id'] for r in Records if r['id'] != KeptId]

                    if not DeleteIds:
                        continue

                    # Update MediaFilesArchive: reassign any references from deleted IDs to kept ID
                    Placeholders = ','.join(['%s'] * len(DeleteIds))
                    cursor.execute(f"""
                        UPDATE MediaFilesArchive
                        SET Id = %s
                        WHERE Id IN ({Placeholders})
                    """, [KeptId] + DeleteIds)

                    # Delete the duplicate records
                    cursor.execute(f"""
                        DELETE FROM MediaFiles WHERE Id IN ({Placeholders})
                    """, DeleteIds)

                    TotalRemoved += len(DeleteIds)

                connection.commit()
                LoggingService.LogInfo(
                    f"Cleaned up {TotalRemoved} duplicate media file records across {len(DuplicateGroups)} groups",
                    "FileScanningRepository", "CleanupDuplicateMediaFiles"
                )

                # Create unique index to prevent future duplicates
                try:
                    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_mediafiles_filepath_unique ON MediaFiles (LOWER(FilePath))")
                    connection.commit()
                    LoggingService.LogInfo("Created unique index on MediaFiles.FilePath", "FileScanningRepository", "CleanupDuplicateMediaFiles")
                except Exception as IndexError:
                    LoggingService.LogWarning(
                        f"Could not create unique index (may already exist or duplicates remain): {str(IndexError)}",
                        "FileScanningRepository", "CleanupDuplicateMediaFiles"
                    )

                return {
                    'Success': True,
                    'DuplicatesRemoved': TotalRemoved,
                    'DuplicateGroups': len(DuplicateGroups),
                    'Message': f'Removed {TotalRemoved} duplicate records from {len(DuplicateGroups)} groups'
                }
            finally:
                self.DatabaseService.CloseConnection(connection)
        except Exception as e:
            LoggingService.LogException("Error cleaning up duplicate media files", e, "FileScanningRepository", "CleanupDuplicateMediaFiles")
            return {
                'Success': False,
                'DuplicatesRemoved': 0,
                'Message': f'Error: {str(e)}'
            }

    # ─── Season Methods ────────────────────────────────────────────────

    def GetAllSeasons(self) -> List[SeasonModel]:
        query = "SELECT Id, RootFolderId, SeasonName FROM Seasons ORDER BY RootFolderId, SeasonName"
        rows = self.ExecuteQuery(query)
        seasons = []
        for row in rows:
            season = SeasonModel(Id=row['Id'], RootFolderId=row['RootFolderId'], SeasonName=row['SeasonName'])
            seasons.append(season)
        return seasons

    def GetSeasonById(self, SeasonId: int) -> Optional[SeasonModel]:
        query = "SELECT Id, RootFolderId, SeasonName FROM Seasons WHERE Id = %s"
        rows = self.ExecuteQuery(query, (SeasonId,))
        if not rows:
            return None
        row = rows[0]
        return SeasonModel(Id=row['Id'], RootFolderId=row['RootFolderId'], SeasonName=row['SeasonName'])

    def SaveSeason(self, Season: SeasonModel) -> int:
        try:
            LoggingService.LogFunctionEntry("SaveSeason", 'FileScanningRepository', f"Season: {Season.SeasonName}, RootFolderId: {Season.RootFolderId}")
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()
                if Season.Id is None:
                    query = """INSERT INTO Seasons (RootFolderId, SeasonName) VALUES (%s, %s) RETURNING Id"""
                    parameters = (Season.RootFolderId, Season.SeasonName)
                    cursor.execute(query, parameters)
                    seasonId = cursor.fetchone()[0]
                    connection.commit()
                    return seasonId
                else:
                    query = """UPDATE Seasons SET RootFolderId = %s, SeasonName = %s WHERE Id = %s"""
                    parameters = (Season.RootFolderId, Season.SeasonName, Season.Id)
                    cursor.execute(query, parameters)
                    connection.commit()
                    return Season.Id
            finally:
                self.DatabaseService.CloseConnection(connection)
        except Exception as e:
            LoggingService.LogException("Exception in SaveSeason", e, "FileScanningRepository", "SaveSeason")
            raise

    def DeleteSeason(self, SeasonId: int) -> bool:
        affectedRows = self.ExecuteNonQuery("DELETE FROM Seasons WHERE Id = %s", (SeasonId,))
        return affectedRows > 0

    def GetSeasonsByRootFolder(self, RootFolderId: int) -> List[SeasonModel]:
        query = "SELECT Id, RootFolderId, SeasonName FROM Seasons WHERE RootFolderId = %s ORDER BY SeasonName"
        rows = self.ExecuteQuery(query, (RootFolderId,))
        seasons = []
        for row in rows:
            season = SeasonModel(Id=row['Id'], RootFolderId=row['RootFolderId'], SeasonName=row['SeasonName'])
            seasons.append(season)
        return seasons

    # ─── Scan Directory Methods ────────────────────────────────────────

    def GetScanDirectories(self) -> List[Dict[str, str]]:
        query = "SELECT SettingKey, SettingValue, Description FROM SystemSettings WHERE SettingKey LIKE 'ScanDir%%' ORDER BY SettingKey"
        rows = self.ExecuteQuery(query)
        scanDirs = []
        for row in rows:
            if row['SettingValue'] and row['SettingValue'].strip():
                scanDirs.append({'Key': row['SettingKey'], 'Path': row['SettingValue'], 'Description': row['Description']})
        return scanDirs

    def AddOrUpdateScanDirectory(self, SettingKey, SettingValue, Description, DataType='string') -> bool:
        try:
            query = "SELECT COUNT(*) as Count FROM SystemSettings WHERE SettingKey = %s"
            rows = self.ExecuteQuery(query, (SettingKey,))
            exists = rows[0]['Count'] > 0 if rows else False
            if exists:
                self.ExecuteNonQuery(
                    "UPDATE SystemSettings SET SettingValue = %s, Description = %s, DataType = %s WHERE SettingKey = %s",
                    (SettingValue, Description, DataType, SettingKey)
                )
            else:
                self.ExecuteNonQuery(
                    "INSERT INTO SystemSettings (SettingKey, SettingValue, Description, DataType) VALUES (%s, %s, %s, %s)",
                    (SettingKey, SettingValue, Description, DataType)
                )
            return True
        except Exception as e:
            LoggingService.LogException("Exception in AddOrUpdateScanDirectory", e, "FileScanningRepository", "AddOrUpdateScanDirectory")
            return False

    def DeleteScanDirectory(self, SettingKey) -> bool:
        try:
            affectedRows = self.ExecuteNonQuery("DELETE FROM SystemSettings WHERE SettingKey = %s", (SettingKey,))
            return affectedRows > 0
        except Exception as e:
            LoggingService.LogException("Exception in DeleteScanDirectory", e, "FileScanningRepository", "DeleteScanDirectory")
            return False

    # ─── Helper Methods ────────────────────────────────────────────────

    def NormalizePathToFilesystemCase(self, Path: str) -> str:
        """Walk path components using os.listdir to find actual filesystem case."""
        try:
            if not Path:
                return Path
            normalized_path = os.path.normpath(Path)
            if not os.path.exists(normalized_path):
                LoggingService.LogWarning(f"Path does not exist, cannot normalize: {Path}", "FileScanningRepository", "NormalizePathToFilesystemCase")
                return normalized_path
            if len(normalized_path) >= 2 and normalized_path[1] == ':':
                drive = normalized_path[0:2]
                remainder = normalized_path[2:].lstrip(os.sep)
                result_path = drive + os.sep
                if remainder:
                    parts = remainder.split(os.sep)
                else:
                    parts = []
            else:
                parts = normalized_path.split(os.sep)
                result_path = parts[0] if parts else ''
                parts = parts[1:] if parts else []
            current_path = result_path
            for part in parts:
                if not part:
                    continue
                try:
                    if os.path.isdir(current_path):
                        dir_contents = os.listdir(current_path)
                        actual_name = None
                        for item in dir_contents:
                            if item.upper() == part.upper():
                                actual_name = item
                                break
                        if actual_name:
                            current_path = os.path.join(current_path, actual_name)
                        else:
                            current_path = os.path.join(current_path, part)
                    else:
                        current_path = os.path.join(current_path, part)
                except Exception as e:
                    LoggingService.LogWarning(f"Could not list directory '{current_path}' to get actual case, using: {part}", "FileScanningRepository", "NormalizePathToFilesystemCase")
                    current_path = os.path.join(current_path, part)
            if current_path != normalized_path:
                LoggingService.LogInfo(f"Normalized path case: '{normalized_path}' -> '{current_path}'", "FileScanningRepository", "NormalizePathToFilesystemCase")
            return current_path
        except Exception as e:
            LoggingService.LogException("Error normalizing path to filesystem case", e, "FileScanningRepository", "NormalizePathToFilesystemCase")
            return Path

    def GetMediaFileByFileName(self, FileName: str) -> Optional[Dict[str, Any]]:
        """Look up a MediaFile by filename (case-insensitive) for mitigation checking.
        Tries exact match first, then fuzzy match by episode prefix if not found.
        Returns dict with MatchType: 'exact', 'no_ext', or 'fuzzy'."""
        try:
            selectCols = "Id, FileName, FilePath, ContainerFormat, Codec, AudioCodec, TranscodedByMediaVortex, SubtitleFormats"

            # 1. Exact match
            query = f"SELECT {selectCols} FROM MediaFiles WHERE LOWER(FileName) = LOWER(%s) LIMIT 1"
            rows = self.ExecuteQuery(query, (FileName,))
            if rows:
                return self._MapMediaFileSummaryRow(rows[0], "exact")

            # 2. Match without extension (handles container change: .mkv -> .mp4)
            nameNoExt = os.path.splitext(FileName)[0]
            query = f"SELECT {selectCols} FROM MediaFiles WHERE LOWER(FileName) LIKE LOWER(%s) ESCAPE '!' LIMIT 1"
            rows = self.ExecuteQuery(query, (nameNoExt + '%',))
            if rows:
                return self._MapMediaFileSummaryRow(rows[0], "no_ext")

            # 3. Fuzzy match by episode prefix (handles resolution/quality change)
            episodePrefix = self._ExtractEpisodePrefix(FileName)
            if episodePrefix and episodePrefix != nameNoExt:
                rows = self.ExecuteQuery(query, (episodePrefix + '%',))
                if rows:
                    return self._MapMediaFileSummaryRow(rows[0], "fuzzy")

            return None
        except Exception as e:
            LoggingService.LogException("Error getting media file by filename", e, "FileScanningRepository", "GetMediaFileByFileName")
            return None

    def GetFullMediaFileByFileName(self, FileName: str) -> Optional[MediaFileModel]:
        """Get full MediaFile model by filename (case-insensitive) for re-analysis.
        Uses same 3-tier fuzzy matching as GetMediaFileByFileName."""
        try:
            # 1. Exact match
            query = f"SELECT {self._MEDIA_FILE_SELECT_COLS} FROM MediaFiles WHERE LOWER(FileName) = LOWER(%s) LIMIT 1"
            rows = self.ExecuteQuery(query, (FileName,))

            # 2. Match without extension (handles container change: .mkv -> .mp4)
            if not rows:
                nameNoExt = os.path.splitext(FileName)[0]
                likeQuery = f"SELECT {self._MEDIA_FILE_SELECT_COLS} FROM MediaFiles WHERE LOWER(FileName) LIKE LOWER(%s) ESCAPE '!' LIMIT 1"
                rows = self.ExecuteQuery(likeQuery, (nameNoExt + '%',))

                # 3. Fuzzy match by episode prefix (handles resolution/quality change)
                if not rows:
                    episodePrefix = self._ExtractEpisodePrefix(FileName)
                    if episodePrefix and episodePrefix != nameNoExt:
                        rows = self.ExecuteQuery(likeQuery, (episodePrefix + '%',))

            if not rows:
                return None
            return self._MapRowToMediaFile(rows[0])
        except Exception as e:
            LoggingService.LogException("Error getting full media file by filename", e, "FileScanningRepository", "GetFullMediaFileByFileName")
            return None

    def _MapMediaFileSummaryRow(self, row, matchType: str = "exact") -> Dict[str, Any]:
        """Map a summary row to a dict for mitigation checking."""
        return {
            "Id": row['id'], "FileName": row['filename'], "FilePath": row['filepath'],
            "ContainerFormat": row['containerformat'], "Codec": row['codec'],
            "AudioCodec": row['audiocodec'], "TranscodedByMediaVortex": row['transcodedbymediavortex'],
            "SubtitleFormats": row['subtitleformats'], "MatchType": matchType
        }

    def _ExtractEpisodePrefix(self, FileName: str) -> Optional[str]:
        """Extract the show name + episode identifier from a filename for fuzzy matching.
        E.g. 'Psych - S06E01 - Shawn Rescues Darth Vader WEBRip-480p.mkv'
          -> 'Psych - S06E01'
        """
        # Match patterns like S01E05, S1E5, s01e05
        match = re.search(r'(.*\bS\d{1,2}E\d{1,2})', FileName, re.IGNORECASE)
        if match:
            return match.group(1).strip(' -_.')
        # Match patterns like "1x05", "01x05"
        match = re.search(r'(.*\b\d{1,2}x\d{2})', FileName, re.IGNORECASE)
        if match:
            return match.group(1).strip(' -_.')
        return None

    def SaveMediaFileArchive(self, MediaFileId: int, TranscodeAttemptId: int) -> int:
        """Archive original file details using INSERT SELECT from MediaFiles table."""
        try:
            LoggingService.LogFunctionEntry("SaveMediaFileArchive", "FileScanningRepository", MediaFileId, TranscodeAttemptId)

            query = """
                INSERT INTO MediaFilesArchive
                (Id, SeasonId, FilePath, FileName, SizeMB, VideoBitrateKbps, AudioBitrateKbps,
                 Resolution, Codec, DurationMinutes, FrameRate, LastScannedDate,
                 CompressionPotential, AssignedProfile, IsInterlaced, ResolutionCategory,
                 FileModificationTime, KeepSource, TotalFrames, CodecProfile, ColorRange,
                 FieldOrder, HasBFrames, RefFrames, PixelFormat, Level, AudioChannels,
                 AudioSampleRate, AudioSampleFormat, AudioChannelLayout, ContainerFormat,
                 OverallBitrate, TranscodedByMediaVortex, ArchiveDate, TranscodeAttemptId)
                SELECT Id, SeasonId, FilePath, FileName, SizeMB, VideoBitrateKbps, AudioBitrateKbps,
                       Resolution, Codec, DurationMinutes, FrameRate, LastScannedDate,
                       CompressionPotential, AssignedProfile, IsInterlaced, ResolutionCategory,
                       FileModificationTime, KeepSource, TotalFrames, CodecProfile, ColorRange,
                       FieldOrder, HasBFrames, RefFrames, PixelFormat, Level, AudioChannels,
                       AudioSampleRate, AudioSampleFormat, AudioChannelLayout, ContainerFormat,
                       OverallBitrate, TranscodedByMediaVortex, NOW(), %s
                FROM MediaFiles
                WHERE Id = %s
            """

            parameters = (TranscodeAttemptId, MediaFileId)

            result = self.ExecuteNonQuery(query, parameters)

            if result:
                LoggingService.LogInfo(f"Successfully archived original file details for MediaFile {MediaFileId}, Archive ID: {result}",
                                     "FileScanningRepository", "SaveMediaFileArchive")
                return result
            else:
                LoggingService.LogError(f"Failed to archive original file details for MediaFile {MediaFileId}",
                                      "FileScanningRepository", "SaveMediaFileArchive")
                return 0

        except Exception as e:
            LoggingService.LogException("Exception saving media file archive", e, "FileScanningRepository", "SaveMediaFileArchive")
            return 0
