from typing import List, Optional, Dict, Any
from datetime import datetime
from Models.TranscodeProfileModel import TranscodeProfileModel
from Models.ProfileThresholdModel import ProfileThresholdModel
from Models.RootFolderModel import RootFolderModel
from Models.MediaFileModel import MediaFileModel
from Models.SeasonModel import SeasonModel
from Models.FileScanResultModel import FileScanResultModel
from Models.TranscodeQueueModel import TranscodeQueueModel
from Models.TranscodeAttemptModel import TranscodeAttemptModel
from Models.TranscodeFileModel import TranscodeFileModel
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
                
                if Profile.Id is None:
                    # Insert new profile
                    LoggingService.LogInfo("Inserting new profile...", "DatabaseManager", "SaveProfile")
                    query = """
                        INSERT INTO Profiles (ProfileName, Description, CreatedDate, LastModified)
                        VALUES (?, ?, ?, ?)
                    """
                    parameters = (Profile.ProfileName, Profile.Description, Profile.CreatedDate, Profile.LastModified)
                    LoggingService.LogInfo("Insert parameters: {}", "DatabaseManager", "SaveProfile", parameters)
                    cursor.execute(query, parameters)
                    connection.commit()
                    profile_id = cursor.lastrowid
                    LoggingService.LogInfo("Profile inserted with ID: {}", "DatabaseManager", "SaveProfile", profile_id)
                    return profile_id
                else:
                    # Update existing profile
                    LoggingService.LogInfo("Updating existing profile with ID: {}", "DatabaseManager", "SaveProfile", Profile.Id)
                    query = """
                        UPDATE Profiles 
                        SET ProfileName = ?, Description = ?, LastModified = ?
                        WHERE Id = ?
                    """
                    parameters = (Profile.ProfileName, Profile.Description, Profile.LastModified, Profile.Id)
                    LoggingService.LogInfo("Update parameters: {}", "DatabaseManager", "SaveProfile", parameters)
                    cursor.execute(query, parameters)
                    connection.commit()
                    affected_rows = cursor.rowcount
                    LoggingService.LogInfo("Profile update affected {} rows", "DatabaseManager", "SaveProfile", affected_rows)
                    return Profile.Id
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
                   FallbackAudioBitrateKbps, TranscodeDownTo, Quality
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
                TranscodeDownTo=row['TranscodeDownTo'],
                Quality=row['Quality']
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
                
                if Threshold.Id is None:
                    # Insert new threshold
                    LoggingService.LogInfo("Inserting new threshold...")
                    query = """
                        INSERT INTO ProfileThresholds 
                        (ProfileId, Resolution, Under30MinMB, Under65MinMB, Over65MinMB,
                         VideoBitrateKbps, AudioBitrateKbps, FallbackVideoBitrateKbps,
                         FallbackAudioBitrateKbps, TranscodeDownTo, Quality)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    parameters = (
                        Threshold.ProfileId, Threshold.Resolution, Threshold.Under30MinMB,
                        Threshold.Under65MinMB, Threshold.Over65MinMB, Threshold.VideoBitrateKbps,
                        Threshold.AudioBitrateKbps, Threshold.FallbackVideoBitrateKbps,
                        Threshold.FallbackAudioBitrateKbps, Threshold.TranscodeDownTo, Threshold.Quality
                    )
                    LoggingService.LogInfo(f"Insert threshold parameters: {parameters}", "SaveThreshold", "DatabaseManager")
                    cursor.execute(query, parameters)
                    connection.commit()
                    threshold_id = cursor.lastrowid
                    LoggingService.LogInfo(f"Threshold inserted with ID: {threshold_id}", "SaveThreshold", "DatabaseManager")
                    return threshold_id
                else:
                    # Update existing threshold
                    LoggingService.LogInfo(f"Updating existing threshold with ID: {Threshold.Id}", "SaveThreshold", "DatabaseManager")
                    query = """
                        UPDATE ProfileThresholds 
                        SET ProfileId = ?, Resolution = ?, Under30MinMB = ?, Under65MinMB = ?,
                            Over65MinMB = ?, VideoBitrateKbps = ?, AudioBitrateKbps = ?,
                            FallbackVideoBitrateKbps = ?, FallbackAudioBitrateKbps = ?,
                            TranscodeDownTo = ?, Quality = ?
                        WHERE Id = ?
                    """
                    parameters = (
                        Threshold.ProfileId, Threshold.Resolution, Threshold.Under30MinMB,
                        Threshold.Under65MinMB, Threshold.Over65MinMB, Threshold.VideoBitrateKbps,
                        Threshold.AudioBitrateKbps, Threshold.FallbackVideoBitrateKbps,
                        Threshold.FallbackAudioBitrateKbps, Threshold.TranscodeDownTo, Threshold.Quality, Threshold.Id
                    )
                    LoggingService.LogInfo(f"Update threshold parameters: {parameters}", "SaveThreshold", "DatabaseManager")
                    cursor.execute(query, parameters)
                    connection.commit()
                    affected_rows = cursor.rowcount
                    LoggingService.LogInfo(f"Threshold update affected {affected_rows} rows", "SaveThreshold", "DatabaseManager")
                    return Threshold.Id
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
    def GetAllRootFolders(self, SortColumn: str = 'RootFolder', SortOrder: str = 'ASC') -> List[RootFolderModel]:
        """Get all root folders with optional sorting."""
        # Validate sort column to prevent SQL injection
        ValidColumns = ['Id', 'RootFolder', 'LastScannedDate', 'TotalSizeGB']
        if SortColumn not in ValidColumns:
            SortColumn = 'RootFolder'
        
        # Validate sort order
        if SortOrder.upper() not in ['ASC', 'DESC']:
            SortOrder = 'ASC'
        
        query = f"SELECT Id, RootFolder, LastScannedDate, TotalSizeGB FROM RootFolders ORDER BY {SortColumn} {SortOrder.upper()}"
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
                
                if RootFolder.Id is None:
                    # Insert new root folder
                    LoggingService.LogInfo("Inserting new root folder...")
                    query = """
                        INSERT INTO RootFolders (RootFolder, LastScannedDate, TotalSizeGB)
                        VALUES (?, ?, ?)
                    """
                    parameters = (RootFolder.RootFolder, RootFolder.LastScannedDate, RootFolder.TotalSizeGB)
                    LoggingService.LogInfo("Insert root folder parameters: {}", "DatabaseManager", "SaveRootFolder", parameters)
                    cursor.execute(query, parameters)
                    connection.commit()
                    rootFolderId = cursor.lastrowid
                    LoggingService.LogInfo("Root folder inserted with ID: {}", "DatabaseManager", "SaveRootFolder", rootFolderId)
                    return rootFolderId
                else:
                    # Update existing root folder
                    LoggingService.LogInfo("Updating existing root folder with ID: {}", "DatabaseManager", "SaveRootFolder", RootFolder.Id)
                    query = """
                        UPDATE RootFolders 
                        SET RootFolder = ?, LastScannedDate = ?, TotalSizeGB = ?
                        WHERE Id = ?
                    """
                    parameters = (RootFolder.RootFolder, RootFolder.LastScannedDate, RootFolder.TotalSizeGB, RootFolder.Id)
                    LoggingService.LogInfo("Update root folder parameters: {}", "DatabaseManager", "SaveRootFolder", parameters)
                    cursor.execute(query, parameters)
                    connection.commit()
                    affectedRows = cursor.rowcount
                    LoggingService.LogInfo("Root folder update affected {} rows", "DatabaseManager", "SaveRootFolder", affectedRows)
                    return RootFolder.Id
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
                   CompressionPotential, AssignedProfile, FileModificationTime
            FROM MediaFiles
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
                AssignedProfile=row['AssignedProfile'],
                FileModificationTime=row['FileModificationTime']
            )
            mediaFiles.append(mediaFile)
        
        return mediaFiles
    
    def GetMediaFileById(self, MediaFileId: int) -> Optional[MediaFileModel]:
        """Get a specific media file by ID."""
        query = """
            SELECT Id, SeasonId, FilePath, FileName, SizeMB, VideoBitrateKbps, AudioBitrateKbps,
                   Resolution, Codec, DurationMinutes, FrameRate, LastScannedDate,
                   CompressionPotential, AssignedProfile, FileModificationTime
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
            AssignedProfile=row['AssignedProfile'],
            FileModificationTime=row['FileModificationTime']
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
                         CompressionPotential, AssignedProfile, FileModificationTime)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    parameters = (
                        MediaFile.SeasonId, MediaFile.FilePath, MediaFile.FileName, MediaFile.SizeMB,
                        MediaFile.VideoBitrateKbps, MediaFile.AudioBitrateKbps, MediaFile.Resolution,
                        MediaFile.Codec, MediaFile.DurationMinutes, MediaFile.FrameRate,
                        MediaFile.LastScannedDate, MediaFile.CompressionPotential, MediaFile.AssignedProfile,
                        MediaFile.FileModificationTime
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
                            FrameRate = ?, LastScannedDate = ?, CompressionPotential = ?, AssignedProfile = ?,
                            FileModificationTime = ?
                        WHERE Id = ?
                    """
                    parameters = (
                        MediaFile.SeasonId, MediaFile.FilePath, MediaFile.FileName, MediaFile.SizeMB,
                        MediaFile.VideoBitrateKbps, MediaFile.AudioBitrateKbps, MediaFile.Resolution,
                        MediaFile.Codec, MediaFile.DurationMinutes, MediaFile.FrameRate,
                        MediaFile.LastScannedDate, MediaFile.CompressionPotential, MediaFile.AssignedProfile,
                        MediaFile.FileModificationTime, MediaFile.Id
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
                   CompressionPotential, AssignedProfile, FileModificationTime
            FROM MediaFiles 
            WHERE FilePath LIKE ?
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
                AssignedProfile=row['AssignedProfile'],
                FileModificationTime=row['FileModificationTime']
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
                   CompressionPotential, AssignedProfile, FileModificationTime
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
            AssignedProfile=row['AssignedProfile'],
            FileModificationTime=row['FileModificationTime']
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
    
    # TranscodeQueue Management Methods
    def GetAllTranscodeQueueItems(self) -> List[TranscodeQueueModel]:
        """Get all transcoding queue items."""
        query = """
            SELECT Id, FilePath, FileName, Directory, SizeBytes, SizeMB, Priority, Status, DateAdded, DateStarted
            FROM TranscodeQueue 
            ORDER BY Priority DESC, DateAdded ASC
        """
        rows = self.DatabaseService.ExecuteQuery(query)
        
        queueItems = []
        for row in rows:
            queueItem = TranscodeQueueModel(
                Id=row['Id'],
                FilePath=row['FilePath'],
                FileName=row['FileName'],
                Directory=row['Directory'],
                SizeBytes=row['SizeBytes'],
                SizeMB=row['SizeMB'],
                Priority=row['Priority'],
                Status=row['Status'],
                DateAdded=row['DateAdded'],
                DateStarted=row['DateStarted']
            )
            queueItems.append(queueItem)
        
        return queueItems
    
    def GetTranscodeQueueItemById(self, ItemId: int) -> Optional[TranscodeQueueModel]:
        """Get a specific transcoding queue item by ID."""
        query = """
            SELECT Id, FilePath, FileName, Directory, SizeBytes, SizeMB, Priority, Status, DateAdded, DateStarted
            FROM TranscodeQueue 
            WHERE Id = ?
        """
        rows = self.DatabaseService.ExecuteQuery(query, (ItemId,))
        
        if not rows:
            return None
        
        row = rows[0]
        return TranscodeQueueModel(
            Id=row['Id'],
            FilePath=row['FilePath'],
            FileName=row['FileName'],
            Directory=row['Directory'],
            SizeBytes=row['SizeBytes'],
            SizeMB=row['SizeMB'],
            Priority=row['Priority'],
            Status=row['Status'],
            DateAdded=row['DateAdded'],
            DateStarted=row['DateStarted']
        )
    
    def SaveTranscodeQueueItem(self, QueueItem: TranscodeQueueModel) -> int:
        """Save a transcoding queue item (insert or update) and return the item ID."""
        try:
            LoggingService.LogFunctionEntry("SaveTranscodeQueueItem", "DatabaseManager", QueueItem.Id, QueueItem.FilePath, QueueItem.Status)
            
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()
                
                if QueueItem.Id is None:
                    # Insert new queue item
                    LoggingService.LogInfo("Inserting new transcoding queue item...", "DatabaseManager", "SaveTranscodeQueueItem")
                    query = """
                        INSERT INTO TranscodeQueue 
                        (FilePath, FileName, Directory, SizeBytes, SizeMB, Priority, Status, DateAdded, DateStarted)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    parameters = (
                        QueueItem.FilePath, QueueItem.FileName, QueueItem.Directory,
                        QueueItem.SizeBytes, QueueItem.SizeMB, QueueItem.Priority,
                        QueueItem.Status, QueueItem.DateAdded, QueueItem.DateStarted
                    )
                    LoggingService.LogInfo(f"Insert queue item parameters: {parameters}", "DatabaseManager", "SaveTranscodeQueueItem")
                    cursor.execute(query, parameters)
                    connection.commit()
                    itemId = cursor.lastrowid
                    LoggingService.LogInfo(f"Queue item inserted with ID: {itemId}", "DatabaseManager", "SaveTranscodeQueueItem")
                    return itemId
                else:
                    # Update existing queue item
                    LoggingService.LogInfo(f"Updating existing queue item with ID: {QueueItem.Id}", "DatabaseManager", "SaveTranscodeQueueItem")
                    query = """
                        UPDATE TranscodeQueue 
                        SET FilePath = ?, FileName = ?, Directory = ?, SizeBytes = ?, SizeMB = ?,
                            Priority = ?, Status = ?, DateAdded = ?, DateStarted = ?
                        WHERE Id = ?
                    """
                    parameters = (
                        QueueItem.FilePath, QueueItem.FileName, QueueItem.Directory,
                        QueueItem.SizeBytes, QueueItem.SizeMB, QueueItem.Priority,
                        QueueItem.Status, QueueItem.DateAdded, QueueItem.DateStarted, QueueItem.Id
                    )
                    LoggingService.LogInfo(f"Update queue item parameters: {parameters}", "DatabaseManager", "SaveTranscodeQueueItem")
                    cursor.execute(query, parameters)
                    connection.commit()
                    affectedRows = cursor.rowcount
                    LoggingService.LogInfo(f"Queue item update affected {affectedRows} rows", "DatabaseManager", "SaveTranscodeQueueItem")
                    return QueueItem.Id
            finally:
                connection.close()
        except Exception as e:
            LoggingService.LogException("Exception in SaveTranscodeQueueItem", e, "DatabaseManager", "SaveTranscodeQueueItem")
            raise
    
    def DeleteTranscodeQueueItem(self, ItemId: int) -> bool:
        """Delete a transcoding queue item."""
        affectedRows = self.DatabaseService.ExecuteNonQuery("DELETE FROM TranscodeQueue WHERE Id = ?", (ItemId,))
        return affectedRows > 0
    
    def GetTranscodeQueueItemsByStatus(self, Status: str) -> List[TranscodeQueueModel]:
        """Get all transcoding queue items with a specific status."""
        query = """
            SELECT Id, FilePath, FileName, Directory, SizeBytes, SizeMB, Priority, Status, DateAdded, DateStarted
            FROM TranscodeQueue 
            WHERE Status = ?
            ORDER BY Priority DESC, DateAdded ASC
        """
        rows = self.DatabaseService.ExecuteQuery(query, (Status,))
        
        queueItems = []
        for row in rows:
            queueItem = TranscodeQueueModel(
                Id=row['Id'],
                FilePath=row['FilePath'],
                FileName=row['FileName'],
                Directory=row['Directory'],
                SizeBytes=row['SizeBytes'],
                SizeMB=row['SizeMB'],
                Priority=row['Priority'],
                Status=row['Status'],
                DateAdded=row['DateAdded'],
                DateStarted=row['DateStarted']
            )
            queueItems.append(queueItem)
        
        return queueItems
    
    def ClearAllTranscodeQueueItems(self) -> int:
        """Clear all items from the transcoding queue and return the count of deleted items."""
        try:
            LoggingService.LogFunctionEntry("ClearAllTranscodeQueueItems", "DatabaseManager")
            
            # First get the count of items to be deleted for logging
            countQuery = "SELECT COUNT(*) as Count FROM TranscodeQueue"
            countResult = self.DatabaseService.ExecuteQuery(countQuery)
            itemsToDelete = countResult[0]['Count'] if countResult else 0
            
            if itemsToDelete > 0:
                # Delete all items from the queue
                deleteQuery = "DELETE FROM TranscodeQueue"
                affectedRows = self.DatabaseService.ExecuteNonQuery(deleteQuery)
                
                LoggingService.LogInfo(f"Cleared {affectedRows} items from TranscodeQueue", "DatabaseManager", "ClearAllTranscodeQueueItems")
                return affectedRows
            else:
                LoggingService.LogInfo("No items found in TranscodeQueue to clear", "DatabaseManager", "ClearAllTranscodeQueueItems")
                return 0
                
        except Exception as e:
            LoggingService.LogException("Exception clearing all transcoding queue items", e, "DatabaseManager", "ClearAllTranscodeQueueItems")
            return 0
    
    # TranscodeAttempts Management Methods
    def GetAllTranscodeAttempts(self) -> List[TranscodeAttemptModel]:
        """Get all transcoding attempts."""
        query = """
            SELECT Id, FilePath, AttemptDate, Quality, OldSizeBytes, NewSizeBytes, Success,
                   SizeReductionBytes, SizeReductionPercent, ErrorMessage, TranscodeDurationSeconds,
                   HandbrakeSettings, AudioBitrateKbps, VideoBitrateKbps, ProfileName, VMAF, VMAF
            FROM TranscodeAttempts 
            ORDER BY AttemptDate DESC
        """
        rows = self.DatabaseService.ExecuteQuery(query)
        
        attempts = []
        for row in rows:
            attempt = TranscodeAttemptModel(
                Id=row['Id'],
                FilePath=row['FilePath'],
                AttemptDate=row['AttemptDate'],
                Quality=row['Quality'],
                OldSizeBytes=row['OldSizeBytes'],
                NewSizeBytes=row['NewSizeBytes'],
                Success=row['Success'],
                SizeReductionBytes=row['SizeReductionBytes'],
                SizeReductionPercent=row['SizeReductionPercent'],
                ErrorMessage=row['ErrorMessage'],
                TranscodeDurationSeconds=row['TranscodeDurationSeconds'],
                HandbrakeSettings=row['HandbrakeSettings'],
                AudioBitrateKbps=row['AudioBitrateKbps'],
                VideoBitrateKbps=row['VideoBitrateKbps'],
                ProfileName=row['ProfileName'],
                VMAF=row['VMAF']
            )
            attempts.append(attempt)
        
        return attempts
    
    def GetTranscodeAttemptsByFilePath(self, FilePath: str) -> List[TranscodeAttemptModel]:
        """Get all transcoding attempts for a specific file."""
        query = """
            SELECT Id, FilePath, AttemptDate, Quality, OldSizeBytes, NewSizeBytes, Success,
                   SizeReductionBytes, SizeReductionPercent, ErrorMessage, TranscodeDurationSeconds,
                   HandbrakeSettings, AudioBitrateKbps, VideoBitrateKbps, ProfileName, VMAF
            FROM TranscodeAttempts 
            WHERE FilePath = ?
            ORDER BY AttemptDate DESC
        """
        rows = self.DatabaseService.ExecuteQuery(query, (FilePath,))
        
        attempts = []
        for row in rows:
            attempt = TranscodeAttemptModel(
                Id=row['Id'],
                FilePath=row['FilePath'],
                AttemptDate=row['AttemptDate'],
                Quality=row['Quality'],
                OldSizeBytes=row['OldSizeBytes'],
                NewSizeBytes=row['NewSizeBytes'],
                Success=row['Success'],
                SizeReductionBytes=row['SizeReductionBytes'],
                SizeReductionPercent=row['SizeReductionPercent'],
                ErrorMessage=row['ErrorMessage'],
                TranscodeDurationSeconds=row['TranscodeDurationSeconds'],
                HandbrakeSettings=row['HandbrakeSettings'],
                AudioBitrateKbps=row['AudioBitrateKbps'],
                VideoBitrateKbps=row['VideoBitrateKbps'],
                ProfileName=row['ProfileName'],
                VMAF=row['VMAF']
            )
            attempts.append(attempt)
        
        return attempts
    
    def SaveTranscodeAttempt(self, Attempt: TranscodeAttemptModel) -> int:
        """Save a transcoding attempt (insert or update) and return the attempt ID."""
        try:
            LoggingService.LogFunctionEntry("SaveTranscodeAttempt", "DatabaseManager", Attempt.Id, Attempt.FilePath, Attempt.Success)
            
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()
                
                if Attempt.Id is None:
                    # Insert new attempt
                    LoggingService.LogInfo("Inserting new transcoding attempt...", "DatabaseManager", "SaveTranscodeAttempt")
                    query = """
                        INSERT INTO TranscodeAttempts 
                        (FilePath, AttemptDate, Quality, OldSizeBytes, NewSizeBytes, Success,
                         SizeReductionBytes, SizeReductionPercent, ErrorMessage, TranscodeDurationSeconds,
                         HandbrakeSettings, AudioBitrateKbps, VideoBitrateKbps, ProfileName, VMAF)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    parameters = (
                        Attempt.FilePath, Attempt.AttemptDate, Attempt.Quality,
                        Attempt.OldSizeBytes, Attempt.NewSizeBytes, Attempt.Success,
                        Attempt.SizeReductionBytes, Attempt.SizeReductionPercent, Attempt.ErrorMessage,
                        Attempt.TranscodeDurationSeconds, Attempt.HandbrakeSettings,
                        Attempt.AudioBitrateKbps, Attempt.VideoBitrateKbps, Attempt.ProfileName, Attempt.VMAF
                    )
                    LoggingService.LogInfo(f"Insert attempt parameters: {parameters}", "DatabaseManager", "SaveTranscodeAttempt")
                    cursor.execute(query, parameters)
                    connection.commit()
                    attemptId = cursor.lastrowid
                    LoggingService.LogInfo(f"Attempt inserted with ID: {attemptId}", "DatabaseManager", "SaveTranscodeAttempt")
                    return attemptId
                else:
                    # Update existing attempt
                    LoggingService.LogInfo(f"Updating existing attempt with ID: {Attempt.Id}", "DatabaseManager", "SaveTranscodeAttempt")
                    query = """
                        UPDATE TranscodeAttempts 
                        SET FilePath = ?, AttemptDate = ?, Quality = ?, OldSizeBytes = ?, NewSizeBytes = ?,
                            Success = ?, SizeReductionBytes = ?, SizeReductionPercent = ?, ErrorMessage = ?,
                            TranscodeDurationSeconds = ?, HandbrakeSettings = ?, AudioBitrateKbps = ?,
                            VideoBitrateKbps = ?, ProfileName = ?, VMAF = ?
                        WHERE Id = ?
                    """
                    parameters = (
                        Attempt.FilePath, Attempt.AttemptDate, Attempt.Quality,
                        Attempt.OldSizeBytes, Attempt.NewSizeBytes, Attempt.Success,
                        Attempt.SizeReductionBytes, Attempt.SizeReductionPercent, Attempt.ErrorMessage,
                        Attempt.TranscodeDurationSeconds, Attempt.HandbrakeSettings,
                        Attempt.AudioBitrateKbps, Attempt.VideoBitrateKbps, Attempt.ProfileName, Attempt.VMAF, Attempt.Id
                    )
                    LoggingService.LogInfo(f"Update attempt parameters: {parameters}", "DatabaseManager", "SaveTranscodeAttempt")
                    cursor.execute(query, parameters)
                    connection.commit()
                    affectedRows = cursor.rowcount
                    LoggingService.LogInfo(f"Attempt update affected {affectedRows} rows", "DatabaseManager", "SaveTranscodeAttempt")
                    return Attempt.Id
            finally:
                connection.close()
        except Exception as e:
            LoggingService.LogException("Exception in SaveTranscodeAttempt", e, "DatabaseManager", "SaveTranscodeAttempt")
            raise
    
    # TranscodeFiles Management Methods
    def GetAllTranscodeFiles(self) -> List[TranscodeFileModel]:
        """Get all transcoding file records."""
        query = """
            SELECT Id, FilePath, AllQualitiesFailed, SuccessfullyTranscoded, FirstAttemptDate,
                   LastAttemptDate, SuccessDate, FinalQuality, FinalSizeBytes, TotalAttempts,
                   OriginalFilePath, FinalFilePath
            FROM TranscodeFiles 
            ORDER BY FirstAttemptDate DESC
        """
        rows = self.DatabaseService.ExecuteQuery(query)
        
        transcodeFiles = []
        for row in rows:
            transcodeFile = TranscodeFileModel(
                Id=row['Id'],
                FilePath=row['FilePath'],
                AllQualitiesFailed=row['AllQualitiesFailed'],
                SuccessfullyTranscoded=row['SuccessfullyTranscoded'],
                FirstAttemptDate=row['FirstAttemptDate'],
                LastAttemptDate=row['LastAttemptDate'],
                SuccessDate=row['SuccessDate'],
                FinalQuality=row['FinalQuality'],
                FinalSizeBytes=row['FinalSizeBytes'],
                TotalAttempts=row['TotalAttempts'],
                OriginalFilePath=row['OriginalFilePath'],
                FinalFilePath=row['FinalFilePath']
            )
            transcodeFiles.append(transcodeFile)
        
        return transcodeFiles
    
    def GetTranscodeFileByFilePath(self, FilePath: str) -> Optional[TranscodeFileModel]:
        """Get transcoding file record by file path."""
        query = """
            SELECT Id, FilePath, AllQualitiesFailed, SuccessfullyTranscoded, FirstAttemptDate,
                   LastAttemptDate, SuccessDate, FinalQuality, FinalSizeBytes, TotalAttempts,
                   OriginalFilePath, FinalFilePath
            FROM TranscodeFiles 
            WHERE FilePath = ?
        """
        rows = self.DatabaseService.ExecuteQuery(query, (FilePath,))
        
        if not rows:
            return None
        
        row = rows[0]
        return TranscodeFileModel(
            Id=row['Id'],
            FilePath=row['FilePath'],
            AllQualitiesFailed=row['AllQualitiesFailed'],
            SuccessfullyTranscoded=row['SuccessfullyTranscoded'],
            FirstAttemptDate=row['FirstAttemptDate'],
            LastAttemptDate=row['LastAttemptDate'],
            SuccessDate=row['SuccessDate'],
            FinalQuality=row['FinalQuality'],
            FinalSizeBytes=row['FinalSizeBytes'],
            TotalAttempts=row['TotalAttempts'],
            OriginalFilePath=row['OriginalFilePath'],
            FinalFilePath=row['FinalFilePath']
        )
    
    def SaveTranscodeFile(self, TranscodeFile: TranscodeFileModel) -> int:
        """Save a transcoding file record (insert or update) and return the file ID."""
        try:
            LoggingService.LogFunctionEntry("SaveTranscodeFile", "DatabaseManager", TranscodeFile.Id, TranscodeFile.FilePath, TranscodeFile.SuccessfullyTranscoded)
            
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()
                
                if TranscodeFile.Id is None:
                    # Insert new transcode file
                    LoggingService.LogInfo("Inserting new transcoding file record...", "DatabaseManager", "SaveTranscodeFile")
                    query = """
                        INSERT INTO TranscodeFiles 
                        (FilePath, AllQualitiesFailed, SuccessfullyTranscoded, FirstAttemptDate,
                         LastAttemptDate, SuccessDate, FinalQuality, FinalSizeBytes, TotalAttempts,
                         OriginalFilePath, FinalFilePath)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    parameters = (
                        TranscodeFile.FilePath, TranscodeFile.AllQualitiesFailed, TranscodeFile.SuccessfullyTranscoded,
                        TranscodeFile.FirstAttemptDate, TranscodeFile.LastAttemptDate, TranscodeFile.SuccessDate,
                        TranscodeFile.FinalQuality, TranscodeFile.FinalSizeBytes, TranscodeFile.TotalAttempts,
                        TranscodeFile.OriginalFilePath, TranscodeFile.FinalFilePath
                    )
                    LoggingService.LogInfo(f"Insert transcode file parameters: {parameters}", "DatabaseManager", "SaveTranscodeFile")
                    cursor.execute(query, parameters)
                    connection.commit()
                    fileId = cursor.lastrowid
                    LoggingService.LogInfo(f"Transcode file inserted with ID: {fileId}", "DatabaseManager", "SaveTranscodeFile")
                    return fileId
                else:
                    # Update existing transcode file
                    LoggingService.LogInfo(f"Updating existing transcode file with ID: {TranscodeFile.Id}", "DatabaseManager", "SaveTranscodeFile")
                    query = """
                        UPDATE TranscodeFiles 
                        SET FilePath = ?, AllQualitiesFailed = ?, SuccessfullyTranscoded = ?, FirstAttemptDate = ?,
                            LastAttemptDate = ?, SuccessDate = ?, FinalQuality = ?, FinalSizeBytes = ?,
                            TotalAttempts = ?, OriginalFilePath = ?, FinalFilePath = ?
                        WHERE Id = ?
                    """
                    parameters = (
                        TranscodeFile.FilePath, TranscodeFile.AllQualitiesFailed, TranscodeFile.SuccessfullyTranscoded,
                        TranscodeFile.FirstAttemptDate, TranscodeFile.LastAttemptDate, TranscodeFile.SuccessDate,
                        TranscodeFile.FinalQuality, TranscodeFile.FinalSizeBytes, TranscodeFile.TotalAttempts,
                        TranscodeFile.OriginalFilePath, TranscodeFile.FinalFilePath, TranscodeFile.Id
                    )
                    LoggingService.LogInfo(f"Update transcode file parameters: {parameters}", "DatabaseManager", "SaveTranscodeFile")
                    cursor.execute(query, parameters)
                    connection.commit()
                    affectedRows = cursor.rowcount
                    LoggingService.LogInfo(f"Transcode file update affected {affectedRows} rows", "DatabaseManager", "SaveTranscodeFile")
                    return TranscodeFile.Id
            finally:
                connection.close()
        except Exception as e:
            LoggingService.LogException("Exception in SaveTranscodeFile", e, "DatabaseManager", "SaveTranscodeFile")
            raise
    
    def UpdateTranscodeFileStatus(self, FilePath: str, SuccessfullyTranscoded: bool = None, 
                                 AllQualitiesFailed: bool = None, FinalQuality: int = None,
                                 FinalSizeBytes: int = None, FinalFilePath: str = None) -> bool:
        """Update transcoding file status fields."""
        try:
            LoggingService.LogFunctionEntry("UpdateTranscodeFileStatus", "DatabaseManager", FilePath, SuccessfullyTranscoded, AllQualitiesFailed)
            
            # Build dynamic update query
            updateFields = []
            parameters = []
            
            if SuccessfullyTranscoded is not None:
                updateFields.append("SuccessfullyTranscoded = ?")
                parameters.append(SuccessfullyTranscoded)
            
            if AllQualitiesFailed is not None:
                updateFields.append("AllQualitiesFailed = ?")
                parameters.append(AllQualitiesFailed)
            
            if FinalQuality is not None:
                updateFields.append("FinalQuality = ?")
                parameters.append(FinalQuality)
            
            if FinalSizeBytes is not None:
                updateFields.append("FinalSizeBytes = ?")
                parameters.append(FinalSizeBytes)
            
            if FinalFilePath is not None:
                updateFields.append("FinalFilePath = ?")
                parameters.append(FinalFilePath)
            
            if not updateFields:
                LoggingService.LogWarning("No fields to update", "DatabaseManager", "UpdateTranscodeFileStatus")
                return False
            
            # Add LastAttemptDate update
            updateFields.append("LastAttemptDate = ?")
            parameters.append(datetime.now())
            
            # Add FilePath to parameters for WHERE clause
            parameters.append(FilePath)
            
            query = f"UPDATE TranscodeFiles SET {', '.join(updateFields)} WHERE FilePath = ?"
            
            affectedRows = self.DatabaseService.ExecuteNonQuery(query, parameters)
            LoggingService.LogInfo(f"Updated transcode file status for {FilePath}, affected {affectedRows} rows", "DatabaseManager", "UpdateTranscodeFileStatus")
            return affectedRows > 0
            
        except Exception as e:
            LoggingService.LogException("Exception in UpdateTranscodeFileStatus", e, "DatabaseManager", "UpdateTranscodeFileStatus")
            return False
    
    # Queue Statistics Methods
    def GetQueueStatistics(self) -> Dict[str, Any]:
        """Get current queue statistics."""
        try:
            LoggingService.LogFunctionEntry("GetQueueStatistics", "DatabaseManager")
            
            # Get total counts by status
            query = """
                SELECT Status, COUNT(*) as Count
                FROM TranscodeQueue 
                GROUP BY Status
            """
            rows = self.DatabaseService.ExecuteQuery(query)
            
            # Initialize counts
            totalJobs = 0
            pendingJobs = 0
            runningJobs = 0
            completedJobs = 0
            failedJobs = 0
            cancelledJobs = 0
            
            for row in rows:
                status = row['Status']
                count = row['Count']
                totalJobs += count
                
                if status == "Pending":
                    pendingJobs = count
                elif status == "Running":
                    runningJobs = count
                elif status == "Completed":
                    completedJobs = count
                elif status == "Failed":
                    failedJobs = count
                elif status == "Cancelled":
                    cancelledJobs = count
            
            # Get active job IDs
            activeJobsQuery = "SELECT Id FROM TranscodeQueue WHERE Status = 'Running' ORDER BY Priority DESC, DateAdded ASC"
            activeJobRows = self.DatabaseService.ExecuteQuery(activeJobsQuery)
            activeJobs = [row['Id'] for row in activeJobRows]
            
            # Get next job ID (highest priority pending job)
            nextJobQuery = """
                SELECT Id FROM TranscodeQueue 
                WHERE Status = 'Pending' 
                ORDER BY Priority DESC, DateAdded ASC 
                LIMIT 1
            """
            nextJobRows = self.DatabaseService.ExecuteQuery(nextJobQuery)
            nextJobId = nextJobRows[0]['Id'] if nextJobRows else None
            
            statistics = {
                'TotalJobs': totalJobs,
                'PendingJobs': pendingJobs,
                'RunningJobs': runningJobs,
                'CompletedJobs': completedJobs,
                'FailedJobs': failedJobs,
                'CancelledJobs': cancelledJobs,
                'QueueSize': pendingJobs + runningJobs,
                'ActiveJobs': activeJobs,
                'NextJobId': nextJobId
            }
            
            # Calculate success rate
            if totalJobs > 0:
                statistics['SuccessRate'] = (completedJobs / totalJobs) * 100.0
                statistics['FailureRate'] = (failedJobs / totalJobs) * 100.0
            else:
                statistics['SuccessRate'] = 0.0
                statistics['FailureRate'] = 0.0
            
            LoggingService.LogInfo(f"Queue statistics: {totalJobs} total, {pendingJobs} pending, {runningJobs} running", "DatabaseManager", "GetQueueStatistics")
            return statistics
            
        except Exception as e:
            LoggingService.LogException("Exception in GetQueueStatistics", e, "DatabaseManager", "GetQueueStatistics")
            return {}
    
    def GetJobCounts(self) -> Dict[str, int]:
        """Get job counts by status."""
        try:
            LoggingService.LogFunctionEntry("GetJobCounts", "DatabaseManager")
            
            query = """
                SELECT Status, COUNT(*) as Count
                FROM TranscodeQueue 
                GROUP BY Status
            """
            rows = self.DatabaseService.ExecuteQuery(query)
            
            counts = {}
            for row in rows:
                counts[row['Status']] = row['Count']
            
            LoggingService.LogInfo(f"Job counts: {counts}", "DatabaseManager", "GetJobCounts")
            return counts
            
        except Exception as e:
            LoggingService.LogException("Exception in GetJobCounts", e, "DatabaseManager", "GetJobCounts")
            return {}
    
    def UpdateMediaFilesProfileByRootFolder(self, RootFolderPath: str, ProfileId: int) -> int:
        """Update AssignedProfile for all MediaFiles in a specific root folder."""
        try:
            LoggingService.LogFunctionEntry("UpdateMediaFilesProfileByRootFolder", "DatabaseManager", RootFolderPath, ProfileId)
            
            # Get profile name for logging
            profile = self.GetProfileById(ProfileId)
            profileName = profile.ProfileName if profile else f"ProfileId_{ProfileId}"
            
            # Update all media files where FilePath starts with RootFolderPath
            query = """
                UPDATE MediaFiles 
                SET AssignedProfile = ?
                WHERE FilePath LIKE ? || '%'
            """
            
            connection = self.DatabaseService.GetConnection()
            cursor = connection.cursor()
            cursor.execute(query, (profileName, RootFolderPath))
            connection.commit()
            
            filesUpdated = cursor.rowcount
            LoggingService.LogInfo(f"Updated {filesUpdated} media files in root folder '{RootFolderPath}' to use profile '{profileName}'", "DatabaseManager", "UpdateMediaFilesProfileByRootFolder")
            
            return filesUpdated
            
        except Exception as e:
            LoggingService.LogException("Exception updating media files profile by root folder", e, "DatabaseManager", "UpdateMediaFilesProfileByRootFolder")
            return 0
