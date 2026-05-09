from typing import List, Optional, Dict, Any
from Core.Database.BaseRepository import BaseRepository
from Core.Database.DatabaseService import EscapeLikePattern
from Features.Profiles.Models.TranscodeProfileModel import TranscodeProfileModel
from Features.Profiles.Models.ProfileThresholdModel import ProfileThresholdModel
from Core.Logging.LoggingService import LoggingService


class ProfileRepository(BaseRepository):
    """Data access for profiles, thresholds, and codec configuration."""

    def GetAllProfiles(self) -> List[TranscodeProfileModel]:
        """Get all transcoding profiles."""
        query = """SELECT Id, ProfileName, Description, CreatedDate, LastModified,
                          Codec, Preset, FilmGrain, YadifMode, YadifParity, YadifDeint, UseNvidiaHardware, SortOrder
                   FROM Profiles ORDER BY SortOrder, ProfileName"""
        rows = self.ExecuteQuery(query)

        profiles = []
        for row in rows:
            profile = TranscodeProfileModel(
                Id=row['Id'],
                ProfileName=row['ProfileName'],
                Description=row['Description'],
                CreatedDate=row['CreatedDate'],
                LastModified=row['LastModified'],
                Codec=row['Codec'] if row['Codec'] is not None else 'libsvtav1',
                Preset=row['Preset'] if row['Preset'] is not None else 6,
                FilmGrain=row['FilmGrain'] if row['FilmGrain'] is not None else 10,
                YadifMode=row['YadifMode'] if row['YadifMode'] is not None else 1,
                YadifParity=row['YadifParity'] if row['YadifParity'] is not None else 1,
                YadifDeint=row['YadifDeint'] if row['YadifDeint'] is not None else 1,
                UseNvidiaHardware=row['UseNvidiaHardware'] if row['UseNvidiaHardware'] is not None else 0,
                SortOrder=row['SortOrder'] if row['SortOrder'] is not None else 0
            )
            profiles.append(profile)

        return profiles

    def GetProfileById(self, ProfileId: int) -> Optional[TranscodeProfileModel]:
        """Get a specific profile by ID."""
        query = """SELECT Id, ProfileName, Description, CreatedDate, LastModified,
                          Codec, Preset, FilmGrain, YadifMode, YadifParity, YadifDeint, UseNvidiaHardware
                   FROM Profiles WHERE Id = %s"""
        rows = self.ExecuteQuery(query, (ProfileId,))

        if not rows:
            return None

        row = rows[0]
        return TranscodeProfileModel(
            Id=row['Id'],
            ProfileName=row['ProfileName'],
            Description=row['Description'],
            CreatedDate=row['CreatedDate'],
            LastModified=row['LastModified'],
            Codec=row['Codec'] if row['Codec'] is not None else 'libsvtav1',
            Preset=row['Preset'] if row['Preset'] is not None else 6,
            FilmGrain=row['FilmGrain'] if row['FilmGrain'] is not None else 10,
            YadifMode=row['YadifMode'] if row['YadifMode'] is not None else 1,
            YadifParity=row['YadifParity'] if row['YadifParity'] is not None else 1,
            YadifDeint=row['YadifDeint'] if row['YadifDeint'] is not None else 1,
            UseNvidiaHardware=row['UseNvidiaHardware'] if row['UseNvidiaHardware'] is not None else 0
        )

    def SaveProfile(self, Profile: TranscodeProfileModel) -> int:
        """Save a profile (insert or update) and return the profile ID."""
        try:
            LoggingService.LogFunctionEntry("SaveProfile", "ProfileRepository", Profile.Id, Profile.ProfileName, Profile.Description)

            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()

                if Profile.Id is None:
                    LoggingService.LogInfo("Inserting new profile...", "ProfileRepository", "SaveProfile")
                    query = """
                        INSERT INTO Profiles (ProfileName, Description, CreatedDate, LastModified,
                                             Codec, Preset, FilmGrain, YadifMode, YadifParity, YadifDeint, UseNvidiaHardware, SortOrder)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, (SELECT COALESCE(MAX(SortOrder), 0) + 1 FROM Profiles))
                        RETURNING Id
                    """
                    parameters = (Profile.ProfileName, Profile.Description, Profile.CreatedDate, Profile.LastModified,
                                 Profile.Codec, Profile.Preset, Profile.FilmGrain, Profile.YadifMode,
                                 Profile.YadifParity, Profile.YadifDeint, Profile.UseNvidiaHardware)
                    LoggingService.LogInfo("Insert parameters: {}", "ProfileRepository", "SaveProfile", parameters)
                    cursor.execute(query, parameters)
                    profile_id = cursor.fetchone()[0]
                    connection.commit()
                    LoggingService.LogInfo("Profile inserted with ID: {}", "ProfileRepository", "SaveProfile", profile_id)
                    return profile_id
                else:
                    LoggingService.LogInfo("Updating existing profile with ID: {}", "ProfileRepository", "SaveProfile", Profile.Id)
                    query = """
                        UPDATE Profiles
                        SET ProfileName = %s, Description = %s, LastModified = %s,
                            Codec = %s, Preset = %s, FilmGrain = %s, YadifMode = %s, YadifParity = %s, YadifDeint = %s, UseNvidiaHardware = %s
                        WHERE Id = %s
                    """
                    parameters = (Profile.ProfileName, Profile.Description, Profile.LastModified,
                                 Profile.Codec, Profile.Preset, Profile.FilmGrain, Profile.YadifMode,
                                 Profile.YadifParity, Profile.YadifDeint, Profile.UseNvidiaHardware, Profile.Id)
                    LoggingService.LogInfo("Update parameters: {}", "ProfileRepository", "SaveProfile", parameters)
                    cursor.execute(query, parameters)
                    connection.commit()
                    affected_rows = cursor.rowcount
                    LoggingService.LogInfo("Profile update affected {} rows", "ProfileRepository", "SaveProfile", affected_rows)
                    return Profile.Id
            finally:
                self.DatabaseService.CloseConnection(connection)
        except Exception as e:
            LoggingService.LogException("Exception in SaveProfile", e, "ProfileRepository", "SaveProfile")
            raise

    def DeleteProfile(self, ProfileId: int) -> bool:
        """Delete a profile and its associated thresholds."""
        try:
            self.ExecuteNonQuery("DELETE FROM ProfileThresholds WHERE ProfileId = %s", (ProfileId,))
            affected_rows = self.ExecuteNonQuery("DELETE FROM Profiles WHERE Id = %s", (ProfileId,))
            return affected_rows > 0
        except Exception:
            return False

    def UpdateProfileOrder(self, OrderedIds: list) -> bool:
        """Update SortOrder for all profiles based on the provided ID order."""
        try:
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()
                for Index, ProfileId in enumerate(OrderedIds):
                    cursor.execute("UPDATE Profiles SET SortOrder = %s WHERE Id = %s", (Index + 1, int(ProfileId)))
                connection.commit()
                return True
            finally:
                self.DatabaseService.CloseConnection(connection)
        except Exception as e:
            LoggingService.LogException("Exception in UpdateProfileOrder", e, "ProfileRepository", "UpdateProfileOrder")
            return False

    def GetThresholdsByProfileId(self, ProfileId: int) -> List[ProfileThresholdModel]:
        """Get all thresholds for a specific profile."""
        query = """
            SELECT Id, ProfileId, Resolution, Under30MinMB, Under65MinMB, Over65MinMB,
                   VideoBitrateKbps, AudioBitrateKbps, FallbackVideoBitrateKbps,
                   FallbackAudioBitrateKbps, TranscodeDownTo, Quality, KeepSource, ContainerType
            FROM ProfileThresholds
            WHERE ProfileId = %s
            ORDER BY Resolution
        """
        rows = self.ExecuteQuery(query, (ProfileId,))

        thresholds = []
        for row in rows:
            threshold = ProfileThresholdModel(
                Id=row['Id'],
                ProfileId=row['ProfileId'],
                Resolution=row['Resolution'],
                Under30MinMB=row['Under30MinMB'],
                Under65MinMB=row['Under65MinMB'],
                Over65MinMB=row['Over65MinMB'],
                VideoBitrateKbps=row['VideoBitrateKbps'],
                AudioBitrateKbps=row['AudioBitrateKbps'],
                FallbackVideoBitrateKbps=row['FallbackVideoBitrateKbps'],
                FallbackAudioBitrateKbps=row['FallbackAudioBitrateKbps'],
                TranscodeDownTo=row['TranscodeDownTo'],
                Quality=row['Quality'],
                KeepSource=bool(row['keepsource'] if 'keepsource' in row else 0),
                ContainerType=row['containertype'] if 'containertype' in row else 'mp4'
            )
            thresholds.append(threshold)

        return thresholds

    def GetAllProfileThresholds(self) -> List[ProfileThresholdModel]:
        """Get all thresholds from all profiles."""
        query = """
            SELECT Id, ProfileId, Resolution, Under30MinMB, Under65MinMB, Over65MinMB,
                   VideoBitrateKbps, AudioBitrateKbps, FallbackVideoBitrateKbps,
                   FallbackAudioBitrateKbps, TranscodeDownTo, Quality, KeepSource, ContainerType
            FROM ProfileThresholds
            ORDER BY ProfileId, Resolution
        """
        rows = self.ExecuteQuery(query)

        thresholds = []
        for row in rows:
            threshold = ProfileThresholdModel(
                Id=row['Id'],
                ProfileId=row['ProfileId'],
                Resolution=row['Resolution'],
                Under30MinMB=row['Under30MinMB'],
                Under65MinMB=row['Under65MinMB'],
                Over65MinMB=row['Over65MinMB'],
                VideoBitrateKbps=row['VideoBitrateKbps'],
                AudioBitrateKbps=row['AudioBitrateKbps'],
                FallbackVideoBitrateKbps=row['FallbackVideoBitrateKbps'],
                FallbackAudioBitrateKbps=row['FallbackAudioBitrateKbps'],
                TranscodeDownTo=row['TranscodeDownTo'],
                Quality=row['Quality'],
                KeepSource=bool(row['keepsource'] if 'keepsource' in row else 0),
                ContainerType=row['containertype'] if 'containertype' in row else 'mp4'
            )
            thresholds.append(threshold)

        return thresholds

    def SaveThreshold(self, Threshold: ProfileThresholdModel) -> int:
        """Save a threshold (insert or update) and return the threshold ID."""
        try:
            LoggingService.LogFunctionEntry("SaveThreshold", "ProfileRepository", Threshold.Id, Threshold.ProfileId, Threshold.Resolution)

            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()

                if Threshold.Id is None:
                    LoggingService.LogInfo("Inserting new threshold...")
                    query = """
                        INSERT INTO ProfileThresholds
                        (ProfileId, Resolution, Under30MinMB, Under65MinMB, Over65MinMB,
                         VideoBitrateKbps, AudioBitrateKbps, FallbackVideoBitrateKbps,
                         FallbackAudioBitrateKbps, TranscodeDownTo, Quality, KeepSource, ContainerType)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING Id
                    """
                    parameters = (
                        Threshold.ProfileId, Threshold.Resolution, Threshold.Under30MinMB,
                        Threshold.Under65MinMB, Threshold.Over65MinMB, Threshold.VideoBitrateKbps,
                        Threshold.AudioBitrateKbps, Threshold.FallbackVideoBitrateKbps,
                        Threshold.FallbackAudioBitrateKbps,
                        Threshold.TranscodeDownTo if Threshold.TranscodeDownTo is not None else '',
                        Threshold.Quality, Threshold.KeepSource, 'mp4'
                    )
                    LoggingService.LogInfo(f"Insert threshold parameters: {parameters}", "SaveThreshold", "ProfileRepository")
                    cursor.execute(query, parameters)
                    threshold_id = cursor.fetchone()[0]
                    connection.commit()
                    LoggingService.LogInfo(f"Threshold inserted with ID: {threshold_id}", "SaveThreshold", "ProfileRepository")
                    return threshold_id
                else:
                    LoggingService.LogInfo(f"Updating existing threshold with ID: {Threshold.Id}", "SaveThreshold", "ProfileRepository")
                    query = """
                        UPDATE ProfileThresholds
                        SET ProfileId = %s, Resolution = %s, Under30MinMB = %s, Under65MinMB = %s,
                            Over65MinMB = %s, VideoBitrateKbps = %s, AudioBitrateKbps = %s,
                            FallbackVideoBitrateKbps = %s, FallbackAudioBitrateKbps = %s,
                            TranscodeDownTo = %s, Quality = %s, KeepSource = %s
                        WHERE Id = %s
                    """
                    parameters = (
                        Threshold.ProfileId, Threshold.Resolution, Threshold.Under30MinMB,
                        Threshold.Under65MinMB, Threshold.Over65MinMB, Threshold.VideoBitrateKbps,
                        Threshold.AudioBitrateKbps, Threshold.FallbackVideoBitrateKbps,
                        Threshold.FallbackAudioBitrateKbps,
                        Threshold.TranscodeDownTo if Threshold.TranscodeDownTo is not None else '',
                        Threshold.Quality, Threshold.KeepSource, Threshold.Id
                    )
                    LoggingService.LogInfo(f"Update threshold parameters: {parameters}", "SaveThreshold", "ProfileRepository")
                    cursor.execute(query, parameters)
                    connection.commit()
                    affected_rows = cursor.rowcount
                    LoggingService.LogInfo(f"Threshold update affected {affected_rows} rows", "SaveThreshold", "ProfileRepository")
                    return Threshold.Id
            finally:
                self.DatabaseService.CloseConnection(connection)
        except Exception as e:
            LoggingService.LogException("Exception in SaveThreshold", e, "ProfileRepository", "SaveThreshold")
            raise

    def DeleteThreshold(self, ThresholdId: int) -> bool:
        """Delete a threshold."""
        affected_rows = self.ExecuteNonQuery("DELETE FROM ProfileThresholds WHERE Id = %s", (ThresholdId,))
        return affected_rows > 0

    def UpdateMediaFilesProfileByRootFolder(self, RootFolderPath: str, ProfileId: int) -> int:
        """Update AssignedProfile for all MediaFiles in a specific root folder.

        Triggers PriorityScore recompute for affected files (priority-materialization.feature.md
        criterion 8). Recompute failure does not roll back the AssignedProfile update.
        """
        try:
            LoggingService.LogFunctionEntry("UpdateMediaFilesProfileByRootFolder", "ProfileRepository", RootFolderPath, ProfileId)

            profile = self.GetProfileById(ProfileId)
            profileName = profile.ProfileName if profile else f"ProfileId_{ProfileId}"

            # First, capture the IDs that will be affected (so we can recompute their priority).
            escapedPath = EscapeLikePattern(RootFolderPath)
            affectedRows = self.ExecuteQuery(
                "SELECT Id FROM MediaFiles WHERE LOWER(FilePath) LIKE LOWER(%s) || '%%' ESCAPE '!'",
                (escapedPath,)
            )
            affectedIds = [r['Id'] for r in affectedRows]

            query = """
                UPDATE MediaFiles
                SET AssignedProfile = %s
                WHERE LOWER(FilePath) LIKE LOWER(%s) || '%%' ESCAPE '!'
            """
            filesUpdated = self.ExecuteNonQuery(query, (profileName, escapedPath))
            LoggingService.LogInfo(f"Updated {filesUpdated} media files in root folder '{RootFolderPath}' to use profile '{profileName}'", "ProfileRepository", "UpdateMediaFilesProfileByRootFolder")

            if affectedIds:
                try:
                    from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
                    Service = QueueManagementBusinessService()
                    # Process in batches to keep the bulk UPDATE VALUES clause manageable.
                    BatchSize = 1000
                    for i in range(0, len(affectedIds), BatchSize):
                        Service.ComputePriorityScoresForFiles(affectedIds[i:i+BatchSize])
                except Exception as PriorityEx:
                    LoggingService.LogException(
                        f"Priority recompute after AssignedProfile bulk-update failed for {len(affectedIds)} files in '{RootFolderPath}' -- profile is assigned, scores stale",
                        PriorityEx, "ProfileRepository", "UpdateMediaFilesProfileByRootFolder"
                    )

            return filesUpdated

        except Exception as e:
            LoggingService.LogException("Exception updating media files profile by root folder", e, "ProfileRepository", "UpdateMediaFilesProfileByRootFolder")
            return 0

    def GetProfileQuality(self, ProfileName: str) -> Optional[int]:
        """Get the Quality value from ProfileThresholds for a given profile name."""
        try:
            LoggingService.LogFunctionEntry("GetProfileQuality", "ProfileRepository", ProfileName)

            query = """
                SELECT pt.Quality
                FROM ProfileThresholds pt
                JOIN Profiles p ON pt.ProfileId = p.Id
                WHERE p.ProfileName = %s
                LIMIT 1
            """
            rows = self.ExecuteQuery(query, (ProfileName,))

            if rows:
                quality = rows[0]['Quality']
                LoggingService.LogInfo(f"Found Quality {quality} for Profile {ProfileName}", "ProfileRepository", "GetProfileQuality")
                return quality
            else:
                LoggingService.LogWarning(f"No Quality found for Profile {ProfileName}", "ProfileRepository", "GetProfileQuality")
                return None

        except Exception as e:
            LoggingService.LogException("Exception getting profile quality", e, "ProfileRepository", "GetProfileQuality")
            return None

    def GetProfileQualityForTargetResolution(self, ProfileName: str, SourceResolution: str) -> Optional[int]:
        """Get the Quality value from ProfileThresholds for the target resolution based on TranscodeDownTo setting."""
        try:
            LoggingService.LogFunctionEntry("GetProfileQualityForTargetResolution", "ProfileRepository", ProfileName, SourceResolution)

            resolutionCategory = self._ConvertPixelDimensionsToResolutionCategory(SourceResolution)
            LoggingService.LogInfo(f"Converted {SourceResolution} to {resolutionCategory}", "ProfileRepository", "GetProfileQualityForTargetResolution")

            query = """
                SELECT pt.TranscodeDownTo
                FROM ProfileThresholds pt
                JOIN Profiles p ON pt.ProfileId = p.Id
                WHERE p.ProfileName = %s AND pt.Resolution = %s
                LIMIT 1
            """
            rows = self.ExecuteQuery(query, (ProfileName, resolutionCategory))

            if not rows:
                LoggingService.LogWarning(f"No TranscodeDownTo found for Profile {ProfileName} and Resolution {SourceResolution}", "ProfileRepository", "GetProfileQualityForTargetResolution")
                return None

            targetResolution = rows[0]['TranscodeDownTo']
            if not targetResolution:
                LoggingService.LogInfo(f"No TranscodeDownTo set for Profile {ProfileName} and Resolution {SourceResolution}", "ProfileRepository", "GetProfileQualityForTargetResolution")
                return None

            if targetResolution == 'No downscaling':
                query = """
                    SELECT pt.Quality
                    FROM ProfileThresholds pt
                    JOIN Profiles p ON pt.ProfileId = p.Id
                    WHERE p.ProfileName = %s AND pt.Resolution = %s
                    LIMIT 1
                """
                rows = self.ExecuteQuery(query, (ProfileName, resolutionCategory))
            else:
                query = """
                    SELECT pt.Quality
                    FROM ProfileThresholds pt
                    JOIN Profiles p ON pt.ProfileId = p.Id
                    WHERE p.ProfileName = %s AND pt.Resolution = %s
                    LIMIT 1
                """
                rows = self.ExecuteQuery(query, (ProfileName, targetResolution))

            if rows:
                quality = rows[0]['Quality']
                LoggingService.LogInfo(f"Found Quality {quality} for Profile {ProfileName} targeting {targetResolution} (from source {SourceResolution})", "ProfileRepository", "GetProfileQualityForTargetResolution")
                return quality
            else:
                LoggingService.LogWarning(f"No Quality found for Profile {ProfileName} and target Resolution {targetResolution}", "ProfileRepository", "GetProfileQualityForTargetResolution")
                return None

        except Exception as e:
            LoggingService.LogException("Exception getting profile quality for target resolution", e, "ProfileRepository", "GetProfileQualityForTargetResolution")
            return None

    def GetProfileSettingsForTargetResolution(self, ProfileName: str, SourceResolution: str) -> Optional[Dict[str, Any]]:
        """Get all quality settings from ProfileThresholds for the target resolution based on TranscodeDownTo setting."""
        try:
            LoggingService.LogFunctionEntry("GetProfileSettingsForTargetResolution", "ProfileRepository", ProfileName, SourceResolution)

            query = """
                SELECT pt.TranscodeDownTo
                FROM ProfileThresholds pt
                JOIN Profiles p ON pt.ProfileId = p.Id
                WHERE p.ProfileName = %s AND pt.Resolution = %s
                LIMIT 1
            """
            rows = self.ExecuteQuery(query, (ProfileName, SourceResolution))
            foundResolution = SourceResolution

            if not rows:
                resolutionCategory = self._ConvertPixelDimensionsToResolutionCategory(SourceResolution)
                LoggingService.LogInfo(f"Resolution {SourceResolution} not found in database, using standardized resolution {resolutionCategory}", "ProfileRepository", "GetProfileSettingsForTargetResolution")
                rows = self.ExecuteQuery(query, (ProfileName, resolutionCategory))
                foundResolution = resolutionCategory
            else:
                LoggingService.LogInfo(f"Found exact resolution match for {SourceResolution}", "ProfileRepository", "GetProfileSettingsForTargetResolution")

            if not rows:
                LoggingService.LogWarning(f"No profile settings found for Profile '{ProfileName}' and Resolution '{foundResolution}' (original: {SourceResolution})", "ProfileRepository", "GetProfileSettingsForTargetResolution")
                return None

            targetResolution = rows[0]['TranscodeDownTo']
            if not targetResolution:
                LoggingService.LogInfo(f"No TranscodeDownTo set for Profile {ProfileName} and Resolution {SourceResolution}, treating as 'No downscaling'", "ProfileRepository", "GetProfileSettingsForTargetResolution")
                targetResolution = 'No downscaling'

            settingsQuery = """
                SELECT pt.VideoBitrateKbps, pt.AudioBitrateKbps, pt.Quality, pt.Resolution,
                       p.Codec, p.Preset, p.FilmGrain, p.YadifMode, p.YadifParity, p.YadifDeint, p.UseNvidiaHardware, pt.ContainerType, p.Id as ProfileId
                FROM ProfileThresholds pt
                JOIN Profiles p ON pt.ProfileId = p.Id
                WHERE p.ProfileName = %s AND pt.Resolution = %s
                LIMIT 1
            """

            if targetResolution == 'No downscaling':
                rows = self.ExecuteQuery(settingsQuery, (ProfileName, foundResolution))
            else:
                rows = self.ExecuteQuery(settingsQuery, (ProfileName, targetResolution))

            if rows:
                row = rows[0]
                actualTargetResolution = SourceResolution if targetResolution == 'No downscaling' else targetResolution
                settings = {
                    'VideoBitrateKbps': row['VideoBitrateKbps'],
                    'AudioBitrateKbps': row['AudioBitrateKbps'],
                    'Quality': row['Quality'],
                    'TargetResolution': actualTargetResolution,
                    'Codec': row['Codec'],
                    'Preset': row['Preset'],
                    'FilmGrain': row['FilmGrain'],
                    'YadifMode': row['YadifMode'],
                    'YadifParity': row['YadifParity'],
                    'YadifDeint': row['YadifDeint'],
                    'UseNvidiaHardware': row['UseNvidiaHardware'],
                    'ContainerType': row['ContainerType'],
                    'ProfileId': row['ProfileId']
                }
                LoggingService.LogInfo(f"Found ProfileSettings for {ProfileName} targeting {actualTargetResolution}: {settings}", "ProfileRepository", "GetProfileSettingsForTargetResolution")
                return settings
            else:
                LoggingService.LogWarning(f"No ProfileSettings found for Profile {ProfileName} and target Resolution {targetResolution}", "ProfileRepository", "GetProfileSettingsForTargetResolution")
                return None

        except Exception as e:
            LoggingService.LogException("Exception getting profile settings for target resolution", e, "ProfileRepository", "GetProfileSettingsForTargetResolution")
            return None

    def _ConvertPixelDimensionsToResolutionCategory(self, PixelDimensions: str) -> str:
        """Convert pixel dimensions (e.g., '3840x2160') to resolution category (e.g., '2160p')."""
        try:
            if not PixelDimensions or 'x' not in PixelDimensions:
                return PixelDimensions

            height = int(PixelDimensions.split('x')[1])

            if height >= 2160:
                return "2160p"
            elif height >= 1080:
                return "1080p"
            elif height >= 720:
                return "720p"
            elif height >= 480:
                return "480p"
            else:
                return "480p"
        except Exception:
            return PixelDimensions

    def GetCodecFlagsByCodecName(self, CodecName: str) -> Optional[Dict[str, Any]]:
        """Get codec flags by codec name."""
        try:
            LoggingService.LogFunctionEntry("GetCodecFlagsByCodecName", "ProfileRepository", CodecName)

            query = """
            SELECT Id, CodecName, DisplayName, PresetType, PresetMin, PresetMax, PresetDefault,
                   PresetOptions, FilmGrainType, FilmGrainMin, FilmGrainMax, FilmGrainDefault,
                   TuneOptions, CreatedDate, LastModified
            FROM CodecFlags
            WHERE CodecName = %s
            """
            rows = self.ExecuteQuery(query, (CodecName,))

            if not rows:
                LoggingService.LogWarning(f"No codec flags found for codec: {CodecName}", "ProfileRepository", "GetCodecFlagsByCodecName")
                return None

            row = rows[0]
            LoggingService.LogInfo(f"Retrieved codec flags for {CodecName}", "ProfileRepository", "GetCodecFlagsByCodecName")
            return row

        except Exception as e:
            LoggingService.LogException("Exception getting codec flags by codec name", e, "ProfileRepository", "GetCodecFlagsByCodecName")
            return None

    def GetCodecParametersByCodecFlagsId(self, CodecFlagsId: int) -> List[Dict[str, Any]]:
        """Get codec parameters by codec flags ID."""
        try:
            LoggingService.LogFunctionEntry("GetCodecParametersByCodecFlagsId", "ProfileRepository", CodecFlagsId)

            query = """
            SELECT Id, CodecFlagsId, ParameterName, ParameterType, MinValue, MaxValue,
                   DefaultValue, Description, FFmpegFlag, CreatedDate
            FROM CodecParameters
            WHERE CodecFlagsId = %s
            ORDER BY ParameterName
            """
            rows = self.ExecuteQuery(query, (CodecFlagsId,))

            LoggingService.LogInfo(f"Retrieved {len(rows)} codec parameters for CodecFlagsId {CodecFlagsId}", "ProfileRepository", "GetCodecParametersByCodecFlagsId")
            return list(rows)

        except Exception as e:
            LoggingService.LogException("Exception getting codec parameters by codec flags ID", e, "ProfileRepository", "GetCodecParametersByCodecFlagsId")
            return []
