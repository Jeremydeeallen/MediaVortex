from typing import List, Optional, Dict, Any
from Core.Database.BaseRepository import BaseRepository
from Core.Database.DatabaseService import EscapeLikePattern
from Core.Logging.LoggingService import LoggingService
from Core.Path.Path import Path, PathError
from Core.Path.PathStorageRoots import GetStorageRoots, GetPrefixMap


# directive: path-schema-migration | # see path.S8
def _SafeLookupTypedPair(CanonicalString: str):
    if not CanonicalString:
        return (None, None)
    try:
        P = Path.FromLegacyString(CanonicalString, GetStorageRoots())
        return (P.StorageRootId, P.RelativePath)
    except PathError:
        return (None, None)


# directive: path-schema-migration | # see path.S8
def _SafeCanonical(StorageRootId, RelativePath) -> str:
    if StorageRootId is None:
        return ""
    try:
        return Path(StorageRootId, RelativePath or "").CanonicalDisplay(GetPrefixMap())
    except PathError:
        return ""


# directive: path-schema-migration | # see path.S8
def PrefixMap():
    """Alias for the cached storage-root-id to canonical-prefix mapping."""
    return GetPrefixMap()
from Features.ShowSettings.Models.ShowSettingModel import ShowSettingModel


class ShowSettingsRepository(BaseRepository):
    # directive: path-schema-migration | # see path.S8
    """Repository for ShowSettings table operations."""

    # directive: path-schema-migration | # see path.S8
    def GetAllShowSettings(self) -> List[ShowSettingModel]:
        """Get all show settings ordered by typed-pair."""
        try:
            query = (
                "SELECT Id, StorageRootId, RelativePath, TargetResolution, CreatedDate, LastModifiedDate "
                "FROM ShowSettings "
                "ORDER BY StorageRootId, RelativePath"
            )
            Rows = self.ExecuteQuery(query)
            return [self._MapRowToModel(Row) for Row in Rows]
        except Exception as Ex:
            LoggingService.LogException("Exception getting all show settings", Ex, "ShowSettingsRepository", "GetAllShowSettings")
            return []

    # directive: path-schema-migration | # see path.S8
    def GetShowSettingByFolder(self, ShowFolder: str) -> Optional[ShowSettingModel]:
        """Get show setting for a specific folder via typed-pair lookup."""
        try:
            Sid, Rel = _SafeLookupTypedPair(ShowFolder)
            if Sid is None or Rel is None:
                return None
            query = (
                "SELECT Id, StorageRootId, RelativePath, TargetResolution, CreatedDate, LastModifiedDate "
                "FROM ShowSettings "
                "WHERE StorageRootId = %s AND RelativePath = %s "
                "LIMIT 1"
            )
            Rows = self.ExecuteQuery(query, (Sid, Rel))
            if Rows:
                return self._MapRowToModel(Rows[0])
            return None
        except Exception as Ex:
            LoggingService.LogException("Exception getting show setting by folder", Ex, "ShowSettingsRepository", "GetShowSettingByFolder")
            return None

    # directive: path-schema-migration | # see path.S8
    def SaveShowSetting(self, Setting: ShowSettingModel) -> int:
        """Insert or update a show setting via typed-pair. Returns the Id."""
        try:
            Sid, Rel = _SafeLookupTypedPair(Setting.ShowFolder)
            if Sid is None or Rel is None:
                LoggingService.LogException(
                    f"Cannot resolve ShowFolder to typed pair: {Setting.ShowFolder!r}",
                    Exception("LookupTypedPair returned None"),
                    "ShowSettingsRepository", "SaveShowSetting",
                )
                return 0
            Existing = self.GetShowSettingByFolder(Setting.ShowFolder)
            if Existing:
                query = (
                    "UPDATE ShowSettings "
                    "SET TargetResolution = %s, LastModifiedDate = NOW() "
                    "WHERE StorageRootId = %s AND RelativePath = %s "
                    "RETURNING Id"
                )
                self.ExecuteNonQuery(query, (Setting.TargetResolution, Sid, Rel))
                return Existing.Id
            else:
                query = (
                    "INSERT INTO ShowSettings (StorageRootId, RelativePath, TargetResolution, CreatedDate, LastModifiedDate) "
                    "VALUES (%s, %s, %s, NOW(), NOW()) "
                    "RETURNING Id"
                )
                self.ExecuteNonQuery(query, (Sid, Rel, Setting.TargetResolution))
                return self.GetLastInsertId()
        except Exception as Ex:
            LoggingService.LogException("Exception saving show setting", Ex, "ShowSettingsRepository", "SaveShowSetting")
            return 0

    # directive: path-schema-migration | # see path.S8
    def SetSeriesAssignedProfile(self, ShowFolder: str, AssignedProfile: Optional[str]) -> int:
        """Set or clear the per-show AssignedProfile via typed-pair WHERE."""
        try:
            Sid, Rel = _SafeLookupTypedPair(ShowFolder)
            if Sid is None or Rel is None:
                LoggingService.LogException(
                    f"Cannot resolve ShowFolder to typed pair: {ShowFolder!r}",
                    Exception("LookupTypedPair returned None"),
                    "ShowSettingsRepository", "SetSeriesAssignedProfile",
                )
                return 0
            Existing = self.GetShowSettingByFolder(ShowFolder)
            if Existing:
                self.ExecuteNonQuery(
                    "UPDATE ShowSettings "
                    "SET AssignedProfile = %s, LastModifiedDate = NOW() "
                    "WHERE StorageRootId = %s AND RelativePath = %s",
                    (AssignedProfile, Sid, Rel),
                )
                return Existing.Id
            self.ExecuteNonQuery(
                "INSERT INTO ShowSettings (StorageRootId, RelativePath, TargetResolution, AssignedProfile, CreatedDate, LastModifiedDate) "
                "VALUES (%s, %s, '', %s, NOW(), NOW())",
                (Sid, Rel, AssignedProfile),
            )
            return self.GetLastInsertId()
        except Exception as Ex:
            LoggingService.LogException(
                f"Exception setting AssignedProfile for {ShowFolder!r}",
                Ex, "ShowSettingsRepository", "SetSeriesAssignedProfile"
            )
            return 0

    def BulkUpdateTargetResolution(self, ShowFolders: List[str], TargetResolution: str) -> int:
        # directive: path-schema-migration | # see path.S8
        """Update target resolution for multiple shows at once. Creates settings for shows that don't have one."""
        try:
            Updated = 0
            for Folder in ShowFolders:
                Setting = ShowSettingModel(ShowFolder=Folder, TargetResolution=TargetResolution)
                Result = self.SaveShowSetting(Setting)
                if Result:
                    Updated += 1
            return Updated
        except Exception as Ex:
            LoggingService.LogException("Exception bulk updating target resolution", Ex, "ShowSettingsRepository", "BulkUpdateTargetResolution")
            return 0

    # directive: path-schema-migration | # see path.S8
    def DeleteShowSetting(self, ShowFolder: str) -> bool:
        """Delete a show setting via typed-pair WHERE (reverts to default)."""
        try:
            Sid, Rel = _SafeLookupTypedPair(ShowFolder)
            if Sid is None or Rel is None:
                return False
            query = "DELETE FROM ShowSettings WHERE StorageRootId = %s AND RelativePath = %s"
            AffectedRows = self.ExecuteNonQuery(query, (Sid, Rel))
            return AffectedRows > 0
        except Exception as Ex:
            LoggingService.LogException("Exception deleting show setting", Ex, "ShowSettingsRepository", "DeleteShowSetting")
            return False

    # directive: path-schema-migration | # see path.S8
    def GetTargetResolutionForFile(self, FilePath: str) -> Optional[str]:
        """Per-show target resolution override, or None when no show row exists."""
        try:
            ShowFolder = self._ExtractShowFolder(FilePath)
            if not ShowFolder:
                return None
            Setting = self.GetShowSettingByFolder(ShowFolder)
            return Setting.TargetResolution if Setting else None
        except Exception as Ex:
            LoggingService.LogException(
                "Exception getting target resolution for file", Ex,
                "ShowSettingsRepository", "GetTargetResolutionForFile",
            )
            return None

    # directive: path-schema-migration | # see path.S8
    def GetShowsWithStats(self, RootDrive: str = None) -> List[Dict[str, Any]]:
        """Get all unique shows from MediaFiles via typed-pair grouping; synthesizes ShowFolder display string."""
        try:
            DriveFilter = ""
            Params = ()
            if RootDrive:
                StorageRootId = self._ResolveRootDriveToStorageRootId(RootDrive)
                if StorageRootId is not None:
                    DriveFilter = "WHERE mf.StorageRootId = %s"
                    Params = (StorageRootId,)

            query = (
                "SELECT "
                "    mf.StorageRootId as StorageRootId, "
                "    split_part(mf.RelativePath, '/', 1) as RelativePath, "
                "    split_part(mf.RelativePath, '/', 1) as ShowName, "
                "    COUNT(*) as FileCount, "
                "    ROUND(SUM(mf.SizeMB)::numeric / 1024, 1) as TotalGB, "
                "    MODE() WITHIN GROUP (ORDER BY mf.ResolutionCategory) as CommonResolution, "
                "    MODE() WITHIN GROUP (ORDER BY mf.Codec) as CommonCodec, "
                "    ss.TargetResolution as TargetResolution, "
                "    ss.AssignedProfile as AssignedProfile, "
                "    SUM(CASE WHEN mf.TranscodedByMediaVortex = true THEN 1 ELSE 0 END) as TranscodedCount "
                "FROM MediaFiles mf "
                "LEFT JOIN ShowSettings ss "
                "    ON ss.StorageRootId = mf.StorageRootId "
                "   AND ss.RelativePath = split_part(mf.RelativePath, '/', 1) "
                f"{DriveFilter} "
                "GROUP BY mf.StorageRootId, split_part(mf.RelativePath, '/', 1), ss.TargetResolution, ss.AssignedProfile "
                "HAVING COUNT(*) > 0 "
                "ORDER BY SUM(mf.SizeMB) DESC"
            )
            Rows = self.ExecuteQuery(query, Params)
            Pm = PrefixMap()
            for R in Rows:
                Sid = R.get("storagerootid") if "storagerootid" in R else R.get("StorageRootId")
                Rel = R.get("relativepath") if "relativepath" in R else R.get("RelativePath")
                Prefix = Pm.get(Sid, "") if Sid is not None else ""
                Display = (Prefix + Rel.replace("/", "\\")) if (Prefix and Rel) else ""
                R["ShowFolder"] = Display
                R["showfolder"] = Display
            return Rows
        except Exception as Ex:
            LoggingService.LogException("Exception getting shows with stats", Ex, "ShowSettingsRepository", "GetShowsWithStats")
            return []

    # directive: path-schema-migration | # see path.S8
    def _ResolveRootDriveToStorageRootId(self, RootDrive: str) -> Optional[int]:
        """Map a bare drive prefix like 'Z:' or 'T:\\' to a StorageRootId by CanonicalPrefix match."""
        if not RootDrive:
            return None
        Needle = RootDrive.upper().rstrip("\\").rstrip("/")
        for Sid, Prefix in PrefixMap().items():
            Hay = (Prefix or "").upper().rstrip("\\").rstrip("/")
            if Hay == Needle:
                return Sid
        for Sid, Prefix in PrefixMap().items():
            if (Prefix or "").upper().startswith(Needle):
                return Sid
        return None

    # directive: path-schema-migration | # see path.S8
    def _ExtractShowFolder(self, FilePath: str) -> Optional[str]:
        """Extract show folder from a file path. E.g., 'T:\\House\\Season 1\\ep.mp4' -> 'T:\\House'"""
        try:
            if not FilePath:
                return None
            from Core.PathNormalize import NormalizeCanonical, ExtractShowFolder as ExtractShow
            Normalized = NormalizeCanonical(FilePath)
            Show = ExtractShow(Normalized)
            if Show == 'Unknown':
                return None
            Root = Normalized.split('\\', 1)[0]
            if not Root:
                return None
            return Root + '\\' + Show
        except Exception:
            return None

    # directive: path-schema-migration | # see path.S8
    def _MapRowToModel(self, Row) -> ShowSettingModel:
        """Map a database row to a ShowSettingModel; synthesizes ShowFolder from typed pair."""
        Sid = Row.get('StorageRootId') if hasattr(Row, 'get') else Row['StorageRootId']
        Rel = Row.get('RelativePath') if hasattr(Row, 'get') else Row['RelativePath']
        ShowFolder = _SafeCanonical(Sid, Rel) if (Sid is not None and Rel) else ""
        return ShowSettingModel(
            Id=Row['Id'],
            StorageRootId=Sid,
            RelativePath=Rel or "",
            ShowFolder=ShowFolder,
            TargetResolution=Row['TargetResolution'],
            CreatedDate=Row.get('CreatedDate'),
            LastModifiedDate=Row.get('LastModifiedDate')
        )
