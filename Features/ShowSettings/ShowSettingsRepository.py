from typing import List, Optional, Dict, Any
from Core.Database.BaseRepository import BaseRepository
from Core.Database.DatabaseService import EscapeLikePattern
from Core.Logging.LoggingService import LoggingService
from Features.ShowSettings.Models.ShowSettingModel import ShowSettingModel


class ShowSettingsRepository(BaseRepository):
    """Repository for ShowSettings table operations."""

    def GetAllShowSettings(self) -> List[ShowSettingModel]:
        """Get all show settings ordered by ShowFolder."""
        try:
            query = """
                SELECT Id, ShowFolder, TargetResolution, CreatedDate, LastModifiedDate
                FROM ShowSettings
                ORDER BY ShowFolder
            """
            Rows = self.ExecuteQuery(query)
            return [self._MapRowToModel(Row) for Row in Rows]
        except Exception as Ex:
            LoggingService.LogException("Exception getting all show settings", Ex, "ShowSettingsRepository", "GetAllShowSettings")
            return []

    def GetShowSettingByFolder(self, ShowFolder: str) -> Optional[ShowSettingModel]:
        """Get show setting for a specific folder."""
        try:
            query = """
                SELECT Id, ShowFolder, TargetResolution, CreatedDate, LastModifiedDate
                FROM ShowSettings
                WHERE ShowFolder = %s
                LIMIT 1
            """
            Rows = self.ExecuteQuery(query, (ShowFolder,))
            if Rows:
                return self._MapRowToModel(Rows[0])
            return None
        except Exception as Ex:
            LoggingService.LogException("Exception getting show setting by folder", Ex, "ShowSettingsRepository", "GetShowSettingByFolder")
            return None

    def GetDefaultTargetResolution(self) -> Optional[str]:
        """Get the default target resolution (ShowFolder = '*')."""
        try:
            query = """
                SELECT TargetResolution
                FROM ShowSettings
                WHERE ShowFolder = '*'
                LIMIT 1
            """
            Rows = self.ExecuteQuery(query, ())
            if Rows:
                return Rows[0]['TargetResolution']
            return None
        except Exception as Ex:
            LoggingService.LogException("Exception getting default target resolution", Ex, "ShowSettingsRepository", "GetDefaultTargetResolution")
            return None

    def SaveShowSetting(self, Setting: ShowSettingModel) -> int:
        """Insert or update a show setting. Returns the Id."""
        try:
            Existing = self.GetShowSettingByFolder(Setting.ShowFolder)
            if Existing:
                query = """
                    UPDATE ShowSettings
                    SET TargetResolution = %s, LastModifiedDate = NOW()
                    WHERE ShowFolder = %s
                    RETURNING Id
                """
                self.ExecuteNonQuery(query, (Setting.TargetResolution, Setting.ShowFolder))
                return Existing.Id
            else:
                query = """
                    INSERT INTO ShowSettings (ShowFolder, TargetResolution, CreatedDate, LastModifiedDate)
                    VALUES (%s, %s, NOW(), NOW())
                    RETURNING Id
                """
                self.ExecuteNonQuery(query, (Setting.ShowFolder, Setting.TargetResolution))
                return self.GetLastInsertId()
        except Exception as Ex:
            LoggingService.LogException("Exception saving show setting", Ex, "ShowSettingsRepository", "SaveShowSetting")
            return 0

    def SetSeriesAssignedProfile(self, ShowFolder: str, AssignedProfile: Optional[str]) -> int:
        """Set or clear the per-show AssignedProfile.

        Owns: transcode-vs-remux-routing.feature.md (per-show profile override).
        AssignedProfile=None clears the override; the show then inherits
        SystemSettings.DefaultProfileName via _GetEffectiveProfile.
        Caller is responsible for validating AssignedProfile against Profiles.
        Returns the Id of the affected ShowSettings row.
        """
        try:
            Existing = self.GetShowSettingByFolder(ShowFolder)
            if Existing:
                self.ExecuteNonQuery(
                    """UPDATE ShowSettings
                       SET AssignedProfile = %s, LastModifiedDate = NOW()
                       WHERE ShowFolder = %s""",
                    (AssignedProfile, ShowFolder),
                )
                return Existing.Id
            self.ExecuteNonQuery(
                """INSERT INTO ShowSettings (ShowFolder, TargetResolution, AssignedProfile, CreatedDate, LastModifiedDate)
                   VALUES (%s, '', %s, NOW(), NOW())""",
                (ShowFolder, AssignedProfile),
            )
            return self.GetLastInsertId()
        except Exception as Ex:
            LoggingService.LogException(
                f"Exception setting AssignedProfile for {ShowFolder!r}",
                Ex, "ShowSettingsRepository", "SetSeriesAssignedProfile"
            )
            return 0

    def BulkUpdateTargetResolution(self, ShowFolders: List[str], TargetResolution: str) -> int:
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

    def DeleteShowSetting(self, ShowFolder: str) -> bool:
        """Delete a show setting (reverts to default)."""
        try:
            query = "DELETE FROM ShowSettings WHERE ShowFolder = %s"
            AffectedRows = self.ExecuteNonQuery(query, (ShowFolder,))
            return AffectedRows > 0
        except Exception as Ex:
            LoggingService.LogException("Exception deleting show setting", Ex, "ShowSettingsRepository", "DeleteShowSetting")
            return False

    def GetSpecificTargetResolutionForFile(self, FilePath: str) -> Optional[str]:
        """Get the target resolution ONLY when there is a per-show ShowSettings row.

        Returns None when no specific row matches -- callers MUST then fall back
        to the profile's own `TranscodeDownTo` value, NOT to the `ShowFolder='*'`
        global default. This is the precedence the queue admission and worker
        paths use: profile drives default; ShowSettings overrides only when
        the operator has explicitly opted that show in.

        See `ShowSettings.feature.md` Success Criterion 1 and `KNOWN-ISSUES.md`
        for the regression this method prevents.
        """
        try:
            ShowFolder = self._ExtractShowFolder(FilePath)
            if not ShowFolder:
                return None
            Setting = self.GetShowSettingByFolder(ShowFolder)
            return Setting.TargetResolution if Setting else None
        except Exception as Ex:
            LoggingService.LogException(
                "Exception getting specific target resolution for file", Ex,
                "ShowSettingsRepository", "GetSpecificTargetResolutionForFile",
            )
            return None

    def GetTargetResolutionForFile(self, FilePath: str) -> Optional[str]:
        """Specific match if present; otherwise the `*` global default.

        DEPRECATED for the worker / queue-admission paths -- those should call
        `GetSpecificTargetResolutionForFile` and let the profile drive default
        behavior. Retained for UI display contexts (e.g. the Media page) where
        showing the effective target including the global default is correct.
        """
        try:
            Specific = self.GetSpecificTargetResolutionForFile(FilePath)
            if Specific is not None:
                return Specific
            return self.GetDefaultTargetResolution()
        except Exception as Ex:
            LoggingService.LogException(
                "Exception getting target resolution for file", Ex,
                "ShowSettingsRepository", "GetTargetResolutionForFile",
            )
            return None

    def GetShowsWithStats(self, RootDrive: str = None) -> List[Dict[str, Any]]:
        """Get all unique shows from MediaFiles with file count, total size, and current settings."""
        try:
            DriveFilter = ""
            Params = ()
            if RootDrive:
                DriveFilter = "WHERE mf.FilePath LIKE %s"
                Params = (RootDrive + '%',)

            query = f"""
                SELECT
                    split_part(replace(mf.FilePath, '\\', '/'), '/', 2) as ShowName,
                    MIN(split_part(mf.FilePath, '\\', 1) || '\\' || split_part(replace(mf.FilePath, '\\', '/'), '/', 2)) as ShowFolder,
                    COUNT(*) as FileCount,
                    ROUND(SUM(mf.SizeMB)::numeric / 1024, 1) as TotalGB,
                    MODE() WITHIN GROUP (ORDER BY mf.ResolutionCategory) as CommonResolution,
                    MODE() WITHIN GROUP (ORDER BY mf.Codec) as CommonCodec,
                    ss.TargetResolution as TargetResolution,
                    ss.AssignedProfile as AssignedProfile,
                    SUM(CASE WHEN mf.TranscodedByMediaVortex = true THEN 1 ELSE 0 END) as TranscodedCount
                FROM MediaFiles mf
                LEFT JOIN ShowSettings ss ON ss.ShowFolder = split_part(mf.FilePath, '\\', 1) || '\\' || split_part(replace(mf.FilePath, '\\', '/'), '/', 2)
                {DriveFilter}
                GROUP BY ShowName, ss.TargetResolution, ss.AssignedProfile
                HAVING COUNT(*) > 0
                ORDER BY SUM(mf.SizeMB) DESC
            """
            return self.ExecuteQuery(query, Params)
        except Exception as Ex:
            LoggingService.LogException("Exception getting shows with stats", Ex, "ShowSettingsRepository", "GetShowsWithStats")
            return []

    def _ExtractShowFolder(self, FilePath: str) -> Optional[str]:
        """Extract show folder from a file path. E.g., 'T:\\House\\Season 1\\ep.mp4' -> 'T:\\House'"""
        try:
            if not FilePath:
                return None
            # Normalize to forward slashes for splitting
            Parts = FilePath.replace('\\', '/').split('/')
            if len(Parts) >= 2:
                # Reconstruct with backslashes (matching DB format): "T:\House"
                return Parts[0] + '\\' + Parts[1]
            return None
        except Exception:
            return None

    def _MapRowToModel(self, Row) -> ShowSettingModel:
        """Map a database row to a ShowSettingModel."""
        return ShowSettingModel(
            Id=Row['Id'],
            ShowFolder=Row['ShowFolder'],
            TargetResolution=Row['TargetResolution'],
            CreatedDate=Row.get('CreatedDate'),
            LastModifiedDate=Row.get('LastModifiedDate')
        )
