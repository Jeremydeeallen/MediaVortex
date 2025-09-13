from typing import List, Optional, Dict, Any
from Models.TranscodeProfileModel import TranscodeProfileModel
from Models.ProfileThresholdModel import ProfileThresholdModel
from Models.RootFolderModel import RootFolderModel
from Models.MediaFileModel import MediaFileModel
from Services.DatabaseService import DatabaseService
from Services.DebugService import DebugService


class DatabaseManager:
    """Handles business logic for data access operations."""
    
    def __init__(self, database_service: DatabaseService = None):
        self.DatabaseService = database_service or DatabaseService()
    
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
    
    def GetProfileById(self, profile_id: int) -> Optional[TranscodeProfileModel]:
        """Get a specific profile by ID."""
        query = "SELECT Id, ProfileName, Description, CreatedDate, LastModified FROM Profiles WHERE Id = ?"
        rows = self.DatabaseService.ExecuteQuery(query, (profile_id,))
        
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
    
    def SaveProfile(self, profile: TranscodeProfileModel) -> int:
        """Save a profile (insert or update) and return the profile ID."""
        try:
            DebugService.LogFunctionEntry("SaveProfile", profile.Id, profile.ProfileName, profile.Description)
            
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()
                
                if profile.Id is None:
                    # Insert new profile
                    DebugService.Log("Inserting new profile...")
                    query = """
                        INSERT INTO Profiles (ProfileName, Description, CreatedDate, LastModified)
                        VALUES (?, ?, ?, ?)
                    """
                    parameters = (profile.ProfileName, profile.Description, profile.CreatedDate, profile.LastModified)
                    DebugService.LogData("Insert parameters", parameters)
                    cursor.execute(query, parameters)
                    connection.commit()
                    profile_id = cursor.lastrowid
                    DebugService.Log("Profile inserted with ID: {}", profile_id)
                    return profile_id
                else:
                    # Update existing profile
                    DebugService.Log("Updating existing profile with ID: {}", profile.Id)
                    query = """
                        UPDATE Profiles 
                        SET ProfileName = ?, Description = ?, LastModified = ?
                        WHERE Id = ?
                    """
                    parameters = (profile.ProfileName, profile.Description, profile.LastModified, profile.Id)
                    DebugService.LogData("Update parameters", parameters)
                    cursor.execute(query, parameters)
                    connection.commit()
                    affected_rows = cursor.rowcount
                    DebugService.Log("Profile update affected {} rows", affected_rows)
                    return profile.Id
            finally:
                connection.close()
        except Exception as e:
            DebugService.LogException("Exception in SaveProfile", e)
            raise
    
    def DeleteProfile(self, profile_id: int) -> bool:
        """Delete a profile and its associated thresholds."""
        try:
            # Delete associated thresholds first
            self.DatabaseService.ExecuteNonQuery("DELETE FROM ProfileThresholds WHERE ProfileId = ?", (profile_id,))
            
            # Delete the profile
            affected_rows = self.DatabaseService.ExecuteNonQuery("DELETE FROM Profiles WHERE Id = ?", (profile_id,))
            return affected_rows > 0
        except Exception:
            return False
    
    # Profile Threshold Management Methods
    def GetThresholdsByProfileId(self, profile_id: int) -> List[ProfileThresholdModel]:
        """Get all thresholds for a specific profile."""
        query = """
            SELECT Id, ProfileId, Resolution, Under30MinMB, Under65MinMB, Over65MinMB,
                   VideoBitrateKbps, AudioBitrateKbps, FallbackVideoBitrateKbps,
                   FallbackAudioBitrateKbps, TranscodeDownTo
            FROM ProfileThresholds 
            WHERE ProfileId = ?
            ORDER BY Resolution
        """
        rows = self.DatabaseService.ExecuteQuery(query, (profile_id,))
        
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
    
    def SaveThreshold(self, threshold: ProfileThresholdModel) -> int:
        """Save a threshold (insert or update) and return the threshold ID."""
        try:
            DebugService.LogFunctionEntry("SaveThreshold", threshold.Id, threshold.ProfileId, threshold.Resolution)
            
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()
                
                if threshold.Id is None:
                    # Insert new threshold
                    DebugService.Log("Inserting new threshold...")
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
                    DebugService.LogData("Insert threshold parameters", parameters)
                    cursor.execute(query, parameters)
                    connection.commit()
                    threshold_id = cursor.lastrowid
                    DebugService.Log("Threshold inserted with ID: {}", threshold_id)
                    return threshold_id
                else:
                    # Update existing threshold
                    DebugService.Log("Updating existing threshold with ID: {}", threshold.Id)
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
                    DebugService.LogData("Update threshold parameters", parameters)
                    cursor.execute(query, parameters)
                    connection.commit()
                    affected_rows = cursor.rowcount
                    DebugService.Log("Threshold update affected {} rows", affected_rows)
                    return threshold.Id
            finally:
                connection.close()
        except Exception as e:
            DebugService.LogException("Exception in SaveThreshold", e)
            raise
    
    def DeleteThreshold(self, threshold_id: int) -> bool:
        """Delete a threshold."""
        affected_rows = self.DatabaseService.ExecuteNonQuery("DELETE FROM ProfileThresholds WHERE Id = ?", (threshold_id,))
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
    
    def GetRootFolderById(self, rootFolderId: int) -> Optional[RootFolderModel]:
        """Get a specific root folder by ID."""
        query = "SELECT Id, RootFolder, LastScannedDate, TotalSizeGB FROM RootFolders WHERE Id = ?"
        rows = self.DatabaseService.ExecuteQuery(query, (rootFolderId,))
        
        if not rows:
            return None
        
        row = rows[0]
        return RootFolderModel(
            Id=row['Id'],
            RootFolder=row['RootFolder'],
            LastScannedDate=row['LastScannedDate'],
            TotalSizeGB=row['TotalSizeGB']
        )
    
    def SaveRootFolder(self, rootFolder: RootFolderModel) -> int:
        """Save a root folder (insert or update) and return the root folder ID."""
        try:
            DebugService.LogFunctionEntry("SaveRootFolder", rootFolder.Id, rootFolder.RootFolder, rootFolder.TotalSizeGB)
            
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()
                
                if rootFolder.Id is None:
                    # Insert new root folder
                    DebugService.Log("Inserting new root folder...")
                    query = """
                        INSERT INTO RootFolders (RootFolder, LastScannedDate, TotalSizeGB)
                        VALUES (?, ?, ?)
                    """
                    parameters = (rootFolder.RootFolder, rootFolder.LastScannedDate, rootFolder.TotalSizeGB)
                    DebugService.LogData("Insert root folder parameters", parameters)
                    cursor.execute(query, parameters)
                    connection.commit()
                    rootFolderId = cursor.lastrowid
                    DebugService.Log("Root folder inserted with ID: {}", rootFolderId)
                    return rootFolderId
                else:
                    # Update existing root folder
                    DebugService.Log("Updating existing root folder with ID: {}", rootFolder.Id)
                    query = """
                        UPDATE RootFolders 
                        SET RootFolder = ?, LastScannedDate = ?, TotalSizeGB = ?
                        WHERE Id = ?
                    """
                    parameters = (rootFolder.RootFolder, rootFolder.LastScannedDate, rootFolder.TotalSizeGB, rootFolder.Id)
                    DebugService.LogData("Update root folder parameters", parameters)
                    cursor.execute(query, parameters)
                    connection.commit()
                    affectedRows = cursor.rowcount
                    DebugService.Log("Root folder update affected {} rows", affectedRows)
                    return rootFolder.Id
            finally:
                connection.close()
        except Exception as e:
            DebugService.LogException("Exception in SaveRootFolder", e)
            raise
    
    def DeleteRootFolder(self, rootFolderId: int) -> bool:
        """Delete a root folder and its associated media files."""
        try:
            # Delete associated media files first
            self.DatabaseService.ExecuteNonQuery("DELETE FROM MediaFiles WHERE Id IN (SELECT Id FROM MediaFiles WHERE FilePath LIKE (SELECT RootFolder || '%' FROM RootFolders WHERE Id = ?))", (rootFolderId,))
            
            # Delete the root folder
            affectedRows = self.DatabaseService.ExecuteNonQuery("DELETE FROM RootFolders WHERE Id = ?", (rootFolderId,))
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
    
    def GetMediaFileById(self, mediaFileId: int) -> Optional[MediaFileModel]:
        """Get a specific media file by ID."""
        query = """
            SELECT Id, SeasonId, FilePath, FileName, SizeMB, VideoBitrateKbps, AudioBitrateKbps,
                   Resolution, Codec, DurationMinutes, FrameRate, LastScannedDate,
                   CompressionPotential, AssignedProfile
            FROM MediaFiles 
            WHERE Id = ?
        """
        rows = self.DatabaseService.ExecuteQuery(query, (mediaFileId,))
        
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
    
    def SaveMediaFile(self, mediaFile: MediaFileModel) -> int:
        """Save a media file (insert or update) and return the media file ID."""
        try:
            DebugService.LogFunctionEntry("SaveMediaFile", mediaFile.Id, mediaFile.FilePath, mediaFile.FileName)
            
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()
                
                if mediaFile.Id is None:
                    # Insert new media file
                    DebugService.Log("Inserting new media file...")
                    query = """
                        INSERT INTO MediaFiles 
                        (SeasonId, FilePath, FileName, SizeMB, VideoBitrateKbps, AudioBitrateKbps,
                         Resolution, Codec, DurationMinutes, FrameRate, LastScannedDate,
                         CompressionPotential, AssignedProfile)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    parameters = (
                        mediaFile.SeasonId, mediaFile.FilePath, mediaFile.FileName, mediaFile.SizeMB,
                        mediaFile.VideoBitrateKbps, mediaFile.AudioBitrateKbps, mediaFile.Resolution,
                        mediaFile.Codec, mediaFile.DurationMinutes, mediaFile.FrameRate,
                        mediaFile.LastScannedDate, mediaFile.CompressionPotential, mediaFile.AssignedProfile
                    )
                    DebugService.LogData("Insert media file parameters", parameters)
                    cursor.execute(query, parameters)
                    connection.commit()
                    mediaFileId = cursor.lastrowid
                    DebugService.Log("Media file inserted with ID: {}", mediaFileId)
                    return mediaFileId
                else:
                    # Update existing media file
                    DebugService.Log("Updating existing media file with ID: {}", mediaFile.Id)
                    query = """
                        UPDATE MediaFiles 
                        SET SeasonId = ?, FilePath = ?, FileName = ?, SizeMB = ?, VideoBitrateKbps = ?,
                            AudioBitrateKbps = ?, Resolution = ?, Codec = ?, DurationMinutes = ?,
                            FrameRate = ?, LastScannedDate = ?, CompressionPotential = ?, AssignedProfile = ?
                        WHERE Id = ?
                    """
                    parameters = (
                        mediaFile.SeasonId, mediaFile.FilePath, mediaFile.FileName, mediaFile.SizeMB,
                        mediaFile.VideoBitrateKbps, mediaFile.AudioBitrateKbps, mediaFile.Resolution,
                        mediaFile.Codec, mediaFile.DurationMinutes, mediaFile.FrameRate,
                        mediaFile.LastScannedDate, mediaFile.CompressionPotential, mediaFile.AssignedProfile,
                        mediaFile.Id
                    )
                    DebugService.LogData("Update media file parameters", parameters)
                    cursor.execute(query, parameters)
                    connection.commit()
                    affectedRows = cursor.rowcount
                    DebugService.Log("Media file update affected {} rows", affectedRows)
                    return mediaFile.Id
            finally:
                connection.close()
        except Exception as e:
            DebugService.LogException("Exception in SaveMediaFile", e)
            raise
    
    def DeleteMediaFile(self, mediaFileId: int) -> bool:
        """Delete a media file."""
        affectedRows = self.DatabaseService.ExecuteNonQuery("DELETE FROM MediaFiles WHERE Id = ?", (mediaFileId,))
        return affectedRows > 0
    
    def GetMediaFilesByRootFolder(self, rootFolderPath: str) -> List[MediaFileModel]:
        """Get all media files for a specific root folder."""
        query = """
            SELECT Id, SeasonId, FilePath, FileName, SizeMB, VideoBitrateKbps, AudioBitrateKbps,
                   Resolution, Codec, DurationMinutes, FrameRate, LastScannedDate,
                   CompressionPotential, AssignedProfile
            FROM MediaFiles 
            WHERE FilePath LIKE ?
            ORDER BY FilePath
        """
        rows = self.DatabaseService.ExecuteQuery(query, (f"{rootFolderPath}%",))
        
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
