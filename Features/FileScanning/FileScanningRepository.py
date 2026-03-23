import os
import re
from typing import Optional, List, Dict, Any
from Core.Database.BaseRepository import BaseRepository
from Core.Database.DatabaseService import EscapeLikePattern
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
            rfRows = self.ExecuteQuery("SELECT RootFolder FROM RootFolders WHERE Id = %s", (RootFolderId,))
            if rfRows:
                escapedPath = EscapeLikePattern(rfRows[0]['RootFolder'])
                self.ExecuteNonQuery("DELETE FROM MediaFiles WHERE LOWER(FilePath) LIKE LOWER(%s) || '%%' ESCAPE '!'", (escapedPath,))
            affectedRows = self.ExecuteNonQuery("DELETE FROM RootFolders WHERE Id = %s", (RootFolderId,))
            return affectedRows > 0
        except Exception:
            return False

    def GetSubfoldersByRootFolder(self, RootFolderPath: str, Page: int = 1, PageSize: int = 25,
                                  Search: str = '', SortColumn: str = 'TotalSizeMB',
                                  SortOrder: str = 'DESC', ExcludedDirectories: List[str] = None) -> Dict[str, Any]:
        """Get subfolders under a root folder with aggregated stats from MediaFiles, with SQL-level pagination."""
        valid_sort = {'SubfolderName': 'SubfolderName', 'TotalSizeMB': 'TotalSizeMB',
                      'FileCount': 'FileCount', 'MkvCount': 'MkvCount'}
        sort_col = valid_sort.get(SortColumn, 'TotalSizeMB')
        order = 'DESC' if SortOrder.upper() == 'DESC' else 'ASC'

        # Ensure trailing backslash for prefix matching
        root = RootFolderPath.rstrip('\\') + '\\'
        root_len = len(root)

        # Search filter on subfolder name
        search_condition = ""
        search_params = []
        if Search:
            search_condition = "AND LOWER(SubfolderName) LIKE LOWER(%s)"
            search_params = [f"%{Search}%"]

        # CTE uses LEFT() for prefix matching instead of LIKE (avoids backslash escape issues)
        # SPLIT_PART extracts the first path component after the root prefix
        cte = """
            WITH subfolders AS (
                SELECT
                    SPLIT_PART(SUBSTRING(mf.FilePath FROM %s + 1), chr(92), 1) AS SubfolderName,
                    COUNT(*) AS FileCount,
                    ROUND(SUM(mf.SizeMB)::numeric, 2) AS TotalSizeMB,
                    SUM(CASE WHEN LOWER(mf.FileName) LIKE '%%.mkv' THEN 1 ELSE 0 END) AS MkvCount
                FROM MediaFiles mf
                WHERE LEFT(mf.FilePath, %s) = %s
                  AND LENGTH(mf.FilePath) > %s
                GROUP BY SPLIT_PART(SUBSTRING(mf.FilePath FROM %s + 1), chr(92), 1)
            )
        """
        cte_params = [root_len, root_len, root, root_len, root_len]

        # Count query
        count_query = cte + f"SELECT COUNT(*) AS Count FROM subfolders WHERE SubfolderName != '' {search_condition}"
        count_rows = self.ExecuteQuery(count_query, tuple(cte_params + search_params))
        total_count = count_rows[0]['Count'] if count_rows else 0

        # Data query
        offset = (Page - 1) * PageSize
        data_query = cte + f"""
            SELECT SubfolderName, FileCount, TotalSizeMB, MkvCount
            FROM subfolders
            WHERE SubfolderName != ''
            {search_condition}
            ORDER BY {sort_col} {order}
            LIMIT %s OFFSET %s
        """
        rows = self.ExecuteQuery(data_query, tuple(cte_params + search_params + [PageSize, offset]))

        subfolders = []
        for row in rows:
            subfolders.append({
                'SubfolderName': row['SubfolderName'],
                'SubfolderPath': root + row['SubfolderName'],
                'FileCount': row['FileCount'],
                'TotalSizeMB': float(row['TotalSizeMB']),
                'MkvCount': row['MkvCount']
            })

        return {
            'Subfolders': subfolders,
            'TotalCount': total_count,
            'TotalPages': (total_count + PageSize - 1) // PageSize
        }

    def GetRootFoldersPaginated(self, Page: int, PageSize: int, Search: str = '',
                                SortColumn: str = 'RootFolder', SortOrder: str = 'ASC') -> Dict[str, Any]:
        """Get root folders with SQL-level pagination, filtering, and sorting."""
        ValidColumns = ['Id', 'RootFolder', 'LastScannedDate', 'TotalSizeGB']
        if SortColumn not in ValidColumns:
            SortColumn = 'RootFolder'
        if SortOrder.upper() not in ['ASC', 'DESC']:
            SortOrder = 'ASC'

        params = []
        where_clause = ""
        if Search:
            where_clause = "WHERE LOWER(RootFolder) LIKE LOWER(%s)"
            params.append(f"%{Search}%")

        # Get total count
        count_query = f"SELECT COUNT(*) as Count FROM RootFolders {where_clause}"
        count_rows = self.ExecuteQuery(count_query, tuple(params) if params else None)
        total_count = count_rows[0]['Count'] if count_rows else 0

        # Get paginated results
        offset = (Page - 1) * PageSize
        data_query = f"""SELECT Id, RootFolder, LastScannedDate, TotalSizeGB
                         FROM RootFolders {where_clause}
                         ORDER BY {SortColumn} {SortOrder.upper()}
                         LIMIT %s OFFSET %s"""
        data_params = params + [PageSize, offset]
        rows = self.ExecuteQuery(data_query, tuple(data_params))

        root_folders = []
        for row in rows:
            root_folders.append(RootFolderModel(
                Id=row['Id'], RootFolder=row['RootFolder'],
                LastScannedDate=row['LastScannedDate'], TotalSizeGB=row['TotalSizeGB']
            ))

        return {
            'RootFolders': root_folders,
            'TotalCount': total_count,
            'TotalPages': (total_count + PageSize - 1) // PageSize
        }

    def GetMkvCountsByRootFolder(self) -> Dict[str, int]:
        """Get MKV file counts per root folder using SQL aggregation."""
        try:
            query = """
                SELECT rf.RootFolder, COUNT(mf.Id) as MkvCount
                FROM RootFolders rf
                LEFT JOIN MediaFiles mf ON LOWER(mf.FilePath) LIKE LOWER(rf.RootFolder || '%%')
                    AND LOWER(mf.FileName) LIKE '%%.mkv'
                GROUP BY rf.RootFolder
            """
            rows = self.ExecuteQuery(query)
            counts = {}
            for row in rows:
                folder = row['RootFolder'].replace('/', '\\').rstrip('\\').lower()
                counts[folder] = row['MkvCount']
            return counts
        except Exception as e:
            LoggingService.LogException("Error getting MKV counts", e, "FileScanningRepository", "GetMkvCountsByRootFolder")
            return {}

    def GetMediaFilesPaginated(self, Page: int, PageSize: int, Search: str = '',
                               RootFolderPath: str = '', SortBy: str = 'SizeMB',
                               SortOrder: str = 'DESC') -> Dict[str, Any]:
        """Get media files with SQL-level pagination, filtering, and sorting."""
        valid_sort_columns = {
            'SizeMB': 'SizeMB', 'FileName': 'FileName',
            'LastScannedDate': 'LastScannedDate', 'Codec': 'Codec',
            'Resolution': 'Resolution', 'DurationMinutes': 'DurationMinutes'
        }
        sort_col = valid_sort_columns.get(SortBy, 'SizeMB')
        order = 'DESC' if SortOrder.upper() == 'DESC' else 'ASC'

        conditions = []
        params = []

        # Root folder filter
        if RootFolderPath:
            conditions.append("LOWER(FilePath) LIKE LOWER(%s)")
            params.append(f"{RootFolderPath}%")

        # Search filter (supports negative filter with ! prefix)
        if Search:
            if Search.startswith('!'):
                exclude_term = Search[1:]
                if exclude_term:
                    conditions.append("LOWER(FileName) NOT LIKE LOWER(%s)")
                    params.append(f"%{exclude_term}%")
            else:
                conditions.append("LOWER(FileName) LIKE LOWER(%s)")
                params.append(f"%{Search}%")

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # Get total count
        count_query = f"SELECT COUNT(*) as Count FROM MediaFiles {where_clause}"
        count_rows = self.ExecuteQuery(count_query, tuple(params) if params else None)
        total_count = count_rows[0]['Count'] if count_rows else 0

        # Get paginated results - only select columns needed for display
        offset = (Page - 1) * PageSize
        display_cols = "Id, FileName, FilePath, SizeMB, LastScannedDate, Codec, Resolution, DurationMinutes, AssignedProfile"
        data_query = f"""SELECT {display_cols}
                         FROM MediaFiles {where_clause}
                         ORDER BY {sort_col} {order} NULLS LAST
                         LIMIT %s OFFSET %s"""
        data_params = params + [PageSize, offset]
        rows = self.ExecuteQuery(data_query, tuple(data_params))

        return {
            'Rows': rows,
            'TotalCount': total_count,
            'TotalPages': (total_count + PageSize - 1) // PageSize
        }

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
            TranscodedByMediaVortex=row['TranscodedByMediaVortex'],
            FFprobeFailureCount=row.get('FFprobeFailureCount', 0),
            LastFFprobeError=row.get('LastFFprobeError'),
            LastFFprobeAttemptDate=row.get('LastFFprobeAttemptDate')
        )

    _MEDIA_FILE_SELECT_COLS = """Id, SeasonId, FilePath, FileName, SizeMB, VideoBitrateKbps, AudioBitrateKbps,
                   Resolution, Codec, DurationMinutes, FrameRate, LastScannedDate,
                   CompressionPotential, AssignedProfile, IsInterlaced, ResolutionCategory,
                   FileModificationTime, TotalFrames, CodecProfile, ColorRange, FieldOrder,
                   HasBFrames, RefFrames, PixelFormat, Level, AudioChannels, AudioSampleRate,
                   AudioSampleFormat, AudioChannelLayout, AudioCodec, SubtitleFormats,
                   ContainerFormat, OverallBitrate, TranscodedByMediaVortex,
                   FFprobeFailureCount, LastFFprobeError, LastFFprobeAttemptDate"""

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
        rows = self.ExecuteQuery(query, (f"{EscapeLikePattern(RootFolderPath)}%",))
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
                        query = """INSERT INTO MediaFiles (SeasonId, FilePath, FileName, SizeMB, VideoBitrateKbps, AudioBitrateKbps, Resolution, Codec, DurationMinutes, FrameRate, LastScannedDate, CompressionPotential, AssignedProfile, FileModificationTime, TotalFrames, CodecProfile, ColorRange, FieldOrder, HasBFrames, RefFrames, PixelFormat, Level, AudioChannels, AudioSampleRate, AudioSampleFormat, AudioChannelLayout, AudioCodec, SubtitleFormats, ContainerFormat, OverallBitrate, TranscodedByMediaVortex, FFprobeFailureCount, LastFFprobeError, LastFFprobeAttemptDate) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING Id"""
                        parameters = (MediaFile.SeasonId, MediaFile.FilePath, MediaFile.FileName, MediaFile.SizeMB, MediaFile.VideoBitrateKbps, MediaFile.AudioBitrateKbps, MediaFile.Resolution, MediaFile.Codec, MediaFile.DurationMinutes, MediaFile.FrameRate, MediaFile.LastScannedDate, MediaFile.CompressionPotential, MediaFile.AssignedProfile, MediaFile.FileModificationTime, MediaFile.TotalFrames, MediaFile.CodecProfile, MediaFile.ColorRange, MediaFile.FieldOrder, MediaFile.HasBFrames, MediaFile.RefFrames, MediaFile.PixelFormat, MediaFile.Level, MediaFile.AudioChannels, MediaFile.AudioSampleRate, MediaFile.AudioSampleFormat, MediaFile.AudioChannelLayout, MediaFile.AudioCodec, MediaFile.SubtitleFormats, MediaFile.ContainerFormat, MediaFile.OverallBitrate, MediaFile.TranscodedByMediaVortex, MediaFile.FFprobeFailureCount, MediaFile.LastFFprobeError, MediaFile.LastFFprobeAttemptDate)
                        cursor.execute(query, parameters)
                        mediaFileId = cursor.fetchone()[0]
                        connection.commit()
                        return mediaFileId
                # Update (either explicit update or duplicate converted to update)
                if MediaFile.Id is not None:
                    query = """UPDATE MediaFiles SET SeasonId = %s, FilePath = %s, FileName = %s, SizeMB = %s, VideoBitrateKbps = %s, AudioBitrateKbps = %s, Resolution = %s, Codec = %s, DurationMinutes = %s, FrameRate = %s, LastScannedDate = %s, CompressionPotential = %s, AssignedProfile = %s, FileModificationTime = %s, TotalFrames = %s, CodecProfile = %s, ColorRange = %s, FieldOrder = %s, HasBFrames = %s, RefFrames = %s, PixelFormat = %s, Level = %s, AudioChannels = %s, AudioSampleRate = %s, AudioSampleFormat = %s, AudioChannelLayout = %s, AudioCodec = %s, SubtitleFormats = %s, ContainerFormat = %s, OverallBitrate = %s, TranscodedByMediaVortex = %s, FFprobeFailureCount = %s, LastFFprobeError = %s, LastFFprobeAttemptDate = %s WHERE Id = %s"""
                    parameters = (MediaFile.SeasonId, MediaFile.FilePath, MediaFile.FileName, MediaFile.SizeMB, MediaFile.VideoBitrateKbps, MediaFile.AudioBitrateKbps, MediaFile.Resolution, MediaFile.Codec, MediaFile.DurationMinutes, MediaFile.FrameRate, MediaFile.LastScannedDate, MediaFile.CompressionPotential, MediaFile.AssignedProfile, MediaFile.FileModificationTime, MediaFile.TotalFrames, MediaFile.CodecProfile, MediaFile.ColorRange, MediaFile.FieldOrder, MediaFile.HasBFrames, MediaFile.RefFrames, MediaFile.PixelFormat, MediaFile.Level, MediaFile.AudioChannels, MediaFile.AudioSampleRate, MediaFile.AudioSampleFormat, MediaFile.AudioChannelLayout, MediaFile.AudioCodec, MediaFile.SubtitleFormats, MediaFile.ContainerFormat, MediaFile.OverallBitrate, MediaFile.TranscodedByMediaVortex, MediaFile.FFprobeFailureCount, MediaFile.LastFFprobeError, MediaFile.LastFFprobeAttemptDate, MediaFile.Id)
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

    # ─── Transcode Candidates Methods ─────────────────────────────────

    def GetHistoricalReductionRates(self) -> Dict[str, float]:
        """Get average size reduction percentages grouped by source codec + resolution category.
        Returns dict like {("h264", "1080p"): 93.5, ...}"""
        try:
            query = """
                SELECT LOWER(m.Codec) AS Codec, LOWER(COALESCE(m.ResolutionCategory, 'unknown')) AS ResolutionCategory,
                       AVG(t.SizeReductionPercent) AS AvgReduction
                FROM TranscodeAttempts t
                JOIN MediaFiles m ON LOWER(m.FilePath) = LOWER(t.FilePath)
                WHERE t.Success = true AND t.SizeReductionPercent > 0
                GROUP BY LOWER(m.Codec), LOWER(COALESCE(m.ResolutionCategory, 'unknown'))
            """
            rows = self.ExecuteQuery(query)
            rates = {}
            for row in rows:
                rates[(row['codec'], row['resolutioncategory'])] = float(row['avgreduction'])
            return rates
        except Exception as e:
            LoggingService.LogException("Error getting historical reduction rates", e, "FileScanningRepository", "GetHistoricalReductionRates")
            return {}

    def GetTranscodeCandidatesByRootFolder(self, RootFolderPath: str, Page: int = 1, PageSize: int = 25,
                                            Search: str = '', SortColumn: str = 'EstimatedSavingsMB',
                                            SortOrder: str = 'DESC') -> Dict[str, Any]:
        """Get subfolders with untranscoded files, aggregated with codec/resolution breakdowns and estimated savings."""
        valid_sort = {'SubfolderName': 'SubfolderName', 'TotalSizeMB': 'TotalSizeMB',
                      'FileCount': 'FileCount', 'EstimatedSavingsMB': 'EstimatedSavingsMB',
                      'AvgBitrateKbps': 'AvgBitrateKbps'}
        sort_col = valid_sort.get(SortColumn, 'EstimatedSavingsMB')
        order = 'DESC' if SortOrder.upper() == 'DESC' else 'ASC'

        root = RootFolderPath.rstrip('\\') + '\\'
        root_len = len(root)

        search_condition = ""
        search_params = []
        if Search:
            search_condition = "AND LOWER(SubfolderName) LIKE LOWER(%s)"
            search_params = [f"%{Search}%"]

        # Get historical reduction rates for estimation
        reduction_rates = self.GetHistoricalReductionRates()
        # Calculate global average fallback
        if reduction_rates:
            global_avg = sum(reduction_rates.values()) / len(reduction_rates)
        else:
            global_avg = 85.0

        cte = """
            WITH candidates AS (
                SELECT
                    SPLIT_PART(SUBSTRING(mf.FilePath FROM %s + 1), chr(92), 1) AS SubfolderName,
                    mf.SizeMB,
                    COALESCE(mf.VideoBitrateKbps, 0) AS VideoBitrateKbps,
                    LOWER(COALESCE(mf.Codec, 'unknown')) AS Codec,
                    LOWER(COALESCE(mf.ResolutionCategory, 'unknown')) AS ResolutionCategory
                FROM MediaFiles mf
                WHERE LEFT(mf.FilePath, %s) = %s
                  AND LENGTH(mf.FilePath) > %s
                  AND (mf.TranscodedByMediaVortex IS DISTINCT FROM true)
                  AND LOWER(COALESCE(mf.Codec, '')) NOT IN ('hevc', 'av1', 'h265')
            ),
            subfolder_stats AS (
                SELECT
                    SubfolderName,
                    COUNT(*) AS FileCount,
                    ROUND(SUM(SizeMB)::numeric, 2) AS TotalSizeMB,
                    ROUND(AVG(NULLIF(VideoBitrateKbps, 0))::numeric, 0) AS AvgBitrateKbps,
                    STRING_AGG(Codec || ':' || SizeMB::text || ':' || ResolutionCategory, '|') AS FileDetails
                FROM candidates
                WHERE SubfolderName != ''
                GROUP BY SubfolderName
            )
        """
        cte_params = [root_len, root_len, root, root_len]

        # Count query
        count_query = cte + f"SELECT COUNT(*) AS Count FROM subfolder_stats WHERE 1=1 {search_condition}"
        count_rows = self.ExecuteQuery(count_query, tuple(cte_params + search_params))
        total_count = count_rows[0]['Count'] if count_rows else 0

        # SQL-sortable columns can paginate at DB level; Python-computed columns need all rows
        sql_sortable = ('SubfolderName', 'FileCount', 'TotalSizeMB', 'AvgBitrateKbps')
        data_query = cte + f"""
            SELECT SubfolderName, FileCount, TotalSizeMB, AvgBitrateKbps, FileDetails
            FROM subfolder_stats
            WHERE 1=1
            {search_condition}
            ORDER BY {sort_col if sort_col in sql_sortable else 'TotalSizeMB'} {order if sort_col in sql_sortable else 'DESC'}
        """

        if sort_col in sql_sortable:
            paginated_query = data_query + " LIMIT %s OFFSET %s"
            offset = (Page - 1) * PageSize
            all_rows = self.ExecuteQuery(paginated_query, tuple(cte_params + search_params + [PageSize, offset]))
        else:
            # EstimatedSavingsMB is computed in Python, so fetch all and sort/paginate below
            all_rows = self.ExecuteQuery(data_query, tuple(cte_params + search_params))

        subfolders = []
        for row in all_rows:
            file_details_str = row['filedetails'] or ''
            codec_breakdown = {}
            resolution_breakdown = {}
            estimated_savings_mb = 0.0

            if file_details_str:
                for entry in file_details_str.split('|'):
                    parts = entry.split(':')
                    if len(parts) >= 3:
                        codec = parts[0]
                        size_mb = float(parts[1]) if parts[1] else 0
                        res_cat = parts[2]

                        codec_breakdown[codec] = codec_breakdown.get(codec, 0) + 1
                        resolution_breakdown[res_cat] = resolution_breakdown.get(res_cat, 0) + 1

                        # Calculate estimated savings for this file
                        rate = reduction_rates.get((codec, res_cat))
                        if rate is None:
                            rate = reduction_rates.get((codec, 'unknown'), global_avg)
                        estimated_savings_mb += size_mb * (rate / 100.0)

            subfolders.append({
                'SubfolderName': row['subfoldername'],
                'SubfolderPath': root + row['subfoldername'],
                'FileCount': row['filecount'],
                'TotalSizeMB': float(row['totalsizemb']),
                'AvgBitrateKbps': int(row['avgbitratekbps']) if row['avgbitratekbps'] else 0,
                'CodecBreakdown': codec_breakdown,
                'ResolutionBreakdown': resolution_breakdown,
                'EstimatedSavingsMB': round(estimated_savings_mb, 2)
            })

        # If sorting by EstimatedSavingsMB, sort and paginate in Python
        if sort_col == 'EstimatedSavingsMB':
            reverse = (order == 'DESC')
            subfolders.sort(key=lambda x: x['EstimatedSavingsMB'], reverse=reverse)
            offset = (Page - 1) * PageSize
            subfolders = subfolders[offset:offset + PageSize]

        return {
            'Subfolders': subfolders,
            'TotalCount': total_count,
            'TotalPages': (total_count + PageSize - 1) // PageSize
        }

    def GetTranscodeCandidateFiles(self, SubfolderPath: str, Page: int = 1, PageSize: int = 25) -> Dict[str, Any]:
        """Get individual untranscoded files in a subfolder for drill-down view."""
        conditions = [
            "LEFT(mf.FilePath, %s) = %s",
            "(mf.TranscodedByMediaVortex IS DISTINCT FROM true)",
            "LOWER(COALESCE(mf.Codec, '')) NOT IN ('hevc', 'av1', 'h265')"
        ]
        prefix = SubfolderPath.rstrip('\\') + '\\'
        params = [len(prefix), prefix]

        where_clause = "WHERE " + " AND ".join(conditions)

        # Count
        count_query = f"SELECT COUNT(*) AS Count FROM MediaFiles mf {where_clause}"
        count_rows = self.ExecuteQuery(count_query, tuple(params))
        total_count = count_rows[0]['Count'] if count_rows else 0

        # Data
        offset = (Page - 1) * PageSize
        data_query = f"""
            SELECT mf.Id, mf.FileName, mf.SizeMB, mf.Codec, mf.ResolutionCategory, mf.AssignedProfile
            FROM MediaFiles mf
            {where_clause}
            ORDER BY mf.SizeMB DESC NULLS LAST
            LIMIT %s OFFSET %s
        """
        rows = self.ExecuteQuery(data_query, tuple(params + [PageSize, offset]))

        files = []
        for row in rows:
            files.append({
                'Id': row['id'],
                'FileName': row['filename'],
                'SizeMB': float(row['sizemb']) if row['sizemb'] else 0,
                'Codec': row['codec'] or 'Unknown',
                'ResolutionCategory': row['resolutioncategory'] or 'Unknown',
                'AssignedProfile': row['assignedprofile']
            })

        return {
            'Files': files,
            'TotalCount': total_count,
            'TotalPages': (total_count + PageSize - 1) // PageSize
        }

    def GetAllTranscodeCandidateFiles(self, RootFolderPath: str, Page: int = 1, PageSize: int = 25,
                                       Search: str = '', SortColumn: str = 'VideoBitrateKbps',
                                       SortOrder: str = 'DESC') -> Dict[str, Any]:
        """Get individual untranscoded files across the entire root folder, sortable by bitrate."""
        ValidSortColumns = {
            'FileName': 'mf.FileName',
            'SizeMB': 'mf.SizeMB',
            'VideoBitrateKbps': 'mf.VideoBitrateKbps',
            'ResolutionCategory': 'mf.ResolutionCategory',
            'Codec': 'mf.Codec'
        }
        SortCol = ValidSortColumns.get(SortColumn, 'mf.VideoBitrateKbps')
        Order = 'DESC' if SortOrder.upper() == 'DESC' else 'ASC'

        Prefix = RootFolderPath.rstrip('\\') + '\\'
        Conditions = [
            "LEFT(mf.FilePath, %s) = %s",
            "(mf.TranscodedByMediaVortex IS DISTINCT FROM true)",
            "LOWER(COALESCE(mf.Codec, '')) NOT IN ('hevc', 'av1', 'h265')"
        ]
        Params = [len(Prefix), Prefix]

        if Search:
            Conditions.append("LOWER(mf.FileName) LIKE LOWER(%s) ESCAPE '!'")
            Params.append(f"%{EscapeLikePattern(Search)}%")

        WhereClause = "WHERE " + " AND ".join(Conditions)

        CountQuery = f"SELECT COUNT(*) AS Count FROM MediaFiles mf {WhereClause}"
        CountRows = self.ExecuteQuery(CountQuery, tuple(Params))
        TotalCount = CountRows[0]['Count'] if CountRows else 0

        Offset = (Page - 1) * PageSize
        DataQuery = f"""
            SELECT mf.Id, mf.FileName, mf.FilePath, mf.SizeMB, mf.Codec,
                   mf.ResolutionCategory, mf.VideoBitrateKbps, mf.AssignedProfile,
                   mf.AudioLanguages, mf.HasExplicitEnglishAudio
            FROM MediaFiles mf
            {WhereClause}
            ORDER BY {SortCol} {Order} NULLS LAST
            LIMIT %s OFFSET %s
        """
        Rows = self.ExecuteQuery(DataQuery, tuple(Params + [PageSize, Offset]))

        Files = []
        for Row in Rows:
            # Extract subfolder name from path
            FilePath = Row['filepath'] or ''
            RelativePath = FilePath[len(Prefix):] if FilePath.startswith(Prefix) else FilePath
            FolderParts = RelativePath.rsplit('\\', 1)
            FolderName = FolderParts[0] if len(FolderParts) > 1 else ''

            Files.append({
                'Id': Row['id'],
                'FileName': Row['filename'],
                'FolderName': FolderName,
                'SizeMB': float(Row['sizemb']) if Row['sizemb'] else 0,
                'Codec': Row['codec'] or 'Unknown',
                'ResolutionCategory': Row['resolutioncategory'] or 'Unknown',
                'VideoBitrateKbps': int(Row['videobitratekbps']) if Row['videobitratekbps'] else 0,
                'AssignedProfile': Row['assignedprofile'],
                'AudioLanguages': Row['audiolanguages'],
                'HasExplicitEnglishAudio': Row['hasexplicitenglishaudio']
            })

        return {
            'Files': Files,
            'TotalCount': TotalCount,
            'TotalPages': (TotalCount + PageSize - 1) // PageSize
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
                rows = self.ExecuteQuery(likeQuery, (EscapeLikePattern(nameNoExt) + '%',))

                # 3. Fuzzy match by episode prefix (handles resolution/quality change)
                if not rows:
                    episodePrefix = self._ExtractEpisodePrefix(FileName)
                    if episodePrefix and episodePrefix != nameNoExt:
                        rows = self.ExecuteQuery(likeQuery, (EscapeLikePattern(episodePrefix) + '%',))

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
