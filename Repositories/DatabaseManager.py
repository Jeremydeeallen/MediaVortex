from typing import List, Optional, Dict, Any
from Models.TranscodeProfileModel import TranscodeProfileModel
from Models.ProfileThresholdModel import ProfileThresholdModel
from Models.RootFolderModel import RootFolderModel
from Models.MediaFileModel import MediaFileModel
from Models.SeasonModel import SeasonModel
from Models.FileScanResultModel import FileScanResultModel
from Services.DatabaseService import DatabaseService
from Services.LoggingService import LoggingService


class DatabaseManager:
    """Handles business logic for data access operations."""
    
    def __init__(self, DatabaseServiceInstance: DatabaseService = None):
        self.DatabaseService = DatabaseServiceInstance or DatabaseService()
    
    # Profile Management Methods
    def GetAllProfiles(self) -> List[TranscodeProfileModel]:
        """Get all transcoding profiles."""
        query = "SELECT Id, ProfileName, Description, CreatedDate, LastModified FROM Profiles ORDER BY ProfileName"
        rows = self.DatabaseService.ExecuteQuery(query)
        
        profiles = []
        for row in rows:
            profile = TranscodeProfileModel(
                Id=row['Id'],
                ProfileName=row['ProfileName'],
                Description=row['Description'],
                CreatedDate=row['CreatedDate'],
                LastModified=row['LastModified']
            )
            profiles.append(profile)
        
        return profiles
    
    def GetProfileById(self, ProfileId: int) -> Optional[TranscodeProfileModel]:
        """Get a specific profile by ID."""
        query = "SELECT Id, ProfileName, Description, CreatedDate, LastModified FROM Profiles WHERE Id = ?"
        rows = self.DatabaseService.ExecuteQuery(query, (ProfileId,))
        
        if not rows:
            return None
        
        row = rows[0]
        return TranscodeProfileModel(
            Id=row['Id'],
            ProfileName=row['ProfileName'],
            Description=row['Description'],
            CreatedDate=row['CreatedDate'],
            LastModified=row['LastModified']
        )
    
    def SaveProfile(self, Profile: TranscodeProfileModel) -> int:
        """Save a profile (insert or update) and return the profile ID."""
        try:
            LoggingService.LogFunctionEntry("SaveProfile", "DatabaseManager", Profile.Id, Profile.ProfileName, Profile.Description)
            
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()
                
                if profile.Id is None:
                    # Insert new profile
                    LoggingService.LogInfo("Inserting new profile...", "DatabaseManager", "SaveProfile")
                    query = """
                        INSERT INTO Profiles (ProfileName, Description, CreatedDate, LastModified)
                        VALUES (?, ?, ?, ?)
                    """
                    parameters = (profile.ProfileName, profile.Description, profile.CreatedDate, profile.LastModified)
                    LoggingService.LogInfo("Insert parameters: {}", "DatabaseManager", "SaveProfile", parameters)
                    cursor.execute(query, parameters)
                    connection.commit()
                    profile_id = cursor.lastrowid
                    LoggingService.LogInfo("Profile inserted with ID: {}", "DatabaseManager", "SaveProfile", profile_id)
                    return profile_id
                else:
                    # Update existing profile
                    LoggingService.LogInfo("Updating existing profile with ID: {}", "DatabaseManager", "SaveProfile", profile.Id)
                    query = """
                        UPDATE Profiles 
                        SET ProfileName = ?, Description = ?, LastModified = ?
                        WHERE Id = ?
                    """
                    parameters = (profile.ProfileName, profile.Description, profile.LastModified, profile.Id)
                    LoggingService.LogInfo("Update parameters: {}", "DatabaseManager", "SaveProfile", parameters)
                    cursor.execute(query, parameters)
                    connection.commit()
                    affected_rows = cursor.rowcount
                    LoggingService.LogInfo("Profile update affected {} rows", "DatabaseManager", "SaveProfile", affected_rows)
                    return profile.Id
            finally:
                connection.close()
        except Exception as e:
            LoggingService.LogException("Exception in SaveProfile", e, "DatabaseManager", "SaveProfile")
            raise
    
    def DeleteProfile(self, ProfileId: int) -> bool:
        """Delete a profile and its associated thresholds."""
        try:
            # Delete associated thresholds first
            self.DatabaseService.ExecuteNonQuery("DELETE FROM ProfileThresholds WHERE ProfileId = ?", (ProfileId,))
            
            # Delete the profile
            affected_rows = self.DatabaseService.ExecuteNonQuery("DELETE FROM Profiles WHERE Id = ?", (ProfileId,))
            return affected_rows > 0
        except Exception:
            return False
    
    # Profile Threshold Management Methods
    def GetThresholdsByProfileId(self, ProfileId: int) -> List[ProfileThresholdModel]:
        """Get all thresholds for a specific profile."""
        query = """
            SELECT Id, ProfileId, Resolution, Under30MinMB, Under65MinMB, Over65MinMB,
                   VideoBitrateKbps, AudioBitrateKbps, FallbackVideoBitrateKbps,
                   FallbackAudioBitrateKbps, TranscodeDownTo
            FROM ProfileThresholds 
            WHERE ProfileId = ?
            ORDER BY Resolution
        """
        rows = self.DatabaseService.ExecuteQuery(query, (ProfileId,))
        
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
                TranscodeDownTo=row['TranscodeDownTo']
            )
            thresholds.append(threshold)
        
        return thresholds
    
    def SaveThreshold(self, Threshold: ProfileThresholdModel) -> int:
        """Save a threshold (insert or update) and return the threshold ID."""
        try:
            LoggingService.LogFunctionEntry("SaveThreshold", "DatabaseManager", Threshold.Id, Threshold.ProfileId, Threshold.Resolution)
            
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()
                
                if threshold.Id is None:
                    # Insert new threshold
                    LoggingService.LogInfo("Inserting new threshold...")
                    query = """
                        INSERT INTO ProfileThresholds 
                        (ProfileId, Resolution, Under30MinMB, Under65MinMB, Over65MinMB,
                         VideoBitrateKbps, AudioBitrateKbps, FallbackVideoBitrateKbps,
                         FallbackAudioBitrateKbps, TranscodeDownTo)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    parameters = (
                        threshold.ProfileId, threshold.Resolution, threshold.Under30MinMB,
                        threshold.Under65MinMB, threshold.Over65MinMB, threshold.VideoBitrateKbps,
                        threshold.AudioBitrateKbps, threshold.FallbackVideoBitrateKbps,
                        threshold.FallbackAudioBitrateKbps, threshold.TranscodeDownTo
                    )
                    LoggingService.LogInfo("Insert threshold parameters: {}", "DatabaseManager", "SaveThreshold", parameters)
                    cursor.execute(query, parameters)
                    connection.commit()
                    threshold_id = cursor.lastrowid
                    LoggingService.LogInfo("Threshold inserted with ID: {}", "DatabaseManager", "SaveThreshold", threshold_id)
                    return threshold_id
                else:
                    # Update existing threshold
                    LoggingService.LogInfo("Updating existing threshold with ID: {}", "DatabaseManager", "SaveThreshold", threshold.Id)
                    query = """
                        UPDATE ProfileThresholds 
                        SET ProfileId = ?, Resolution = ?, Under30MinMB = ?, Under65MinMB = ?,
                            Over65MinMB = ?, VideoBitrateKbps = ?, AudioBitrateKbps = ?,
                            FallbackVideoBitrateKbps = ?, FallbackAudioBitrateKbps = ?,
                            TranscodeDownTo = ?
                        WHERE Id = ?
                    """
                    parameters = (
                        threshold.ProfileId, threshold.Resolution, threshold.Under30MinMB,
                        threshold.Under65MinMB, threshold.Over65MinMB, threshold.VideoBitrateKbps,
                        threshold.AudioBitrateKbps, threshold.FallbackVideoBitrateKbps,
                        threshold.FallbackAudioBitrateKbps, threshold.TranscodeDownTo, threshold.Id
                    )
                    LoggingService.LogInfo("Update threshold parameters: {}", "DatabaseManager", "SaveThreshold", parameters)
                    cursor.execute(query, parameters)
                    connection.commit()
                    affected_rows = cursor.rowcount
                    LoggingService.LogInfo("Threshold update affected {} rows", "DatabaseManager", "SaveThreshold", affected_rows)
                    return threshold.Id
            finally:
                connection.close()
        except Exception as e:
            LoggingService.LogException("Exception in SaveThreshold", e, "DatabaseManager", "SaveThreshold")
            raise
    
    def DeleteThreshold(self, ThresholdId: int) -> bool:
        """Delete a threshold."""
        affected_rows = self.DatabaseService.ExecuteNonQuery("DELETE FROM ProfileThresholds WHERE Id = ?", (ThresholdId,))
        return affected_rows > 0
    
    # Root Folder Management Methods
    def GetAllRootFolders(self) -> List[RootFolderModel]:
        """Get all root folders."""
        query = "SELECT Id, RootFolder, LastScannedDate, TotalSizeGB FROM RootFolders ORDER BY RootFolder"
        rows = self.DatabaseService.ExecuteQuery(query)
        
        rootFolders = []
        for row in rows:
            rootFolder = RootFolderModel(
                Id=row['Id'],
                RootFolder=row['RootFolder'],
                LastScannedDate=row['LastScannedDate'],
                TotalSizeGB=row['TotalSizeGB']
            )
            rootFolders.append(rootFolder)
        
        return rootFolders
    
    def GetRootFolderById(self, RootFolderId: int) -> Optional[RootFolderModel]:
        """Get a specific root folder by ID."""
        query = "SELECT Id, RootFolder, LastScannedDate, TotalSizeGB FROM RootFolders WHERE Id = ?"
        rows = self.DatabaseService.ExecuteQuery(query, (RootFolderId,))
        
        if not rows:
            return None
        
        row = rows[0]
        return RootFolderModel(
            Id=row['Id'],
            RootFolder=row['RootFolder'],
            LastScannedDate=row['LastScannedDate'],
            TotalSizeGB=row['TotalSizeGB']
        )
    
    def SaveRootFolder(self, RootFolder: RootFolderModel) -> int:
        """Save a root folder (insert or update) and return the root folder ID."""
        try:
            LoggingService.LogFunctionEntry("SaveRootFolder", 'DatabaseManager', f"RootFolder: {RootFolder.RootFolder}, Size: {RootFolder.TotalSizeGB}GB")
            
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()
                
                if rootFolder.Id is None:
                    # Insert new root folder
                    LoggingService.LogInfo("Inserting new root folder...")
                    query = """
                        INSERT INTO RootFolders (RootFolder, LastScannedDate, TotalSizeGB)
                        VALUES (?, ?, ?)
                    """
                    parameters = (rootFolder.RootFolder, rootFolder.LastScannedDate, rootFolder.TotalSizeGB)
                    LoggingService.LogInfo("Insert root folder parameters: {}", "DatabaseManager", "SaveRootFolder", parameters)
                    cursor.execute(query, parameters)
                    connection.commit()
                    rootFolderId = cursor.lastrowid
                    LoggingService.LogInfo("Root folder inserted with ID: {}", "DatabaseManager", "SaveRootFolder", rootFolderId)
                    return rootFolderId
                else:
                    # Update existing root folder
                    LoggingService.LogInfo("Updating existing root folder with ID: {}", "DatabaseManager", "SaveRootFolder", rootFolder.Id)
                    query = """
                        UPDATE RootFolders 
                        SET RootFolder = ?, LastScannedDate = ?, TotalSizeGB = ?
                        WHERE Id = ?
                    """
                    parameters = (rootFolder.RootFolder, rootFolder.LastScannedDate, rootFolder.TotalSizeGB, rootFolder.Id)
                    LoggingService.LogInfo("Update root folder parameters: {}", "DatabaseManager", "SaveRootFolder", parameters)
                    cursor.execute(query, parameters)
                    connection.commit()
                    affectedRows = cursor.rowcount
                    LoggingService.LogInfo("Root folder update affected {} rows", "DatabaseManager", "SaveRootFolder", affectedRows)
                    return rootFolder.Id
            finally:
                connection.close()
        except Exception as e:
            LoggingService.LogException("Exception in SaveRootFolder", e, "DatabaseManager", "SaveRootFolder")
            raise
    
    def DeleteRootFolder(self, RootFolderId: int) -> bool:
        """Delete a root folder and its associated media files."""
        try:
            # Delete associated media files first
            self.DatabaseService.ExecuteNonQuery("DELETE FROM MediaFiles WHERE Id IN (SELECT Id FROM MediaFiles WHERE FilePath LIKE (SELECT RootFolder || '%' FROM RootFolders WHERE Id = ?))", (RootFolderId,))
            
            # Delete the root folder
            affectedRows = self.DatabaseService.ExecuteNonQuery("DELETE FROM RootFolders WHERE Id = ?", (RootFolderId,))
            return affectedRows > 0
        except Exception:
            return False
    
    # Media File Management Methods
    def GetAllMediaFiles(self) -> List[MediaFileModel]:
        """Get all media files."""
        query = """
            SELECT Id, SeasonId, FilePath, FileName, SizeMB, VideoBitrateKbps, AudioBitrateKbps,
                   Resolution, Codec, DurationMinutes, FrameRate, LastScannedDate,
                   CompressionPotential, AssignedProfile
            FROM MediaFiles 
            ORDER BY FilePath
        """
        rows = self.DatabaseService.ExecuteQuery(query)
        
        mediaFiles = []
        for row in rows:
            mediaFile = MediaFileModel(
                Id=row['Id'],
                SeasonId=row['SeasonId'],
                FilePath=row['FilePath'],
                FileName=row['FileName'],
                SizeMB=row['SizeMB'],
                VideoBitrateKbps=row['VideoBitrateKbps'],
                AudioBitrateKbps=row['AudioBitrateKbps'],
                Resolution=row['Resolution'],
                Codec=row['Codec'],
                DurationMinutes=row['DurationMinutes'],
                FrameRate=row['FrameRate'],
                LastScannedDate=row['LastScannedDate'],
                CompressionPotential=row['CompressionPotential'],
                AssignedProfile=row['AssignedProfile']
            )
            mediaFiles.append(mediaFile)
        
        return mediaFiles
    
    def GetMediaFileById(self, MediaFileId: int) -> Optional[MediaFileModel]:
        """Get a specific media file by ID."""
        query = """
            SELECT Id, SeasonId, FilePath, FileName, SizeMB, VideoBitrateKbps, AudioBitrateKbps,
                   Resolution, Codec, DurationMinutes, FrameRate, LastScannedDate,
                   CompressionPotential, AssignedProfile
            FROM MediaFiles 
            WHERE Id = ?
        """
        rows = self.DatabaseService.ExecuteQuery(query, (MediaFileId,))
        
        if not rows:
            return None
        
        row = rows[0]
        return MediaFileModel(
            Id=row['Id'],
            SeasonId=row['SeasonId'],
            FilePath=row['FilePath'],
            FileName=row['FileName'],
            SizeMB=row['SizeMB'],
            VideoBitrateKbps=row['VideoBitrateKbps'],
            AudioBitrateKbps=row['AudioBitrateKbps'],
            Resolution=row['Resolution'],
            Codec=row['Codec'],
            DurationMinutes=row['DurationMinutes'],
            FrameRate=row['FrameRate'],
            LastScannedDate=row['LastScannedDate'],
            CompressionPotential=row['CompressionPotential'],
            AssignedProfile=row['AssignedProfile']
        )
    
    def SaveMediaFile(self, MediaFile: MediaFileModel) -> int:
        """Save a media file (insert or update) and return the media file ID."""
        try:
            LoggingService.LogFunctionEntry("SaveMediaFile", 'DatabaseManager', f"File: {MediaFile.FileName}, Path: {MediaFile.FilePath}")
            
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()
                
                if MediaFile.Id is None:
                    # Insert new media file
                    LoggingService.LogInfo("Inserting new media file...")
                    query = """
                        INSERT INTO MediaFiles 
                        (SeasonId, FilePath, FileName, SizeMB, VideoBitrateKbps, AudioBitrateKbps,
                         Resolution, Codec, DurationMinutes, FrameRate, LastScannedDate,
                         CompressionPotential, AssignedProfile)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    parameters = (
                        MediaFile.SeasonId, MediaFile.FilePath, MediaFile.FileName, MediaFile.SizeMB,
                        MediaFile.VideoBitrateKbps, MediaFile.AudioBitrateKbps, MediaFile.Resolution,
                        MediaFile.Codec, MediaFile.DurationMinutes, MediaFile.FrameRate,
                        MediaFile.LastScannedDate, MediaFile.CompressionPotential, MediaFile.AssignedProfile
                    )
                    LoggingService.LogInfo(f"Insert media file parameters: {parameters}", "DatabaseManager", "SaveMediaFile")
                    cursor.execute(query, parameters)
                    connection.commit()
                    mediaFileId = cursor.lastrowid
                    LoggingService.LogInfo(f"Media file inserted with ID: {mediaFileId}", "DatabaseManager", "SaveMediaFile")
                    return mediaFileId
                else:
                    # Update existing media file
                    LoggingService.LogInfo(f"Updating existing media file with ID: {MediaFile.Id}", "DatabaseManager", "SaveMediaFile")
                    query = """
                        UPDATE MediaFiles 
                        SET SeasonId = ?, FilePath = ?, FileName = ?, SizeMB = ?, VideoBitrateKbps = ?,
                            AudioBitrateKbps = ?, Resolution = ?, Codec = ?, DurationMinutes = ?,
                            FrameRate = ?, LastScannedDate = ?, CompressionPotential = ?, AssignedProfile = ?
                        WHERE Id = ?
                    """
                    parameters = (
                        MediaFile.SeasonId, MediaFile.FilePath, MediaFile.FileName, MediaFile.SizeMB,
                        MediaFile.VideoBitrateKbps, MediaFile.AudioBitrateKbps, MediaFile.Resolution,
                        MediaFile.Codec, MediaFile.DurationMinutes, MediaFile.FrameRate,
                        MediaFile.LastScannedDate, MediaFile.CompressionPotential, MediaFile.AssignedProfile,
                        MediaFile.Id
                    )
                    LoggingService.LogInfo(f"Update media file parameters: {parameters}", "DatabaseManager", "SaveMediaFile")
                    cursor.execute(query, parameters)
                    connection.commit()
                    affectedRows = cursor.rowcount
                    LoggingService.LogInfo(f"Media file update affected {affectedRows} rows", "DatabaseManager", "SaveMediaFile")
                    return MediaFile.Id
            finally:
                connection.close()
        except Exception as e:
            LoggingService.LogException("Exception in SaveMediaFile", e, "DatabaseManager", "SaveMediaFile")
            raise
    
    def DeleteMediaFile(self, MediaFileId: int) -> bool:
        """Delete a media file."""
        affectedRows = self.DatabaseService.ExecuteNonQuery("DELETE FROM MediaFiles WHERE Id = ?", (MediaFileId,))
        return affectedRows > 0
    
    def GetMediaFilesByRootFolder(self, RootFolderPath: str) -> List[MediaFileModel]:
        """Get all media files for a specific root folder."""
        query = """
            SELECT Id, SeasonId, FilePath, FileName, SizeMB, VideoBitrateKbps, AudioBitrateKbps,
                   Resolution, Codec, DurationMinutes, FrameRate, LastScannedDate,
                   CompressionPotential, AssignedProfile
            FROM MediaFiles 
            WHERE FilePath LIKE ?
            ORDER BY FilePath
        """
        rows = self.DatabaseService.ExecuteQuery(query, (f"{RootFolderPath}%",))
        
        mediaFiles = []
        for row in rows:
            mediaFile = MediaFileModel(
                Id=row['Id'],
                SeasonId=row['SeasonId'],
                FilePath=row['FilePath'],
                FileName=row['FileName'],
                SizeMB=row['SizeMB'],
                VideoBitrateKbps=row['VideoBitrateKbps'],
                AudioBitrateKbps=row['AudioBitrateKbps'],
                Resolution=row['Resolution'],
                Codec=row['Codec'],
                DurationMinutes=row['DurationMinutes'],
                FrameRate=row['FrameRate'],
                LastScannedDate=row['LastScannedDate'],
                CompressionPotential=row['CompressionPotential'],
                AssignedProfile=row['AssignedProfile']
            )
            mediaFiles.append(mediaFile)
        
        return mediaFiles
    
    # Season Management Methods
    def GetAllSeasons(self) -> List[SeasonModel]:
        """Get all seasons."""
        query = """
            SELECT Id, RootFolderId, SeasonName, SeasonNumber, EpisodeCount, 
                   TotalSizeGB, CreatedDate, LastUpdatedDate
            FROM Seasons 
            ORDER BY RootFolderId, SeasonNumber
        """
        rows = self.DatabaseService.ExecuteQuery(query)
        
        seasons = []
        for row in rows:
            season = SeasonModel(
                Id=row['Id'],
                RootFolderId=row['RootFolderId'],
                SeasonName=row['SeasonName'],
                SeasonNumber=row['SeasonNumber'],
                EpisodeCount=row['EpisodeCount'],
                TotalSizeGB=row['TotalSizeGB'],
                CreatedDate=row['CreatedDate'],
                LastUpdatedDate=row['LastUpdatedDate']
            )
            seasons.append(season)
        
        return seasons
    
    def GetSeasonById(self, SeasonId: int) -> Optional[SeasonModel]:
        """Get a specific season by ID."""
        query = """
            SELECT Id, RootFolderId, SeasonName, SeasonNumber, EpisodeCount, 
                   TotalSizeGB, CreatedDate, LastUpdatedDate
            FROM Seasons 
            WHERE Id = ?
        """
        rows = self.DatabaseService.ExecuteQuery(query, (SeasonId,))
        
        if not rows:
            return None
        
        row = rows[0]
        return SeasonModel(
            Id=row['Id'],
            RootFolderId=row['RootFolderId'],
            SeasonName=row['SeasonName'],
            SeasonNumber=row['SeasonNumber'],
            EpisodeCount=row['EpisodeCount'],
            TotalSizeGB=row['TotalSizeGB'],
            CreatedDate=row['CreatedDate'],
            LastUpdatedDate=row['LastUpdatedDate']
        )
    
    def SaveSeason(self, Season: SeasonModel) -> int:
        """Save a season (insert or update) and return the season ID."""
        try:
            if Season.Id is None:
                # Insert new season
                query = """
                    INSERT INTO Seasons 
                    (RootFolderId, SeasonName, SeasonNumber, EpisodeCount, TotalSizeGB, CreatedDate, LastUpdatedDate)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """
                parameters = (
                    Season.RootFolderId, Season.SeasonName, Season.SeasonNumber, 
                    Season.EpisodeCount, Season.TotalSizeGB, Season.CreatedDate, Season.LastUpdatedDate
                )
                Season.Id = self.DatabaseService.ExecuteNonQuery(query, parameters)
                LoggingService.LogInfo("Created new season: {} with ID: {}", Season.SeasonName, Season.Id)
            else:
                # Update existing season
                query = """
                    UPDATE Seasons 
                    SET RootFolderId = ?, SeasonName = ?, SeasonNumber = ?, EpisodeCount = ?,
                        TotalSizeGB = ?, LastUpdatedDate = ?
                    WHERE Id = ?
                """
                parameters = (
                    Season.RootFolderId, Season.SeasonName, Season.SeasonNumber, 
                    Season.EpisodeCount, Season.TotalSizeGB, Season.LastUpdatedDate, Season.Id
                )
                self.DatabaseService.ExecuteNonQuery(query, parameters)
                LoggingService.LogInfo("Updated season: {} with ID: {}", Season.SeasonName, Season.Id)
            
            return Season.Id
            
        except Exception as e:
            LoggingService.LogException("Error saving season", e)
            raise
    
    def DeleteSeason(self, SeasonId: int) -> bool:
        """Delete a season."""
        affectedRows = self.DatabaseService.ExecuteNonQuery("DELETE FROM Seasons WHERE Id = ?", (SeasonId,))
        return affectedRows > 0
    
    def GetSeasonsByRootFolder(self, RootFolderId: int) -> List[SeasonModel]:
        """Get all seasons for a specific root folder."""
        query = """
            SELECT Id, RootFolderId, SeasonName, SeasonNumber, EpisodeCount, 
                   TotalSizeGB, CreatedDate, LastUpdatedDate
            FROM Seasons 
            WHERE RootFolderId = ?
            ORDER BY SeasonNumber
        """
        rows = self.DatabaseService.ExecuteQuery(query, (RootFolderId,))
        
        seasons = []
        for row in rows:
            season = SeasonModel(
                Id=row['Id'],
                RootFolderId=row['RootFolderId'],
                SeasonName=row['SeasonName'],
                SeasonNumber=row['SeasonNumber'],
                EpisodeCount=row['EpisodeCount'],
                TotalSizeGB=row['TotalSizeGB'],
                CreatedDate=row['CreatedDate'],
                LastUpdatedDate=row['LastUpdatedDate']
            )
            seasons.append(season)
        
        return seasons
    
    # Advanced MediaFile Operations for Fuzzy Matching
    def GetMediaFileByPath(self, FilePath: str) -> Optional[MediaFileModel]:
        """Get a media file by exact path match."""
        query = """
            SELECT Id, SeasonId, FilePath, FileName, SizeMB, VideoBitrateKbps, AudioBitrateKbps,
                   Resolution, Codec, DurationMinutes, FrameRate, LastScannedDate,
                   CompressionPotential, AssignedProfile
            FROM MediaFiles 
            WHERE FilePath = ?
        """
        rows = self.DatabaseService.ExecuteQuery(query, (FilePath,))
        
        if not rows:
            return None
        
        row = rows[0]
        return MediaFileModel(
            Id=row['Id'],
            SeasonId=row['SeasonId'],
            FilePath=row['FilePath'],
            FileName=row['FileName'],
            SizeMB=row['SizeMB'],
            VideoBitrateKbps=row['VideoBitrateKbps'],
            AudioBitrateKbps=row['AudioBitrateKbps'],
            Resolution=row['Resolution'],
            Codec=row['Codec'],
            DurationMinutes=row['DurationMinutes'],
            FrameRate=row['FrameRate'],
            LastScannedDate=row['LastScannedDate'],
            CompressionPotential=row['CompressionPotential'],
            AssignedProfile=row['AssignedProfile']
        )
    
    
    def DeleteMediaFileByPath(self, FilePath: str) -> bool:
        """Delete a media file by path."""
        affectedRows = self.DatabaseService.ExecuteNonQuery("DELETE FROM MediaFiles WHERE FilePath = ?", (FilePath,))
        return affectedRows > 0
    
    # System Settings Management Methods
    def GetSystemSetting(self, SettingKey: str) -> Optional[str]:
        """Get a system setting value by key."""
        query = "SELECT SettingValue FROM SystemSettings WHERE SettingKey = ?"
        rows = self.DatabaseService.ExecuteQuery(query, (SettingKey,))
        
        if not rows:
            return None
        
        return rows[0]['SettingValue']
    
    def GetAllSystemSettings(self) -> List[Dict[str, Any]]:
        """Get all system settings."""
        query = "SELECT Id, SettingKey, SettingValue, Description, DataType, LastModified FROM SystemSettings ORDER BY SettingKey"
        rows = self.DatabaseService.ExecuteQuery(query)
        
        settings = []
        for row in rows:
            settings.append({
                'Id': row['Id'],
                'SettingKey': row['SettingKey'],
                'SettingValue': row['SettingValue'],
                'Description': row['Description'],
                'DataType': row['DataType'],
                'LastModified': row['LastModified']
            })
        
        return settings
    
    def GetScanDirectories(self) -> List[Dict[str, str]]:
        """Get all scan directory settings (ScanDir1, ScanDir2, etc.)."""
        query = "SELECT SettingKey, SettingValue, Description FROM SystemSettings WHERE SettingKey LIKE 'ScanDir%' ORDER BY SettingKey"
        rows = self.DatabaseService.ExecuteQuery(query)
        
        scanDirs = []
        for row in rows:
            if row['SettingValue'] and row['SettingValue'].strip():  # Only include non-empty directories
                scanDirs.append({
                    'Key': row['SettingKey'],
                    'Path': row['SettingValue'],
                    'Description': row['Description']
                })
        
        return scanDirs
