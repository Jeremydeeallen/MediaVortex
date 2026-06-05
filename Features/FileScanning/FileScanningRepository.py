import ntpath
import os
import re
from typing import Optional, List, Dict, Any
from Core.Database.BaseRepository import BaseRepository
from Core.Database.DatabaseService import EscapeLikePattern
from Core.Logging.LoggingService import LoggingService
from Core.Models.MediaFileModel import MediaFileModel
from Core.Path.Path import Path, PathError
from Core.Path.PathStorageRoots import GetStorageRoots, GetPrefixMap
from Features.FileScanning.Models.RootFolderModel import RootFolderModel
from Features.FileScanning.Models.SeasonModel import SeasonModel


# directive: path-schema-migration | # see path.S8
def LookupTypedPair(CanonicalString: str):
    """Parse a legacy FilePath into (StorageRootId, RelativePath); returns (None, None) on failure."""
    if not CanonicalString:
        return (None, None)
    try:
        P = Path.FromLegacyString(CanonicalString, GetStorageRoots())
        return (P.StorageRootId, P.RelativePath)
    except PathError:
        return (None, None)


# directive: path-schema-migration | # see path.S8
def SynthesizeFilePath(StorageRootId, RelativePath) -> str:
    """Render canonical FilePath via Path.CanonicalDisplay."""
    if StorageRootId is None:
        return ""
    try:
        return Path(StorageRootId, RelativePath or "").CanonicalDisplay(GetPrefixMap())
    except PathError:
        return ""


# directive: path-schema-migration | # see path.S8
def SynthesizeFilePathInRows(Rows):
    """No-op kept for migration transition; models compute FilePath via @property."""
    return Rows


_FSR_STORAGE_ROOTS_CACHE: dict = {"_StorageRoots": None, "_PrefixMap": None}


# directive: filescanning-uses-path | # see path.S6
def _GetStorageRoots(Db) -> list:
    """Lazy StorageRoots prefix list for shape-agnostic path parsing."""
    if _FSR_STORAGE_ROOTS_CACHE["_StorageRoots"] is None:
        Rows = Db.ExecuteQuery(
            "SELECT Id, CanonicalPrefix FROM StorageRoots ORDER BY length(CanonicalPrefix) DESC"
        )
        _FSR_STORAGE_ROOTS_CACHE["_StorageRoots"] = [
            {"Id": R.get("id", R.get("Id")),
             "CanonicalPrefix": R.get("canonicalprefix", R.get("CanonicalPrefix"))}
            for R in Rows
        ]
        _FSR_STORAGE_ROOTS_CACHE["_PrefixMap"] = {Sr["Id"]: Sr["CanonicalPrefix"] for Sr in _FSR_STORAGE_ROOTS_CACHE["_StorageRoots"]}
    return _FSR_STORAGE_ROOTS_CACHE["_StorageRoots"]


# directive: filescanning-uses-path | # see path.S5
def _LocalExists(Value: str) -> bool:
    """Existence on a worker-local string."""
    return bool(Value) and os.path.exists(Value)


# directive: filescanning-uses-path | # see path.S5
def _LocalIsDir(Value: str) -> bool:
    """Dir-check on a worker-local string."""
    return bool(Value) and os.path.isdir(Value)


# directive: filescanning-uses-path | # see path.S5
def _Normalize(Value: str) -> str:
    """Backslash normalization for canonical Windows-shape paths."""
    return (Value or "").replace("/", "\\")


# directive: filescanning-uses-path | # see path.S5
def _Join(Base: str, *Children: str) -> str:
    """Shape-agnostic join via Path.Join chained; falls through to ntpath on parse failure."""
    if not Base:
        return Base or ""
    try:
        from Core.Database.DatabaseService import DatabaseService
        _GetStorageRoots(DatabaseService())
        P = Path.FromLegacyString(Base, _FSR_STORAGE_ROOTS_CACHE["_StorageRoots"])
        for Child in Children:
            if Child:
                P = P.Join(Child.replace("\\", "/").strip("/"))
        return P.CanonicalDisplay(_FSR_STORAGE_ROOTS_CACHE["_PrefixMap"])
    except Exception:
        BackslashJoin = Base
        for Child in Children:
            if Child:
                if not BackslashJoin.endswith("\\") and not BackslashJoin.endswith("/"):
                    BackslashJoin += "\\"
                BackslashJoin += Child.replace("/", "\\").lstrip("\\")
        return BackslashJoin


# directive: filescanning-uses-path | # see path.S5
def _SplitExt(Value: str) -> tuple:
    """Shape-agnostic splitext; falls through on parse failure."""
    if not Value:
        return ("", "")
    try:
        from Core.Database.DatabaseService import DatabaseService
        _GetStorageRoots(DatabaseService())
        P = Path.FromLegacyString(Value, _FSR_STORAGE_ROOTS_CACHE["_StorageRoots"])
        Base, Ext = P.SplitExt()
        return (Base.CanonicalDisplay(_FSR_STORAGE_ROOTS_CACHE["_PrefixMap"]), Ext)
    except Exception:
        return ntpath.splitext(Value or "")


class FileScanningRepository(BaseRepository):
    """Repository for FileScanning-related database operations."""

    # ─── ScanJobs Queries ──────────────────────────────────────────────

    def GetRunningScans(self, RootFolderPath: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return ScanJobs rows in Status IN ('Pending', 'Running').

        Optionally filtered to a single rootfolder path. The single source of
        truth for "is a scan running?" -- callers derive bool/count/list from
        the result. Replaces CheckForExistingRunningScan, IsScanRunning,
        IsScanRunningForRootFolder, GetRunningScanCount, GetAllRunningScans
        per FileScanning.feature.md criterion 18b.
        """
        try:
            if RootFolderPath:
                query = """
                    SELECT Id, JobId, RootFolderPath, Recursive, Status, ProcessId,
                           StartTime, EndTime, Progress, CurrentDirectory,
                           TotalFiles, ProcessedFiles, SkippedFiles, EncodingErrors,
                           NewFiles, UpdatedFiles, DeletedFiles, ErrorMessage,
                           LastUpdated, WorkerName
                    FROM ScanJobs
                    WHERE RootFolderPath = %s AND Status IN ('Pending', 'Running')
                    ORDER BY StartTime ASC
                """
                rows = self.ExecuteQuery(query, (RootFolderPath,))
            else:
                query = """
                    SELECT Id, JobId, RootFolderPath, Recursive, Status, ProcessId,
                           StartTime, EndTime, Progress, CurrentDirectory,
                           TotalFiles, ProcessedFiles, SkippedFiles, EncodingErrors,
                           NewFiles, UpdatedFiles, DeletedFiles, ErrorMessage,
                           LastUpdated, WorkerName
                    FROM ScanJobs
                    WHERE Status IN ('Pending', 'Running')
                    ORDER BY StartTime ASC
                """
                rows = self.ExecuteQuery(query)
            return rows or []
        except Exception as e:
            LoggingService.LogException("Error querying running scans", e, "FileScanningRepository", "GetRunningScans")
            return []

    # ─── Root Folder Methods ───────────────────────────────────────────

    def GetAllRootFolders(self, SortColumn='RootFolder', SortOrder='ASC') -> List[RootFolderModel]:
        ValidColumns = ['Id', 'RootFolder', 'LastScannedDate', 'TotalSizeGB', 'PreferredWorkerName']
        if SortColumn not in ValidColumns:
            SortColumn = 'RootFolder'
        if SortOrder.upper() not in ['ASC', 'DESC']:
            SortOrder = 'ASC'
        query = f"SELECT Id, RootFolder, LastScannedDate, TotalSizeGB, PreferredWorkerName FROM RootFolders ORDER BY {SortColumn} {SortOrder.upper()}"
        rows = self.ExecuteQuery(query)
        rootFolders = []
        for row in rows:
            rootFolder = RootFolderModel(
                Id=row['Id'],
                RootFolder=row['RootFolder'],
                LastScannedDate=row['LastScannedDate'],
                TotalSizeGB=row['TotalSizeGB'],
                PreferredWorkerName=row.get('PreferredWorkerName'),
            )
            rootFolders.append(rootFolder)
        return rootFolders

    def GetRootFolderById(self, RootFolderId: int) -> Optional[RootFolderModel]:
        query = "SELECT Id, RootFolder, LastScannedDate, TotalSizeGB, PreferredWorkerName FROM RootFolders WHERE Id = %s"
        rows = self.ExecuteQuery(query, (RootFolderId,))
        if not rows:
            return None
        row = rows[0]
        return RootFolderModel(
            Id=row['Id'],
            RootFolder=row['RootFolder'],
            LastScannedDate=row['LastScannedDate'],
            TotalSizeGB=row['TotalSizeGB'],
            PreferredWorkerName=row.get('PreferredWorkerName'),
        )

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

    # directive: path-schema-migration | # see path.S7
    def DeleteRootFolder(self, RootFolderId: int) -> bool:
        try:
            rfRows = self.ExecuteQuery("SELECT RootFolder FROM RootFolders WHERE Id = %s", (RootFolderId,))
            if rfRows:
                Sid, RelPrefix = LookupTypedPair(rfRows[0]['RootFolder'])
                if Sid is not None:
                    # Delete the root entry itself (exact RelativePath match) plus everything beneath it
                    EscapedPrefix = EscapeLikePattern((RelPrefix or '').rstrip('/') + '/')
                    self.ExecuteNonQuery(
                        "DELETE FROM MediaFiles WHERE StorageRootId = %s "
                        "AND (LOWER(RelativePath) = LOWER(%s) "
                        "OR LOWER(RelativePath) LIKE LOWER(%s) || '%%' ESCAPE '!')",
                        (Sid, RelPrefix, EscapedPrefix)
                    )
                else:
                    LoggingService.LogWarning(
                        f"DeleteRootFolder: could not parse RootFolder to typed pair: {rfRows[0]['RootFolder']}",
                        "FileScanningRepository", "DeleteRootFolder"
                    )
            affectedRows = self.ExecuteNonQuery("DELETE FROM RootFolders WHERE Id = %s", (RootFolderId,))
            return affectedRows > 0
        except Exception:
            return False

    # directive: path-schema-migration | # see path.S8
    def GetSubfoldersByRootFolder(self, RootFolderPath: str, Page: int = 1, PageSize: int = 25,
                                  Search: str = '', SortColumn: str = 'TotalSizeMB',
                                  SortOrder: str = 'DESC', ExcludedDirectories: List[str] = None) -> Dict[str, Any]:
        """Subfolders under a root folder with aggregated stats; operates on typed pair (StorageRootId, RelativePath)."""
        valid_sort = {'SubfolderName': 'SubfolderName', 'TotalSizeMB': 'TotalSizeMB',
                      'FileCount': 'FileCount', 'MkvCount': 'MkvCount'}
        sort_col = valid_sort.get(SortColumn, 'TotalSizeMB')
        order = 'DESC' if SortOrder.upper() == 'DESC' else 'ASC'

        # Parse the canonical Windows-shape root path to typed pair.
        Sid, RelRoot = LookupTypedPair(RootFolderPath)
        if Sid is None:
            return {'Subfolders': [], 'TotalCount': 0, 'TotalPages': 0}
        # RelativePath stored with forward slashes; ensure trailing '/' for prefix matching.
        rel_prefix = (RelRoot or '').rstrip('/') + '/'
        rel_prefix_len = len(rel_prefix)

        # For SubfolderPath display, keep the canonical Windows-shape display root with trailing backslash.
        root_display = RootFolderPath.rstrip('\\') + '\\'

        # Search filter on subfolder name
        search_condition = ""
        search_params = []
        if Search:
            search_condition = "AND LOWER(SubfolderName) LIKE LOWER(%s)"
            search_params = [f"%{Search}%"]

        # CTE walks RelativePath using forward-slash split for subfolder extraction.
        cte = (
            "WITH subfolders AS ( "
            "    SELECT "
            "        SPLIT_PART(SUBSTRING(mf.RelativePath FROM %s + 1), '/', 1) AS SubfolderName, "
            "        COUNT(*) AS FileCount, "
            "        ROUND(SUM(mf.SizeMB)::numeric, 2) AS TotalSizeMB, "
            "        SUM(CASE WHEN LOWER(mf.FileName) LIKE '%%.mkv' THEN 1 ELSE 0 END) AS MkvCount "
            "    FROM MediaFiles mf "
            "    WHERE mf.StorageRootId = %s "
            "      AND LEFT(mf.RelativePath, %s) = %s "
            "      AND LENGTH(mf.RelativePath) > %s "
            "    GROUP BY SPLIT_PART(SUBSTRING(mf.RelativePath FROM %s + 1), '/', 1) "
            ") "
        )
        cte_params = [rel_prefix_len, Sid, rel_prefix_len, rel_prefix, rel_prefix_len, rel_prefix_len]

        # Count query
        count_query = cte + f"SELECT COUNT(*) AS Count FROM subfolders WHERE SubfolderName != '' {search_condition}"
        count_rows = self.ExecuteQuery(count_query, tuple(cte_params + search_params))
        total_count = count_rows[0]['Count'] if count_rows else 0

        # Data query
        offset = (Page - 1) * PageSize
        data_query = cte + (
            "SELECT SubfolderName, FileCount, TotalSizeMB, MkvCount "
            "FROM subfolders "
            "WHERE SubfolderName != '' "
            f"{search_condition} "
            f"ORDER BY {sort_col} {order} "
            "LIMIT %s OFFSET %s"
        )
        rows = self.ExecuteQuery(data_query, tuple(cte_params + search_params + [PageSize, offset]))

        subfolders = []
        for row in rows:
            subfolders.append({
                'SubfolderName': row['SubfolderName'],
                'SubfolderPath': root_display + row['SubfolderName'],
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

    # directive: path-schema-migration | # see path.S7
    def GetMkvCountsByRootFolder(self) -> Dict[str, int]:
        """MKV file counts per root folder; joins via typed pair (StorageRootId, RelativePath prefix)."""
        try:
            # directive: path-schema-migration -- RootFolders has no StorageRootId; resolve per row in Python.
            RfRows = self.ExecuteQuery("SELECT RootFolder FROM RootFolders")
            counts: Dict[str, int] = {}
            for RfRow in RfRows:
                RootFolderStr = RfRow['RootFolder']
                Sid, RelRoot = LookupTypedPair(RootFolderStr)
                folder_key = RootFolderStr.replace('/', '\\').rstrip('\\').lower()
                if Sid is None:
                    counts[folder_key] = 0
                    continue
                RelPrefix = (RelRoot or '').rstrip('/') + '/'
                EscapedPrefix = EscapeLikePattern(RelPrefix)
                Rows = self.ExecuteQuery(
                    "SELECT COUNT(Id) AS MkvCount FROM MediaFiles "
                    "WHERE StorageRootId = %s "
                    "AND LOWER(RelativePath) LIKE LOWER(%s) || '%%' ESCAPE '!' "
                    "AND LOWER(FileName) LIKE '%%.mkv'",
                    (Sid, EscapedPrefix)
                )
                counts[folder_key] = Rows[0]['MkvCount'] if Rows else 0
            return counts
        except Exception as e:
            LoggingService.LogException("Error getting MKV counts", e, "FileScanningRepository", "GetMkvCountsByRootFolder")
            return {}

    # directive: path-schema-migration | # see path.S8
    def GetMediaFilesPaginated(self, Page: int, PageSize: int, Search: str = '',
                               RootFolderPath: str = '', SortBy: str = 'SizeMB',
                               SortOrder: str = 'DESC') -> Dict[str, Any]:
        """Paginated media files; root-folder filter uses typed pair; rows post-processed to attach synthesized FilePath."""
        valid_sort_columns = {
            'SizeMB': 'SizeMB', 'FileName': 'FileName',
            'LastScannedDate': 'LastScannedDate', 'Codec': 'Codec',
            'Resolution': 'Resolution', 'DurationMinutes': 'DurationMinutes'
        }
        sort_col = valid_sort_columns.get(SortBy, 'SizeMB')
        order = 'DESC' if SortOrder.upper() == 'DESC' else 'ASC'

        conditions = []
        params = []

        # Root folder filter via typed pair.
        if RootFolderPath:
            Sid, RelRoot = LookupTypedPair(RootFolderPath)
            if Sid is None:
                return {'Rows': [], 'TotalCount': 0, 'TotalPages': 0}
            RelPrefix = (RelRoot or '').rstrip('/') + '/' if RelRoot else ''
            conditions.append("StorageRootId = %s")
            params.append(Sid)
            if RelPrefix:
                conditions.append("LOWER(RelativePath) LIKE LOWER(%s) ESCAPE '!'")
                params.append(f"{EscapeLikePattern(RelPrefix)}%")

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
        display_cols = "Id, StorageRootId, RelativePath, FileName, SizeMB, LastScannedDate, Codec, Resolution, DurationMinutes, AssignedProfile"
        data_query = (
            f"SELECT {display_cols} "
            f"FROM MediaFiles {where_clause} "
            f"ORDER BY {sort_col} {order} NULLS LAST "
            "LIMIT %s OFFSET %s"
        )
        data_params = params + [PageSize, offset]
        rows = self.ExecuteQuery(data_query, tuple(data_params))
        SynthesizeFilePathInRows(rows)

        return {
            'Rows': rows,
            'TotalCount': total_count,
            'TotalPages': (total_count + PageSize - 1) // PageSize
        }

    # ─── Media File Methods ────────────────────────────────────────────

    # directive: path-schema-migration | # see path.S8
    def GetTotalMediaFileCount(self) -> int:
        query = "SELECT COUNT(*) as Count FROM MediaFiles"
        rows = self.ExecuteQuery(query)
        return rows[0]['Count'] if rows else 0

    # directive: path-schema-migration | # see path.S7
    def GetHistoricalReductionRates(self) -> Dict[str, float]:
        """Get average size reduction percentages grouped by source codec + resolution category.
        Returns dict like {("h264", "1080p"): 93.5, ...}"""
        try:
            query = """
                SELECT LOWER(m.Codec) AS Codec, LOWER(COALESCE(m.ResolutionCategory, 'unknown')) AS ResolutionCategory,
                       AVG(t.SizeReductionPercent) AS AvgReduction
                FROM TranscodeAttempts t
                JOIN MediaFiles m ON t.MediaFileId = m.Id
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

    # directive: path-schema-migration | # see path.S8
    def GetTranscodeCandidatesByRootFolder(self, RootFolderPath: str, Page: int = 1, PageSize: int = 25,
                                            Search: str = '', SortColumn: str = 'EstimatedSavingsMB',
                                            SortOrder: str = 'DESC') -> Dict[str, Any]:
        """Subfolders with untranscoded files; operates on typed pair (StorageRootId, RelativePath)."""
        valid_sort = {'SubfolderName': 'SubfolderName', 'TotalSizeMB': 'TotalSizeMB',
                      'FileCount': 'FileCount', 'EstimatedSavingsMB': 'EstimatedSavingsMB',
                      'AvgBitrateKbps': 'AvgBitrateKbps'}
        sort_col = valid_sort.get(SortColumn, 'EstimatedSavingsMB')
        order = 'DESC' if SortOrder.upper() == 'DESC' else 'ASC'

        Sid, RelRoot = LookupTypedPair(RootFolderPath)
        if Sid is None:
            return {'Subfolders': [], 'TotalCount': 0, 'TotalPages': 0}
        rel_prefix = (RelRoot or '').rstrip('/') + '/'
        rel_prefix_len = len(rel_prefix)
        root_display = RootFolderPath.rstrip('\\') + '\\'

        search_condition = ""
        search_params = []
        if Search:
            search_condition = "AND LOWER(SubfolderName) LIKE LOWER(%s)"
            search_params = [f"%{Search}%"]

        # Get historical reduction rates for estimation
        reduction_rates = self.GetHistoricalReductionRates()
        if reduction_rates:
            global_avg = sum(reduction_rates.values()) / len(reduction_rates)
        else:
            global_avg = 85.0

        cte = (
            "WITH candidates AS ( "
            "    SELECT "
            "        SPLIT_PART(SUBSTRING(mf.RelativePath FROM %s + 1), '/', 1) AS SubfolderName, "
            "        mf.SizeMB, "
            "        COALESCE(mf.VideoBitrateKbps, 0) AS VideoBitrateKbps, "
            "        LOWER(COALESCE(mf.Codec, 'unknown')) AS Codec, "
            "        LOWER(COALESCE(mf.ResolutionCategory, 'unknown')) AS ResolutionCategory "
            "    FROM MediaFiles mf "
            "    WHERE mf.StorageRootId = %s "
            "      AND LEFT(mf.RelativePath, %s) = %s "
            "      AND LENGTH(mf.RelativePath) > %s "
            "      AND (mf.TranscodedByMediaVortex IS DISTINCT FROM true) "
            "      AND LOWER(COALESCE(mf.Codec, '')) NOT IN ('hevc', 'av1', 'h265') "
            "), "
            "subfolder_stats AS ( "
            "    SELECT "
            "        SubfolderName, "
            "        COUNT(*) AS FileCount, "
            "        ROUND(SUM(SizeMB)::numeric, 2) AS TotalSizeMB, "
            "        ROUND(AVG(NULLIF(VideoBitrateKbps, 0))::numeric, 0) AS AvgBitrateKbps, "
            "        STRING_AGG(Codec || ':' || SizeMB::text || ':' || ResolutionCategory, '|') AS FileDetails "
            "    FROM candidates "
            "    WHERE SubfolderName != '' "
            "    GROUP BY SubfolderName "
            ") "
        )
        cte_params = [rel_prefix_len, Sid, rel_prefix_len, rel_prefix, rel_prefix_len]

        # Count query
        count_query = cte + f"SELECT COUNT(*) AS Count FROM subfolder_stats WHERE 1=1 {search_condition}"
        count_rows = self.ExecuteQuery(count_query, tuple(cte_params + search_params))
        total_count = count_rows[0]['Count'] if count_rows else 0

        # SQL-sortable columns can paginate at DB level; Python-computed columns need all rows.
        sql_sortable = ('SubfolderName', 'FileCount', 'TotalSizeMB', 'AvgBitrateKbps')
        data_query = cte + (
            "SELECT SubfolderName, FileCount, TotalSizeMB, AvgBitrateKbps, FileDetails "
            "FROM subfolder_stats "
            "WHERE 1=1 "
            f"{search_condition} "
            f"ORDER BY {sort_col if sort_col in sql_sortable else 'TotalSizeMB'} {order if sort_col in sql_sortable else 'DESC'} "
        )

        if sort_col in sql_sortable:
            paginated_query = data_query + " LIMIT %s OFFSET %s"
            offset = (Page - 1) * PageSize
            all_rows = self.ExecuteQuery(paginated_query, tuple(cte_params + search_params + [PageSize, offset]))
        else:
            # EstimatedSavingsMB is computed in Python; fetch all and sort/paginate below.
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

                        rate = reduction_rates.get((codec, res_cat))
                        if rate is None:
                            rate = reduction_rates.get((codec, 'unknown'), global_avg)
                        estimated_savings_mb += size_mb * (rate / 100.0)

            subfolders.append({
                'SubfolderName': row['subfoldername'],
                'SubfolderPath': root_display + row['subfoldername'],
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

    # directive: path-schema-migration | # see path.S8
    def GetTranscodeCandidateFiles(self, SubfolderPath: str, Page: int = 1, PageSize: int = 25) -> Dict[str, Any]:
        """Individual untranscoded files in a subfolder; typed-pair prefix match."""
        Sid, RelRoot = LookupTypedPair(SubfolderPath)
        if Sid is None:
            return {'Files': [], 'TotalCount': 0, 'TotalPages': 0}
        rel_prefix = (RelRoot or '').rstrip('/') + '/'
        conditions = [
            "mf.StorageRootId = %s",
            "LEFT(mf.RelativePath, %s) = %s",
            "(mf.TranscodedByMediaVortex IS DISTINCT FROM true)",
            "LOWER(COALESCE(mf.Codec, '')) NOT IN ('hevc', 'av1', 'h265')"
        ]
        params = [Sid, len(rel_prefix), rel_prefix]

        where_clause = "WHERE " + " AND ".join(conditions)

        # Count
        count_query = f"SELECT COUNT(*) AS Count FROM MediaFiles mf {where_clause}"
        count_rows = self.ExecuteQuery(count_query, tuple(params))
        total_count = count_rows[0]['Count'] if count_rows else 0

        # Data
        offset = (Page - 1) * PageSize
        data_query = (
            "SELECT mf.Id, mf.FileName, mf.SizeMB, mf.Codec, mf.ResolutionCategory, mf.AssignedProfile "
            "FROM MediaFiles mf "
            f"{where_clause} "
            "ORDER BY mf.SizeMB DESC NULLS LAST "
            "LIMIT %s OFFSET %s"
        )
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

    # directive: path-schema-migration | # see path.S8
    def GetAllTranscodeCandidateFiles(self, RootFolderPath: str, Page: int = 1, PageSize: int = 25,
                                       Search: str = '', SortColumn: str = 'VideoBitrateKbps',
                                       SortOrder: str = 'DESC') -> Dict[str, Any]:
        """Individual untranscoded files under a root; typed-pair prefix match; folder name derived from RelativePath."""
        ValidSortColumns = {
            'FileName': 'mf.FileName',
            'SizeMB': 'mf.SizeMB',
            'VideoBitrateKbps': 'mf.VideoBitrateKbps',
            'ResolutionCategory': 'mf.ResolutionCategory',
            'Codec': 'mf.Codec'
        }
        SortCol = ValidSortColumns.get(SortColumn, 'mf.VideoBitrateKbps')
        Order = 'DESC' if SortOrder.upper() == 'DESC' else 'ASC'

        Sid, RelRoot = LookupTypedPair(RootFolderPath)
        if Sid is None:
            return {'Files': [], 'TotalCount': 0, 'TotalPages': 0}
        RelPrefix = (RelRoot or '').rstrip('/') + '/'
        Conditions = [
            "mf.StorageRootId = %s",
            "LEFT(mf.RelativePath, %s) = %s",
            "(mf.TranscodedByMediaVortex IS DISTINCT FROM true)",
            "LOWER(COALESCE(mf.Codec, '')) NOT IN ('hevc', 'av1', 'h265')"
        ]
        Params = [Sid, len(RelPrefix), RelPrefix]

        if Search:
            Conditions.append("LOWER(mf.FileName) LIKE LOWER(%s) ESCAPE '!'")
            Params.append(f"%{EscapeLikePattern(Search)}%")

        WhereClause = "WHERE " + " AND ".join(Conditions)

        CountQuery = f"SELECT COUNT(*) AS Count FROM MediaFiles mf {WhereClause}"
        CountRows = self.ExecuteQuery(CountQuery, tuple(Params))
        TotalCount = CountRows[0]['Count'] if CountRows else 0

        Offset = (Page - 1) * PageSize
        DataQuery = (
            "SELECT mf.Id, mf.FileName, mf.RelativePath, mf.SizeMB, mf.Codec, "
            "       mf.ResolutionCategory, mf.VideoBitrateKbps, mf.AssignedProfile, "
            "       mf.AudioLanguages, mf.HasExplicitEnglishAudio "
            "FROM MediaFiles mf "
            f"{WhereClause} "
            f"ORDER BY {SortCol} {Order} NULLS LAST "
            "LIMIT %s OFFSET %s"
        )
        Rows = self.ExecuteQuery(DataQuery, tuple(Params + [PageSize, Offset]))

        Files = []
        for Row in Rows:
            # Folder name extracted from RelativePath after the root prefix; '/' separator stays in stored form.
            Rel = Row['relativepath'] or ''
            Trail = Rel[len(RelPrefix):] if Rel.startswith(RelPrefix) else Rel
            FolderParts = Trail.rsplit('/', 1)
            FolderName = FolderParts[0].replace('/', '\\') if len(FolderParts) > 1 else ''

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

    def NormalizePathToFilesystemCase(self, Path: str) -> str:
        """Walk path components using os.listdir to find actual filesystem case."""
        try:
            if not Path:
                return Path
            normalized_path = _Normalize(Path)
            if not _LocalExists(normalized_path):
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
                    if _LocalIsDir(current_path):
                        dir_contents = os.listdir(current_path)
                        actual_name = None
                        for item in dir_contents:
                            if item.upper() == part.upper():
                                actual_name = item
                                break
                        if actual_name:
                            current_path = _Join(current_path, actual_name)
                        else:
                            current_path = _Join(current_path, part)
                    else:
                        current_path = _Join(current_path, part)
                except Exception as e:
                    LoggingService.LogWarning(f"Could not list directory '{current_path}' to get actual case, using: {part}", "FileScanningRepository", "NormalizePathToFilesystemCase")
                    current_path = _Join(current_path, part)
            if current_path != normalized_path:
                LoggingService.LogInfo(f"Normalized path case: '{normalized_path}' -> '{current_path}'", "FileScanningRepository", "NormalizePathToFilesystemCase")
            return current_path
        except Exception as e:
            LoggingService.LogException("Error normalizing path to filesystem case", e, "FileScanningRepository", "NormalizePathToFilesystemCase")
            return Path

    # directive: path-schema-migration | # see path.S8
    def GetMediaFileByFileName(self, FileName: str) -> Optional[Dict[str, Any]]:
        """Look up a MediaFile by filename for mitigation; FilePath synthesized from typed pair."""
        try:
            selectCols = "Id, StorageRootId, RelativePath, FileName, ContainerFormat, Codec, AudioCodec, TranscodedByMediaVortex, SubtitleFormats"

            # 1. Exact match
            query = f"SELECT {selectCols} FROM MediaFiles WHERE LOWER(FileName) = LOWER(%s) LIMIT 1"
            rows = self.ExecuteQuery(query, (FileName,))
            if rows:
                SynthesizeFilePathInRows(rows)
                return self._MapMediaFileSummaryRow(rows[0], "exact")

            # 2. Match without extension (handles container change: .mkv -> .mp4)
            nameNoExt = _SplitExt(FileName)[0]
            query = f"SELECT {selectCols} FROM MediaFiles WHERE LOWER(FileName) LIKE LOWER(%s) ESCAPE '!' LIMIT 1"
            rows = self.ExecuteQuery(query, (nameNoExt + '%',))
            if rows:
                SynthesizeFilePathInRows(rows)
                return self._MapMediaFileSummaryRow(rows[0], "no_ext")

            # 3. Fuzzy match by episode prefix (handles resolution/quality change)
            episodePrefix = self._ExtractEpisodePrefix(FileName)
            if episodePrefix and episodePrefix != nameNoExt:
                rows = self.ExecuteQuery(query, (episodePrefix + '%',))
                if rows:
                    SynthesizeFilePathInRows(rows)
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
                nameNoExt = _SplitExt(FileName)[0]
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

    # directive: path-schema-migration | # see path.S8
    def _MapMediaFileSummaryRow(self, row, matchType: str = "exact") -> Dict[str, Any]:
        """Map a summary row to a dict for mitigation checking; FilePath synthesized from typed pair."""
        return {
            "Id": row['id'], "FileName": row['filename'],
            "FilePath": SynthesizeFilePath(row.get('storagerootid'), row.get('relativepath')),
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

    # directive: path-schema-migration | # see path.S7
    def SaveMediaFileArchive(self, MediaFileId: int, TranscodeAttemptId: int) -> int:
        """Archive original file details via INSERT SELECT; typed pair only (FilePath dropped)."""
        try:
            LoggingService.LogFunctionEntry("SaveMediaFileArchive", "FileScanningRepository", MediaFileId, TranscodeAttemptId)

            query = (
                "INSERT INTO MediaFilesArchive "
                "(Id, SeasonId, StorageRootId, RelativePath, FileName, SizeMB, VideoBitrateKbps, AudioBitrateKbps, "
                " Resolution, Codec, DurationMinutes, FrameRate, LastScannedDate, "
                " CompressionPotential, AssignedProfile, IsInterlaced, ResolutionCategory, "
                " FileModificationTime, KeepSource, TotalFrames, CodecProfile, ColorRange, "
                " FieldOrder, HasBFrames, RefFrames, PixelFormat, Level, AudioChannels, "
                " AudioSampleRate, AudioSampleFormat, AudioChannelLayout, ContainerFormat, "
                " OverallBitrate, TranscodedByMediaVortex, ArchiveDate, TranscodeAttemptId) "
                "SELECT Id, SeasonId, StorageRootId, RelativePath, FileName, SizeMB, VideoBitrateKbps, AudioBitrateKbps, "
                "       Resolution, Codec, DurationMinutes, FrameRate, LastScannedDate, "
                "       CompressionPotential, AssignedProfile, IsInterlaced, ResolutionCategory, "
                "       FileModificationTime, KeepSource, TotalFrames, CodecProfile, ColorRange, "
                "       FieldOrder, HasBFrames, RefFrames, PixelFormat, Level, AudioChannels, "
                "       AudioSampleRate, AudioSampleFormat, AudioChannelLayout, ContainerFormat, "
                "       OverallBitrate, TranscodedByMediaVortex, NOW(), %s "
                "FROM MediaFiles "
                "WHERE Id = %s"
            )

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
