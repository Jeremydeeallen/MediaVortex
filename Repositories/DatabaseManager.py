from typing import List, Optional, Dict, Any
from datetime import datetime
import os
from Models.TranscodeProfileModel import TranscodeProfileModel
from Models.ProfileThresholdModel import ProfileThresholdModel
from Models.RootFolderModel import RootFolderModel
from Models.MediaFileModel import MediaFileModel
from Models.SeasonModel import SeasonModel
from Models.FileScanResultModel import FileScanResultModel
from Models.TranscodeQueueModel import TranscodeQueueModel
from Models.TranscodeAttemptModel import TranscodeAttemptModel
from Models.TranscodeFileModel import TranscodeFileModel
# Quality testing models removed - using simple QualityTest methods instead
from Services.DatabaseService import DatabaseService
from Services.LoggingService import LoggingService


class DatabaseManager:
    """Handles business logic for data access operations."""
    
    def __init__(self, DatabaseServiceInstance: DatabaseService = None):
        self.DatabaseService = DatabaseServiceInstance or DatabaseService()
    
    # Profile Management Methods
    def GetAllProfiles(self) -> List[TranscodeProfileModel]:
        """Get all transcoding profiles."""
        query = """SELECT Id, ProfileName, Description, CreatedDate, LastModified, 
                          Codec, Preset, FilmGrain, YadifMode, YadifParity, YadifDeint 
                   FROM Profiles ORDER BY ProfileName"""
        rows = self.DatabaseService.ExecuteQuery(query)
        
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
                YadifDeint=row['YadifDeint'] if row['YadifDeint'] is not None else 1
            )
            profiles.append(profile)
        
        return profiles
    
    def GetProfileById(self, ProfileId: int) -> Optional[TranscodeProfileModel]:
        """Get a specific profile by ID."""
        query = """SELECT Id, ProfileName, Description, CreatedDate, LastModified, 
                          Codec, Preset, FilmGrain, YadifMode, YadifParity, YadifDeint 
                   FROM Profiles WHERE Id = ?"""
        rows = self.DatabaseService.ExecuteQuery(query, (ProfileId,))
        
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
            YadifDeint=row['YadifDeint'] if row['YadifDeint'] is not None else 1
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
                        INSERT INTO Profiles (ProfileName, Description, CreatedDate, LastModified, 
                                             Codec, Preset, FilmGrain, YadifMode, YadifParity, YadifDeint)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    parameters = (Profile.ProfileName, Profile.Description, Profile.CreatedDate, Profile.LastModified,
                                 Profile.Codec, Profile.Preset, Profile.FilmGrain, Profile.YadifMode, 
                                 Profile.YadifParity, Profile.YadifDeint)
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
                        SET ProfileName = ?, Description = ?, LastModified = ?, 
                            Codec = ?, Preset = ?, FilmGrain = ?, YadifMode = ?, YadifParity = ?, YadifDeint = ?
                        WHERE Id = ?
                    """
                    parameters = (Profile.ProfileName, Profile.Description, Profile.LastModified,
                                 Profile.Codec, Profile.Preset, Profile.FilmGrain, Profile.YadifMode, 
                                 Profile.YadifParity, Profile.YadifDeint, Profile.Id)
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
                   FallbackAudioBitrateKbps, TranscodeDownTo, Quality, KeepSource, ContainerType
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
                Quality=row['Quality'],
                KeepSource=bool(row['KeepSource'] if 'KeepSource' in row.keys() else 0),
                ContainerType=row['ContainerType'] if 'ContainerType' in row.keys() else 'mp4'
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
        rows = self.DatabaseService.ExecuteQuery(query)
        
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
                KeepSource=bool(row['KeepSource'] if 'KeepSource' in row.keys() else 0),
                ContainerType=row['ContainerType'] if 'ContainerType' in row.keys() else 'mp4'
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
                         FallbackAudioBitrateKbps, TranscodeDownTo, Quality, KeepSource, ContainerType)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    parameters = (
                        Threshold.ProfileId, Threshold.Resolution, Threshold.Under30MinMB,
                        Threshold.Under65MinMB, Threshold.Over65MinMB, Threshold.VideoBitrateKbps,
                        Threshold.AudioBitrateKbps, Threshold.FallbackVideoBitrateKbps,
                        Threshold.FallbackAudioBitrateKbps, 
                        Threshold.TranscodeDownTo if Threshold.TranscodeDownTo is not None else '', 
                        Threshold.Quality, Threshold.KeepSource, 'mp4'
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
                            TranscodeDownTo = ?, Quality = ?, KeepSource = ?
                        WHERE Id = ?
                    """
                    parameters = (
                        Threshold.ProfileId, Threshold.Resolution, Threshold.Under30MinMB,
                        Threshold.Under65MinMB, Threshold.Over65MinMB, Threshold.VideoBitrateKbps,
                        Threshold.AudioBitrateKbps, Threshold.FallbackVideoBitrateKbps,
                        Threshold.FallbackAudioBitrateKbps, 
                        Threshold.TranscodeDownTo if Threshold.TranscodeDownTo is not None else '', 
                        Threshold.Quality, Threshold.KeepSource, Threshold.Id
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
                         CompressionPotential, AssignedProfile, FileModificationTime,
                         TotalFrames, CodecProfile, ColorRange, FieldOrder, HasBFrames, RefFrames,
                         PixelFormat, Level, AudioChannels, AudioSampleRate, AudioSampleFormat,
                         AudioChannelLayout, ContainerFormat, OverallBitrate, TranscodedByMediaVortex)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    parameters = (
                        MediaFile.SeasonId, MediaFile.FilePath, MediaFile.FileName, MediaFile.SizeMB,
                        MediaFile.VideoBitrateKbps, MediaFile.AudioBitrateKbps, MediaFile.Resolution,
                        MediaFile.Codec, MediaFile.DurationMinutes, MediaFile.FrameRate,
                        MediaFile.LastScannedDate, MediaFile.CompressionPotential, MediaFile.AssignedProfile,
                        MediaFile.FileModificationTime, MediaFile.TotalFrames, MediaFile.CodecProfile,
                        MediaFile.ColorRange, MediaFile.FieldOrder, MediaFile.HasBFrames, MediaFile.RefFrames,
                        MediaFile.PixelFormat, MediaFile.Level, MediaFile.AudioChannels, MediaFile.AudioSampleRate,
                        MediaFile.AudioSampleFormat, MediaFile.AudioChannelLayout, MediaFile.ContainerFormat,
                        MediaFile.OverallBitrate, MediaFile.TranscodedByMediaVortex
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
                            FileModificationTime = ?, TotalFrames = ?, CodecProfile = ?, ColorRange = ?,
                            FieldOrder = ?, HasBFrames = ?, RefFrames = ?, PixelFormat = ?, Level = ?,
                            AudioChannels = ?, AudioSampleRate = ?, AudioSampleFormat = ?,
                            AudioChannelLayout = ?, ContainerFormat = ?, OverallBitrate = ?, TranscodedByMediaVortex = ?
                        WHERE Id = ?
                    """
                    parameters = (
                        MediaFile.SeasonId, MediaFile.FilePath, MediaFile.FileName, MediaFile.SizeMB,
                        MediaFile.VideoBitrateKbps, MediaFile.AudioBitrateKbps, MediaFile.Resolution,
                        MediaFile.Codec, MediaFile.DurationMinutes, MediaFile.FrameRate,
                        MediaFile.LastScannedDate, MediaFile.CompressionPotential, MediaFile.AssignedProfile,
                        MediaFile.FileModificationTime, MediaFile.TotalFrames, MediaFile.CodecProfile,
                        MediaFile.ColorRange, MediaFile.FieldOrder, MediaFile.HasBFrames, MediaFile.RefFrames,
                        MediaFile.PixelFormat, MediaFile.Level, MediaFile.AudioChannels, MediaFile.AudioSampleRate,
                        MediaFile.AudioSampleFormat, MediaFile.AudioChannelLayout, MediaFile.ContainerFormat,
                        MediaFile.OverallBitrate, MediaFile.TranscodedByMediaVortex, MediaFile.Id
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
                   CompressionPotential, AssignedProfile, IsInterlaced,
                   ResolutionCategory, FileModificationTime
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
    
    def AddOrUpdateSystemSetting(self, SettingKey: str, SettingValue: str, Description: str, DataType: str = 'string') -> bool:
        """Add or update a system setting."""
        try:
            # Check if setting already exists
            existingValue = self.GetSystemSetting(SettingKey)
            
            if existingValue is not None:
                # Update existing setting
                query = """
                    UPDATE SystemSettings 
                    SET SettingValue = ?, Description = ?, DataType = ?, LastModified = datetime('now', 'localtime')
                    WHERE SettingKey = ?
                """
                self.DatabaseService.ExecuteNonQuery(query, (SettingValue, Description, DataType, SettingKey))
            else:
                # Insert new setting
                query = """
                    INSERT INTO SystemSettings (SettingKey, SettingValue, Description, DataType, LastModified)
                    VALUES (?, ?, ?, ?, datetime('now', 'localtime'))
                """
                self.DatabaseService.ExecuteNonQuery(query, (SettingKey, SettingValue, Description, DataType))
            
            return True
            
        except Exception as e:
            LoggingService.LogException(f"Error adding/updating system setting {SettingKey}", e, "AddOrUpdateSystemSetting", "DatabaseManager")
            return False
    
    def DeleteSystemSetting(self, SettingKey: str) -> bool:
        """Delete a system setting."""
        try:
            query = "DELETE FROM SystemSettings WHERE SettingKey = ?"
            affectedRows = self.DatabaseService.ExecuteNonQuery(query, (SettingKey,))
            return affectedRows > 0
            
        except Exception as e:
            LoggingService.LogException(f"Error deleting system setting {SettingKey}", e, "DeleteSystemSetting", "DatabaseManager")
            return False
    
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
                DateAdded=self.ConvertStringToDateTime(row['DateAdded']) if row['DateAdded'] else None,
                DateStarted=self.ConvertStringToDateTime(row['DateStarted']) if row['DateStarted'] else None
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
            DateAdded=self.ConvertStringToDateTime(row['DateAdded']) if row['DateAdded'] else None,
            DateStarted=self.ConvertStringToDateTime(row['DateStarted']) if row['DateStarted'] else None
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
    
    def UpdateTranscodeQueueStatus(self, JobId: int, Status: str) -> bool:
        """Update the status of a transcoding queue item."""
        try:
            LoggingService.LogFunctionEntry("UpdateTranscodeQueueStatus", "DatabaseManager", JobId, Status)
            
            query = "UPDATE TranscodeQueue SET Status = ? WHERE Id = ?"
            affectedRows = self.DatabaseService.ExecuteNonQuery(query, (Status, JobId))
            
            LoggingService.LogInfo(f"Updated transcoding queue item {JobId} status to {Status}", "DatabaseManager", "UpdateTranscodeQueueStatus")
            return affectedRows > 0
            
        except Exception as e:
            LoggingService.LogException("Exception updating transcoding queue status", e, "DatabaseManager", "UpdateTranscodeQueueStatus")
            return False
    
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
    
    def GetNextPendingTranscodeJob(self) -> Optional[TranscodeQueueModel]:
        """Get the next pending transcoding job (highest priority, oldest first)."""
        query = """
            SELECT Id, FilePath, FileName, Directory, SizeBytes, SizeMB, Priority, Status, DateAdded, DateStarted
            FROM TranscodeQueue 
            WHERE Status = 'Pending'
            ORDER BY Priority DESC, DateAdded ASC
            LIMIT 1
        """
        rows = self.DatabaseService.ExecuteQuery(query)
        
        if rows:
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
        
        return None
    
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
                   FfpmpegCommand, AudioBitrateKbps, VideoBitrateKbps, ProfileName, VMAF
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
                FfpmpegCommand=row['FfpmpegCommand'],
                AudioBitrateKbps=row['AudioBitrateKbps'],
                VideoBitrateKbps=row['VideoBitrateKbps'],
                ProfileName=row['ProfileName'],
                VMAF=row['VMAF']
            )
            attempts.append(attempt)
        
        return attempts
    
    def GetTranscodeAttemptById(self, AttemptId: int) -> Optional[TranscodeAttemptModel]:
        """Get a specific transcoding attempt by ID."""
        query = """
            SELECT Id, FilePath, AttemptDate, Quality, OldSizeBytes, NewSizeBytes, Success,
                   SizeReductionBytes, SizeReductionPercent, ErrorMessage, TranscodeDurationSeconds,
                   FfpmpegCommand, AudioBitrateKbps, VideoBitrateKbps, ProfileName, VMAF
            FROM TranscodeAttempts 
            WHERE Id = ?
        """
        rows = self.DatabaseService.ExecuteQuery(query, (AttemptId,))
        row = rows[0] if rows else None
        
        if row:
            return TranscodeAttemptModel(
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
                FfpmpegCommand=row['FfpmpegCommand'],
                AudioBitrateKbps=row['AudioBitrateKbps'],
                VideoBitrateKbps=row['VideoBitrateKbps'],
                ProfileName=row['ProfileName'],
                VMAF=row['VMAF']
            )
        return None
    
    def GetTranscodeAttemptsByFilePath(self, FilePath: str) -> List[TranscodeAttemptModel]:
        """Get all transcoding attempts for a specific file."""
        query = """
            SELECT Id, FilePath, AttemptDate, Quality, OldSizeBytes, NewSizeBytes, Success,
                   SizeReductionBytes, SizeReductionPercent, ErrorMessage, TranscodeDurationSeconds,
                   FfpmpegCommand, AudioBitrateKbps, VideoBitrateKbps, ProfileName, VMAF
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
                FfpmpegCommand=row['FfpmpegCommand'],
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
                         FfpmpegCommand, AudioBitrateKbps, VideoBitrateKbps, ProfileName, VMAF)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    parameters = (
                        Attempt.FilePath, Attempt.AttemptDate, Attempt.Quality,
                        Attempt.OldSizeBytes, Attempt.NewSizeBytes, Attempt.Success,
                        Attempt.SizeReductionBytes, Attempt.SizeReductionPercent, Attempt.ErrorMessage,
                        Attempt.TranscodeDurationSeconds,
                        Attempt.FfpmpegCommand,
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
                            TranscodeDurationSeconds = ?, FfpmpegCommand = ?, AudioBitrateKbps = ?,
                            VideoBitrateKbps = ?, ProfileName = ?, VMAF = ?
                        WHERE Id = ?
                    """
                    parameters = (
                        Attempt.FilePath, Attempt.AttemptDate, Attempt.Quality,
                        Attempt.OldSizeBytes, Attempt.NewSizeBytes, Attempt.Success,
                        Attempt.SizeReductionBytes, Attempt.SizeReductionPercent, Attempt.ErrorMessage,
                        Attempt.TranscodeDurationSeconds,
                        Attempt.FfpmpegCommand,
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
    
    def UpdateTranscodeAttempt(self, AttemptId: int, Updates: Dict[str, Any]) -> bool:
        """Update specific fields of a transcoding attempt."""
        try:
            LoggingService.LogFunctionEntry("UpdateTranscodeAttempt", "DatabaseManager", AttemptId, Updates)
            
            # Define all valid fields from TranscodeAttemptModel (excluding Id which is the key)
            valid_fields = [
                'FilePath', 'AttemptDate', 'Quality', 'OldSizeBytes', 'NewSizeBytes',
                'Success', 'SizeReductionBytes', 'SizeReductionPercent', 'ErrorMessage',
                'TranscodeDurationSeconds', 'FfpmpegCommand', 'AudioBitrateKbps',
                'VideoBitrateKbps', 'ProfileName', 'VMAF'
            ]
            
            # Build dynamic UPDATE query based on provided fields
            set_clauses = []
            parameters = []
            
            for field, value in Updates.items():
                if field in valid_fields:
                    set_clauses.append(f"{field} = ?")
                    parameters.append(value)
                elif field == 'FFmpegOutput':
                    # Map FFmpegOutput to FfpmpegCommand (correct column name) - legacy support
                    set_clauses.append("FfpmpegCommand = ?")
                    parameters.append(value)
                elif field == 'FFmpegError':
                    # Map FFmpegError to ErrorMessage (closest equivalent) - legacy support
                    set_clauses.append("ErrorMessage = ?")
                    parameters.append(value)
                else:
                    LoggingService.LogWarning(f"Unknown field '{field}' ignored in UpdateTranscodeAttempt", 
                                            "DatabaseManager", "UpdateTranscodeAttempt")
            
            if not set_clauses:
                LoggingService.LogWarning("No valid fields to update", "DatabaseManager", "UpdateTranscodeAttempt")
                return False
            
            query = f"UPDATE TranscodeAttempts SET {', '.join(set_clauses)} WHERE Id = ?"
            parameters.append(AttemptId)
            
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()
                cursor.execute(query, parameters)
                connection.commit()
                affected_rows = cursor.rowcount
                LoggingService.LogInfo(f"Updated {affected_rows} rows for attempt {AttemptId} with fields: {list(Updates.keys())}", 
                                     "DatabaseManager", "UpdateTranscodeAttempt")
                return affected_rows > 0
            finally:
                connection.close()
                
        except Exception as e:
            LoggingService.LogException("Exception in UpdateTranscodeAttempt", e, "DatabaseManager", "UpdateTranscodeAttempt")
            return False
    
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
            updateFields.append("LastAttemptDate = datetime('now', 'localtime')")
            
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
            
            # Reduced logging verbosity for routine queue statistics
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
    
    def GetProfileQuality(self, ProfileName: str) -> Optional[int]:
        """Get the Quality value from ProfileThresholds for a given profile name."""
        try:
            LoggingService.LogFunctionEntry("GetProfileQuality", "DatabaseManager", ProfileName)
            
            query = """
                SELECT pt.Quality 
                FROM ProfileThresholds pt
                JOIN Profiles p ON pt.ProfileId = p.Id
                WHERE p.ProfileName = ?
                LIMIT 1
            """
            rows = self.DatabaseService.ExecuteQuery(query, (ProfileName,))
            
            if rows:
                quality = rows[0]['Quality']
                LoggingService.LogInfo(f"Found Quality {quality} for Profile {ProfileName}", "DatabaseManager", "GetProfileQuality")
                return quality
            else:
                LoggingService.LogWarning(f"No Quality found for Profile {ProfileName}", "DatabaseManager", "GetProfileQuality")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception getting profile quality", e, "DatabaseManager", "GetProfileQuality")
            return None
    
    def GetProfileQualityForTargetResolution(self, ProfileName: str, SourceResolution: str) -> Optional[int]:
        """Get the Quality value from ProfileThresholds for the target resolution based on TranscodeDownTo setting."""
        try:
            LoggingService.LogFunctionEntry("GetProfileQualityForTargetResolution", "DatabaseManager", ProfileName, SourceResolution)
            
            # Convert pixel dimensions to resolution category
            resolutionCategory = self._ConvertPixelDimensionsToResolutionCategory(SourceResolution)
            LoggingService.LogInfo(f"Converted {SourceResolution} to {resolutionCategory}", "DatabaseManager", "GetProfileQualityForTargetResolution")
            
            # First, get the TranscodeDownTo setting for the source resolution
            query = """
                SELECT pt.TranscodeDownTo 
                FROM ProfileThresholds pt
                JOIN Profiles p ON pt.ProfileId = p.Id
                WHERE p.ProfileName = ? AND pt.Resolution = ?
                LIMIT 1
            """
            rows = self.DatabaseService.ExecuteQuery(query, (ProfileName, resolutionCategory))
            
            if not rows:
                LoggingService.LogWarning(f"No TranscodeDownTo found for Profile {ProfileName} and Resolution {SourceResolution}", "DatabaseManager", "GetProfileQualityForTargetResolution")
                return None
            
            targetResolution = rows[0]['TranscodeDownTo']
            if not targetResolution:
                LoggingService.LogInfo(f"No TranscodeDownTo set for Profile {ProfileName} and Resolution {SourceResolution}", "DatabaseManager", "GetProfileQualityForTargetResolution")
                return None
            
            # Handle "No downscaling" case - use current resolution's settings
            if targetResolution == 'No downscaling':
                # Get the Quality from the current resolution entry
                query = """
                    SELECT pt.Quality 
                    FROM ProfileThresholds pt
                    JOIN Profiles p ON pt.ProfileId = p.Id
                    WHERE p.ProfileName = ? AND pt.Resolution = ?
                    LIMIT 1
                """
                rows = self.DatabaseService.ExecuteQuery(query, (ProfileName, resolutionCategory))
                
                if rows:
                    quality = rows[0]['Quality']
                    LoggingService.LogInfo(f"Found Quality {quality} for Profile {ProfileName} with no downscaling (from source {SourceResolution})", "DatabaseManager", "GetProfileQualityForTargetResolution")
                    return quality
                else:
                    LoggingService.LogWarning(f"No Quality found for Profile {ProfileName} and Resolution {resolutionCategory} (no downscaling)", "DatabaseManager", "GetProfileQualityForTargetResolution")
                    return None
            else:
                # Now get the Quality for the target resolution
                query = """
                    SELECT pt.Quality 
                    FROM ProfileThresholds pt
                    JOIN Profiles p ON pt.ProfileId = p.Id
                    WHERE p.ProfileName = ? AND pt.Resolution = ?
                    LIMIT 1
                """
                rows = self.DatabaseService.ExecuteQuery(query, (ProfileName, targetResolution))
                
                if rows:
                    quality = rows[0]['Quality']
                    LoggingService.LogInfo(f"Found Quality {quality} for Profile {ProfileName} targeting {targetResolution} (from source {SourceResolution})", "DatabaseManager", "GetProfileQualityForTargetResolution")
                    return quality
                else:
                    LoggingService.LogWarning(f"No Quality found for Profile {ProfileName} and target Resolution {targetResolution}", "DatabaseManager", "GetProfileQualityForTargetResolution")
                    return None
                
        except Exception as e:
            LoggingService.LogException("Exception getting profile quality for target resolution", e, "DatabaseManager", "GetProfileQualityForTargetResolution")
            return None

    def GetProfileSettingsForTargetResolution(self, ProfileName: str, SourceResolution: str) -> Optional[Dict[str, Any]]:
        """Get all quality settings from ProfileThresholds for the target resolution based on TranscodeDownTo setting."""
        try:
            LoggingService.LogFunctionEntry("GetProfileSettingsForTargetResolution", "DatabaseManager", ProfileName, SourceResolution)
            
            # First try to find exact resolution match (for VR resolutions like 7680x3840)
            query = """
                SELECT pt.TranscodeDownTo 
                FROM ProfileThresholds pt
                JOIN Profiles p ON pt.ProfileId = p.Id
                WHERE p.ProfileName = ? AND pt.Resolution = ?
                LIMIT 1
            """
            rows = self.DatabaseService.ExecuteQuery(query, (ProfileName, SourceResolution))
            foundResolution = SourceResolution
            
            # If no exact match found, try standardized resolution
            if not rows:
                resolutionCategory = self._ConvertPixelDimensionsToResolutionCategory(SourceResolution)
                LoggingService.LogInfo(f"No exact match for {SourceResolution}, trying standardized {resolutionCategory}", "DatabaseManager", "GetProfileSettingsForTargetResolution")
                rows = self.DatabaseService.ExecuteQuery(query, (ProfileName, resolutionCategory))
                foundResolution = resolutionCategory
            else:
                LoggingService.LogInfo(f"Found exact resolution match for {SourceResolution}", "DatabaseManager", "GetProfileSettingsForTargetResolution")
            
            if not rows:
                LoggingService.LogWarning(f"No TranscodeDownTo found for Profile {ProfileName} and Resolution {SourceResolution}", "DatabaseManager", "GetProfileSettingsForTargetResolution")
                return None
            
            targetResolution = rows[0]['TranscodeDownTo']
            if not targetResolution:
                LoggingService.LogInfo(f"No TranscodeDownTo set for Profile {ProfileName} and Resolution {SourceResolution}, treating as 'No downscaling'", "DatabaseManager", "GetProfileSettingsForTargetResolution")
                targetResolution = 'No downscaling'
            
            # Handle "No downscaling" case (including empty TranscodeDownTo) - use current resolution's settings
            if targetResolution == 'No downscaling':
                # Get all settings from the current resolution entry (use the resolution that was found)
                query = """
                    SELECT pt.VideoBitrateKbps, pt.AudioBitrateKbps, pt.Quality, pt.Resolution, 
                           p.Codec, p.Preset, p.FilmGrain, p.YadifMode, p.YadifParity, p.YadifDeint, pt.ContainerType
                    FROM ProfileThresholds pt
                    JOIN Profiles p ON pt.ProfileId = p.Id
                    WHERE p.ProfileName = ? AND pt.Resolution = ?
                    LIMIT 1
                """
                rows = self.DatabaseService.ExecuteQuery(query, (ProfileName, foundResolution))
            else:
                # Now get all settings for the target resolution
                query = """
                    SELECT pt.VideoBitrateKbps, pt.AudioBitrateKbps, pt.Quality, pt.Resolution, 
                           p.Codec, p.Preset, p.FilmGrain, p.YadifMode, p.YadifParity, p.YadifDeint, pt.ContainerType
                    FROM ProfileThresholds pt
                    JOIN Profiles p ON pt.ProfileId = p.Id
                    WHERE p.ProfileName = ? AND pt.Resolution = ?
                    LIMIT 1
                """
                rows = self.DatabaseService.ExecuteQuery(query, (ProfileName, targetResolution))
            
            if rows:
                row = rows[0]
                # Calculate the actual target resolution for transcoding
                actualTargetResolution = SourceResolution if targetResolution == 'No downscaling' else targetResolution
                settings = {
                    'VideoBitrateKbps': row['VideoBitrateKbps'],
                    'AudioBitrateKbps': row['AudioBitrateKbps'],
                    'Quality': row['Quality'],
                    'TargetResolution': actualTargetResolution,  # Use the actual target resolution from TranscodeDownTo
                    'Codec': row['Codec'],
                    'Preset': row['Preset'],
                    'FilmGrain': row['FilmGrain'],
                    'YadifMode': row['YadifMode'],
                    'YadifParity': row['YadifParity'],
                    'YadifDeint': row['YadifDeint'],
                    'ContainerType': row['ContainerType']
                }
                LoggingService.LogInfo(f"Found ProfileSettings for {ProfileName} targeting {actualTargetResolution}: {settings}", "DatabaseManager", "GetProfileSettingsForTargetResolution")
                return settings
            else:
                LoggingService.LogWarning(f"No ProfileSettings found for Profile {ProfileName} and target Resolution {targetResolution}", "DatabaseManager", "GetProfileSettingsForTargetResolution")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception getting profile settings for target resolution", e, "DatabaseManager", "GetProfileSettingsForTargetResolution")
            return None
    
    def _ConvertPixelDimensionsToResolutionCategory(self, PixelDimensions: str) -> str:
        """Convert pixel dimensions (e.g., '3840x2160') to resolution category (e.g., '2160p')."""
        try:
            if not PixelDimensions or 'x' not in PixelDimensions:
                return PixelDimensions  # Return as-is if not in expected format
            
            # Extract height from pixel dimensions
            height = int(PixelDimensions.split('x')[1])
            
            # Map height to resolution category
            if height >= 2160:
                return "2160p"
            elif height >= 1080:
                return "1080p"
            elif height >= 720:
                return "720p"
            elif height >= 480:
                return "480p"
            else:
                return "480p"  # Default fallback
                
        except (ValueError, IndexError):
            # If parsing fails, return original value
            return PixelDimensions
    
    def SaveTranscodeProgress(self, TranscodeAttemptId: int, CurrentPhase: str, ProgressPercent: float, 
                             CurrentFrame: int, CurrentFPS: float, CurrentBitrate: str, 
                             CurrentTime: str, CurrentSpeed: str, ETA: str = "Unknown", 
                             TotalFrames: int = 0, AverageFPS: float = 0.0) -> int:
        """Save transcoding progress information in the TranscodeProgress table. Uses single record per transcode with UPDATE."""
        try:
            # Function entry logging removed for frequent progress updates
            
            # Check if progress record already exists
            existingQuery = "SELECT Id FROM TranscodeProgress WHERE TranscodeAttemptId = ?"
            existingRows = self.DatabaseService.ExecuteQuery(existingQuery, (TranscodeAttemptId,))
            
            if existingRows:
                # Update existing record
                updateQuery = """
                    UPDATE TranscodeProgress SET
                        CurrentPhase = ?, ProgressPercent = ?, CurrentFrame = ?, CurrentFPS = ?,
                        CurrentBitrate = ?, CurrentTime = ?, CurrentSpeed = ?, ETA = ?,
                        TotalFrames = ?, AverageFPS = ?, LastProgressUpdate = datetime('now', 'localtime')
                    WHERE TranscodeAttemptId = ?
                """
                parameters = (CurrentPhase, ProgressPercent, CurrentFrame, CurrentFPS,
                             CurrentBitrate, CurrentTime, CurrentSpeed, ETA,
                             TotalFrames, AverageFPS, TranscodeAttemptId)
                
                result = self.DatabaseService.ExecuteNonQuery(updateQuery, parameters)
                LoggingService.LogDebug(f"Updated progress record for attempt {TranscodeAttemptId}: {CurrentPhase} ({ProgressPercent}%) - Frame: {CurrentFrame}, FPS: {CurrentFPS}, ETA: {ETA}", "DatabaseManager", "SaveTranscodeProgress")
                return result
            else:
                # Insert new record
                insertQuery = """
                    INSERT INTO TranscodeProgress 
                    (TranscodeAttemptId, PassNumber, PassType, CurrentPhase, ProgressPercent, CurrentFrame, CurrentFPS, 
                     CurrentBitrate, CurrentTime, CurrentSpeed, ETA, TotalFrames, AverageFPS, LastProgressUpdate)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
                """
                parameters = (TranscodeAttemptId, 1, "Encoding", CurrentPhase, ProgressPercent, CurrentFrame, CurrentFPS,
                             CurrentBitrate, CurrentTime, CurrentSpeed, ETA, TotalFrames, AverageFPS)
                
                progressId = self.DatabaseService.ExecuteNonQuery(insertQuery, parameters)
                LoggingService.LogDebug(f"Inserted new progress record for attempt {TranscodeAttemptId}: {CurrentPhase} ({ProgressPercent}%) - Frame: {CurrentFrame}, FPS: {CurrentFPS}, ETA: {ETA}", "DatabaseManager", "SaveTranscodeProgress")
                return progressId
                
        except Exception as e:
            LoggingService.LogException("Exception saving transcode progress", e, "DatabaseManager", "SaveTranscodeProgress")
            return 0
    
    def GetLatestTranscodeProgress(self, TranscodeAttemptId: int) -> Optional[Dict[str, Any]]:
        """Get the latest progress information for a transcoding attempt."""
        try:
            LoggingService.LogFunctionEntry("GetLatestTranscodeProgress", "DatabaseManager", TranscodeAttemptId)
            
            query = """
                SELECT CurrentPhase, ProgressPercent, CurrentFrame, TotalFrames, CurrentFPS, 
                       AverageFPS, CurrentBitrate, CurrentTime, CurrentSpeed, ETA, 
                       PassDuration, LastProgressUpdate
                FROM TranscodeProgress 
                WHERE TranscodeAttemptId = ? 
                ORDER BY LastProgressUpdate DESC 
                LIMIT 1
            """
            
            rows = self.DatabaseService.ExecuteQuery(query, (TranscodeAttemptId,))
            
            if rows:
                row = rows[0]
                progress = {
                    'CurrentPhase': row['CurrentPhase'],
                    'ProgressPercent': row['ProgressPercent'],
                    'CurrentFrame': row['CurrentFrame'],
                    'TotalFrames': row['TotalFrames'],
                    'CurrentFPS': row['CurrentFPS'],
                    'AverageFPS': row['AverageFPS'],
                    'CurrentBitrate': row['CurrentBitrate'],
                    'CurrentTime': row['CurrentTime'],
                    'CurrentSpeed': row['CurrentSpeed'],
                    'ETA': row['ETA'],
                    'PassDuration': row['PassDuration'],
                    'LastProgressUpdate': row['LastProgressUpdate']
                }
                LoggingService.LogDebug(f"Retrieved latest progress for attempt {TranscodeAttemptId}: {progress['CurrentPhase']} ({progress['ProgressPercent']}%)", "DatabaseManager", "GetLatestTranscodeProgress")
                return progress
            else:
                LoggingService.LogDebug(f"No progress found for attempt {TranscodeAttemptId}", "DatabaseManager", "GetLatestTranscodeProgress")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception getting latest transcode progress", e, "DatabaseManager", "GetLatestTranscodeProgress")
            return None
    
    def GetTranscodeProgressByPhase(self, TranscodeAttemptId: int, CurrentPhase: str) -> Optional[Dict[str, Any]]:
        """Get progress information for a specific phase of a transcoding attempt."""
        try:
            LoggingService.LogFunctionEntry("GetTranscodeProgressByPhase", "DatabaseManager", TranscodeAttemptId, CurrentPhase)
            
            query = """
                SELECT CurrentPhase, ProgressPercent, CurrentFrame, CurrentFPS, 
                       CurrentBitrate, CurrentTime, CurrentSpeed, LastProgressUpdate
                FROM TranscodeProgress 
                WHERE TranscodeAttemptId = ? AND CurrentPhase = ?
                ORDER BY LastProgressUpdate DESC 
                LIMIT 1
            """
            
            rows = self.DatabaseService.ExecuteQuery(query, (TranscodeAttemptId, CurrentPhase))
            
            if rows:
                row = rows[0]
                progress = {
                    'CurrentPhase': row['CurrentPhase'],
                    'ProgressPercent': row['ProgressPercent'],
                    'CurrentFrame': row['CurrentFrame'],
                    'CurrentFPS': row['CurrentFPS'],
                    'CurrentBitrate': row['CurrentBitrate'],
                    'CurrentTime': row['CurrentTime'],
                    'CurrentSpeed': row['CurrentSpeed'],
                    'LastProgressUpdate': row['LastProgressUpdate']
                }
                LoggingService.LogDebug(f"Retrieved progress for attempt {TranscodeAttemptId} phase {CurrentPhase}: {progress['ProgressPercent']}%", "DatabaseManager", "GetTranscodeProgressByPhase")
                return progress
            else:
                LoggingService.LogDebug(f"No progress found for attempt {TranscodeAttemptId} phase {CurrentPhase}", "DatabaseManager", "GetTranscodeProgressByPhase")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception getting transcode progress by phase", e, "DatabaseManager", "GetTranscodeProgressByPhase")
            return None
    
    def GetCurrentTranscodeProgress(self) -> Optional[Dict[str, Any]]:
        """Get the current active transcoding progress (latest progress from any active attempt)."""
        try:
            LoggingService.LogFunctionEntry("GetCurrentTranscodeProgress", "DatabaseManager")
            
            # Get the most recent progress from any transcoding attempt with MediaFiles TotalFrames
            query = """
                SELECT tp.TranscodeAttemptId, tp.CurrentPhase, tp.ProgressPercent, tp.CurrentFrame, 
                       tp.TotalFrames, tp.CurrentFPS, tp.AverageFPS, tp.CurrentBitrate, 
                       tp.CurrentTime, tp.CurrentSpeed, tp.ETA, tp.PassDuration, 
                       tp.LastProgressUpdate, ta.FilePath, ta.Quality, ta.ProfileName, ta.AttemptDate,
                       mf.TotalFrames as MediaFileTotalFrames
                FROM TranscodeProgress tp
                INNER JOIN TranscodeAttempts ta ON tp.TranscodeAttemptId = ta.Id
                LEFT JOIN MediaFiles mf ON ta.FilePath = mf.FilePath
                ORDER BY tp.LastProgressUpdate DESC 
                LIMIT 1
            """
            
            result = self.DatabaseService.ExecuteQuery(query)
            
            if result and len(result) > 0:
                row = result[0]
                # Extract filename from filepath
                FilePath = row[13]
                FileName = FilePath.split('\\')[-1] if FilePath else "Unknown"
                
                # Use MediaFiles TotalFrames if available, fallback to TranscodeProgress TotalFrames
                MediaFileTotalFrames = row[17]  # mf.TotalFrames
                ProgressTotalFrames = row[4]    # tp.TotalFrames
                ActualTotalFrames = MediaFileTotalFrames if MediaFileTotalFrames else ProgressTotalFrames
                
                # Recalculate progress percentage if we have better TotalFrames data
                CurrentFrame = row[3]
                RecalculatedProgress = 0.0
                if ActualTotalFrames and ActualTotalFrames > 0 and CurrentFrame > 0:
                    RecalculatedProgress = min((CurrentFrame / ActualTotalFrames) * 100, 95.0)
                
                progressData = {
                    'Success': True,
                    'AttemptId': row[0],  # Frontend expects AttemptId
                    'TranscodeAttemptId': row[0],
                    'CurrentPhase': row[1],
                    'ProgressPercent': RecalculatedProgress if RecalculatedProgress > 0 else row[2],
                    'CurrentFrame': row[3],
                    'TotalFrames': ActualTotalFrames,
                    'CurrentFPS': row[5],
                    'AverageFPS': row[6],
                    'CurrentBitrate': row[7],
                    'CurrentTime': row[8],
                    'CurrentSpeed': row[9],
                    'ETA': row[10],
                    'PassDuration': row[11],
                    'LastUpdate': row[12],  # Frontend expects LastUpdate
                    'LastProgressUpdate': row[12],
                    'FilePath': FilePath,
                    'FileName': FileName,  # Frontend expects FileName
                    'StartTime': row[16],  # Frontend expects StartTime
                    'Quality': row[14],
                    'ProfileName': row[15],
                    'MediaFileTotalFrames': MediaFileTotalFrames,  # For debugging
                    'RecalculatedProgress': RecalculatedProgress > 0  # Flag for debugging
                }
                
                LoggingService.LogDebug(f"Found current progress: {progressData['CurrentPhase']} ({progressData['ProgressPercent']}%) for {progressData['FileName']}", "DatabaseManager", "GetCurrentTranscodeProgress")
                return progressData
            else:
                LoggingService.LogDebug("No current transcoding progress found", "DatabaseManager", "GetCurrentTranscodeProgress")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception getting current transcode progress", e, "DatabaseManager", "GetCurrentTranscodeProgress")
            return None
    
    def DeleteTranscodeProgress(self, TranscodeAttemptId: int) -> bool:
        """Delete all progress records for a specific transcoding attempt."""
        try:
            LoggingService.LogFunctionEntry("DeleteTranscodeProgress", "DatabaseManager", TranscodeAttemptId)
            
            query = "DELETE FROM TranscodeProgress WHERE TranscodeAttemptId = ?"
            rowsAffected = self.DatabaseService.ExecuteNonQuery(query, (TranscodeAttemptId,))
            
            LoggingService.LogInfo(f"Deleted {rowsAffected} progress records for attempt {TranscodeAttemptId}", "DatabaseManager", "DeleteTranscodeProgress")
            return True
                
        except Exception as e:
            LoggingService.LogException("Exception deleting transcode progress", e, "DatabaseManager", "DeleteTranscodeProgress")
            return False
    
    def CleanupOldProgressData(self, DaysToKeep: int = 7) -> int:
        """Clean up old progress data to keep the table manageable."""
        try:
            LoggingService.LogFunctionEntry("CleanupOldProgressData", "DatabaseManager", DaysToKeep)
            
            query = """
                DELETE FROM TranscodeProgress 
                WHERE LastProgressUpdate < datetime('now', '-{} days')
            """.format(DaysToKeep)
            
            rowsAffected = self.DatabaseService.ExecuteNonQuery(query)
            
            LoggingService.LogInfo(f"Cleaned up {rowsAffected} old progress records (older than {DaysToKeep} days)", "DatabaseManager", "CleanupOldProgressData")
            return rowsAffected
                
        except Exception as e:
            LoggingService.LogException("Exception cleaning up old progress data", e, "DatabaseManager", "CleanupOldProgressData")
            return 0
    
    def ConvertStringToDateTime(self, DateString: str) -> Optional[datetime]:
        """Convert date string from database to datetime object."""
        if not DateString:
            return None
        try:
            if 'T' in DateString:
                return datetime.fromisoformat(DateString.replace('Z', '+00:00'))
            else:
                return datetime.strptime(DateString, '%Y-%m-%d %H:%M:%S.%f')
        except (ValueError, AttributeError):
            try:
                return datetime.strptime(DateString, '%Y-%m-%d %H:%M:%S')
            except (ValueError, AttributeError):
                LoggingService.LogWarning(f"Failed to convert date string to datetime: {DateString}", "DatabaseManager", "ConvertStringToDateTime")
                return None
    
    # Quality Testing Database Methods
    
    def SaveServiceStatus(self, ServiceStatus: Dict[str, Any]) -> bool:
        """Save service status to database."""
        try:
            LoggingService.LogFunctionEntry("SaveServiceStatus", "DatabaseManager")
            
            # Check if service status already exists
            ExistingStatus = self.GetServiceStatus(ServiceStatus.get('ServiceName', ''))
            
            if ExistingStatus:
                # Update existing status
                query = """
                UPDATE ServiceStatus SET 
                    Status = ?, HealthStatus = ?, StartTime = ?, LastHealthCheck = ?,
                    UptimeSeconds = ?, MemoryUsage = ?, CPUUsage = ?, DatabaseConnection = ?,
                    DiskSpace = ?, ErrorCount = ?, MaxErrors = ?, ActiveJobsCount = ?,
                    IsProcessing = ?, ProcessId = ?, Version = ?, ServiceType = ?,
                    MaxConcurrentJobs = ?, UpdatedAt = datetime('now', 'localtime')
                WHERE ServiceName = ?
                """
                parameters = (
                    ServiceStatus.get('Status'),
                    ServiceStatus.get('HealthStatus'),
                    ServiceStatus.get('StartTime'),
                    ServiceStatus.get('LastHealthCheck'),
                    ServiceStatus.get('UptimeSeconds'),
                    ServiceStatus.get('MemoryUsage'),
                    ServiceStatus.get('CPUUsage'),
                    ServiceStatus.get('DatabaseConnection'),
                    ServiceStatus.get('DiskSpace'),
                    ServiceStatus.get('ErrorCount'),
                    ServiceStatus.get('MaxErrors'),
                    ServiceStatus.get('ActiveJobsCount'),
                    ServiceStatus.get('IsProcessing'),
                    ServiceStatus.get('ProcessId'),
                    ServiceStatus.get('Version'),
                    ServiceStatus.get('ServiceType'),
                    ServiceStatus.get('MaxConcurrentJobs', 1),
                    ServiceStatus.get('ServiceName')
                )
            else:
                # Insert new status
                query = """
                INSERT INTO ServiceStatus (
                    ServiceName, Status, HealthStatus, StartTime, LastHealthCheck,
                    UptimeSeconds, MemoryUsage, CPUUsage, DatabaseConnection, DiskSpace,
                    ErrorCount, MaxErrors, ActiveJobsCount, IsProcessing, ProcessId,
                    Version, ServiceType, MaxConcurrentJobs, CreatedAt, UpdatedAt
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), datetime('now', 'localtime'))
                """
                parameters = (
                    ServiceStatus.get('ServiceName'),
                    ServiceStatus.get('Status'),
                    ServiceStatus.get('HealthStatus'),
                    ServiceStatus.get('StartTime'),
                    ServiceStatus.get('LastHealthCheck'),
                    ServiceStatus.get('UptimeSeconds'),
                    ServiceStatus.get('MemoryUsage'),
                    ServiceStatus.get('CPUUsage'),
                    ServiceStatus.get('DatabaseConnection'),
                    ServiceStatus.get('DiskSpace'),
                    ServiceStatus.get('ErrorCount'),
                    ServiceStatus.get('MaxErrors'),
                    ServiceStatus.get('ActiveJobsCount'),
                    ServiceStatus.get('IsProcessing'),
                    ServiceStatus.get('ProcessId'),
                    ServiceStatus.get('Version'),
                    ServiceStatus.get('ServiceType'),
                    ServiceStatus.get('MaxConcurrentJobs', 1)
                )
            
            self.DatabaseService.ExecuteNonQuery(query, parameters)
            LoggingService.LogDebug(f"Service status saved for {ServiceStatus.get('ServiceName')}", "DatabaseManager", "SaveServiceStatus")
            return True
            
        except Exception as e:
            LoggingService.LogException("Exception saving service status", e, "DatabaseManager", "SaveServiceStatus")
            return False
    
    def UpdateServiceStatus(self, ServiceName: str, StatusData: Dict[str, Any]) -> bool:
        """Update service status in database."""
        try:
            LoggingService.LogFunctionEntry("UpdateServiceStatus", "DatabaseManager", ServiceName)
            
            # Build dynamic update query
            UpdateFields = []
            Parameters = []
            
            for key, value in StatusData.items():
                UpdateFields.append(f"{key} = ?")
                Parameters.append(value)
            
            if not UpdateFields:
                LoggingService.LogWarning("No fields to update", "DatabaseManager", "UpdateServiceStatus")
                return False
            
            Parameters.append(ServiceName)
            query = f"UPDATE ServiceStatus SET {', '.join(UpdateFields)}, UpdatedAt = datetime('now', 'localtime') WHERE ServiceName = ?"
            
            self.DatabaseService.ExecuteNonQuery(query, Parameters)
            LoggingService.LogDebug(f"Service status updated for {ServiceName}", "DatabaseManager", "UpdateServiceStatus")
            return True
            
        except Exception as e:
            LoggingService.LogException("Exception updating service status", e, "DatabaseManager", "UpdateServiceStatus")
            return False
    
    def GetServiceStatus(self, ServiceName: str) -> Optional[Dict[str, Any]]:
        """Get current service status."""
        try:
            LoggingService.LogFunctionEntry("GetServiceStatus", "DatabaseManager", ServiceName)
            
            query = "SELECT * FROM ServiceStatus WHERE ServiceName = ?"
            rows = self.DatabaseService.ExecuteQuery(query, (ServiceName,))
            
            if rows:
                LoggingService.LogDebug(f"Retrieved service status for {ServiceName}", "DatabaseManager", "GetServiceStatus")
                # Convert sqlite3.Row to dictionary
                row = rows[0]
                return dict(row)
            else:
                LoggingService.LogDebug(f"No service status found for {ServiceName}", "DatabaseManager", "GetServiceStatus")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception getting service status", e, "DatabaseManager", "GetServiceStatus")
            return None
    
    
    
    
    
    
    
    
    
    def CreateServiceCommand(self, CommandData: Dict[str, Any]) -> int:
        """Create a new service command."""
        try:
            LoggingService.LogFunctionEntry("CreateServiceCommand", "DatabaseManager")
            
            query = """
                INSERT INTO ServiceCommands (
                CommandType, SourceService, TargetService, Parameters, Status, 
                Priority, CreatedBy, CreatedAt, UpdatedAt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), datetime('now', 'localtime'))
            """
            
            import json
            parameters = (
                CommandData.get('CommandType'),
                CommandData.get('SourceService', 'ServiceControlController'),
                CommandData.get('TargetService'),
                json.dumps(CommandData.get('Parameters', {})),
                CommandData.get('Status', 'Pending'),
                CommandData.get('Priority', 1),
                CommandData.get('CreatedBy', 'Unknown')
            )
            
            result = self.DatabaseService.ExecuteNonQuery(query, parameters)
            
            if result:
                # Get the ID of the created command
                command_id = self.DatabaseService.GetLastInsertId()
                LoggingService.LogInfo(f"Created ServiceCommand {command_id}", "DatabaseManager", "CreateServiceCommand")
                return command_id
            else:
                LoggingService.LogError("Failed to create ServiceCommand", "DatabaseManager", "CreateServiceCommand")
                return 0
                
        except Exception as e:
            LoggingService.LogException("Error creating ServiceCommand", e, "DatabaseManager", "CreateServiceCommand")
            return 0
    
    def UpdateServiceCommandStatus(self, CommandId: int, Status: str, Result: str = None) -> bool:
        """Update service command status."""
        try:
            LoggingService.LogFunctionEntry("UpdateServiceCommandStatus", "DatabaseManager")
            
            query = """
            UPDATE ServiceCommands 
            SET Status = ?, Result = ?, UpdatedAt = datetime('now', 'localtime')
            WHERE Id = ?
            """
            
            result = self.DatabaseService.ExecuteNonQuery(query, (Status, Result, CommandId))
            
            if result:
                LoggingService.LogInfo(f"Updated ServiceCommand {CommandId} status to {Status}", "DatabaseManager", "UpdateServiceCommandStatus")
                return True
            else:
                LoggingService.LogError(f"Failed to update ServiceCommand {CommandId}", "DatabaseManager", "UpdateServiceCommandStatus")
                return False
                
        except Exception as e:
            LoggingService.LogException("Error updating ServiceCommand status", e, "DatabaseManager", "UpdateServiceCommandStatus")
            return False
    
    def GetPendingCommandsForService(self, ServiceName: str) -> List[Dict[str, Any]]:
        """Get pending commands for specific service."""
        try:
            LoggingService.LogFunctionEntry("GetPendingCommandsForService", "DatabaseManager", ServiceName)
            
            query = """
            SELECT * FROM ServiceCommands 
            WHERE TargetService = ? AND Status = 'Pending'
            ORDER BY Priority DESC, CreatedAt ASC
            """
            rows = self.DatabaseService.ExecuteQuery(query, (ServiceName,))
            
            LoggingService.LogDebug(f"Retrieved {len(rows)} pending commands for {ServiceName}", "DatabaseManager", "GetPendingCommandsForService")
            return rows
            
        except Exception as e:
            LoggingService.LogException("Exception getting pending commands for service", e, "DatabaseManager", "GetPendingCommandsForService")
            return []
    
    def GetCodecFlagsByCodecName(self, CodecName: str) -> Optional[Dict[str, Any]]:
        """Get codec flags by codec name."""
        try:
            LoggingService.LogFunctionEntry("GetCodecFlagsByCodecName", "DatabaseManager", CodecName)
            
            query = """
            SELECT Id, CodecName, DisplayName, PresetType, PresetMin, PresetMax, PresetDefault, 
                   PresetOptions, FilmGrainType, FilmGrainMin, FilmGrainMax, FilmGrainDefault, 
                   TuneOptions, CreatedDate, LastModified
            FROM CodecFlags 
            WHERE CodecName = ?
            """
            rows = self.DatabaseService.ExecuteQuery(query, (CodecName,))
            
            if not rows:
                LoggingService.LogWarning(f"No codec flags found for codec: {CodecName}", "DatabaseManager", "GetCodecFlagsByCodecName")
                return None
            
            row = rows[0]
            LoggingService.LogInfo(f"Retrieved codec flags for {CodecName}", "DatabaseManager", "GetCodecFlagsByCodecName")
            return dict(row)
            
        except Exception as e:
            LoggingService.LogException("Exception getting codec flags by codec name", e, "DatabaseManager", "GetCodecFlagsByCodecName")
            return None
    
    def GetCodecParametersByCodecFlagsId(self, CodecFlagsId: int) -> List[Dict[str, Any]]:
        """Get codec parameters by codec flags ID."""
        try:
            LoggingService.LogFunctionEntry("GetCodecParametersByCodecFlagsId", "DatabaseManager", CodecFlagsId)
            
            query = """
            SELECT Id, CodecFlagsId, ParameterName, ParameterType, MinValue, MaxValue, 
                   DefaultValue, Description, FFmpegFlag, CreatedDate
            FROM CodecParameters 
            WHERE CodecFlagsId = ?
            ORDER BY ParameterName
            """
            rows = self.DatabaseService.ExecuteQuery(query, (CodecFlagsId,))
            
            LoggingService.LogInfo(f"Retrieved {len(rows)} codec parameters for CodecFlagsId {CodecFlagsId}", "DatabaseManager", "GetCodecParametersByCodecFlagsId")
            return [dict(row) for row in rows]
            
        except Exception as e:
            LoggingService.LogException("Exception getting codec parameters by codec flags ID", e, "DatabaseManager", "GetCodecParametersByCodecFlagsId")
            return []

    def CheckDatabaseConnection(self) -> bool:
        """Check if database connection is available."""
        try:
            # Test database connection with simple query
            testResult = self.DatabaseService.ExecuteQuery("SELECT 1")
            if testResult:
                # Only log failures, not successful connections to avoid log flooding
                return True
            else:
                LoggingService.LogError("Database connection test failed", "DatabaseManager", "CheckDatabaseConnection")
                return False
                
        except Exception as e:
            LoggingService.LogException("Exception checking database connection", e, "DatabaseManager", "CheckDatabaseConnection")
            return False
    
    # Quality Test Progress Management Methods
    
    
    # Quality Test Results Management Methods
    
    



    
    
    
    def GetKeepSourceSetting(self, TranscodeAttemptId: int) -> Optional[bool]:
        """Get the KeepSource setting for a transcode attempt."""
        try:
            # Get the assigned profile from the transcode attempt
            query = '''
            SELECT pt.KeepSource 
            FROM ProfileThresholds pt
            JOIN Profiles p ON pt.ProfileId = p.Id
            JOIN MediaFiles mf ON p.ProfileName = mf.AssignedProfile
            JOIN TranscodeAttempts ta ON mf.FilePath = ta.FilePath
            WHERE ta.Id = ?
            '''
            result = self.DatabaseService.ExecuteQuery(query, (TranscodeAttemptId,))
            
            if result:
                return bool(result[0]['KeepSource'])
            return None
            
        except Exception as e:
            LoggingService.LogException(f"Exception getting KeepSource setting for transcode attempt {TranscodeAttemptId}", e, 
                                      "DatabaseManager", "GetKeepSourceSetting")
            return None
    
    def SaveMediaFileArchive(self, MediaFileId: int, TranscodeAttemptId: int) -> int:
        """Archive original file details using INSERT SELECT from MediaFiles table."""
        try:
            LoggingService.LogFunctionEntry("SaveMediaFileArchive", "DatabaseManager", MediaFileId, TranscodeAttemptId)
            
            query = """
                INSERT INTO MediaFilesArchive 
                SELECT *, datetime('now', 'localtime'), ? 
                FROM MediaFiles 
                WHERE Id = ?
            """
            
            parameters = (TranscodeAttemptId, MediaFileId)
            
            result = self.DatabaseService.ExecuteNonQuery(query, parameters)
            
            if result:
                LoggingService.LogInfo(f"Successfully archived original file details for MediaFile {MediaFileId}, Archive ID: {result}", 
                                     "DatabaseManager", "SaveMediaFileArchive")
                return result
            else:
                LoggingService.LogError(f"Failed to archive original file details for MediaFile {MediaFileId}", 
                                      "DatabaseManager", "SaveMediaFileArchive")
                return 0
                
        except Exception as e:
            LoggingService.LogException("Exception saving media file archive", e, "DatabaseManager", "SaveMediaFileArchive")
            return 0
    
    # Quality Testing Methods
    
    
    
    # ActiveJobs Management Methods
    
    def CreateActiveJob(self, ServiceName: str, JobType: str, QueueId: int, ProcessId: int = None, ThreadId: int = None) -> int:
        """Create an active job record for tracking."""
        try:
            LoggingService.LogFunctionEntry("CreateActiveJob", "DatabaseManager", ServiceName, JobType, QueueId, ProcessId, ThreadId)
            
            query = """
                INSERT INTO ActiveJobs (ServiceName, JobType, QueueId, ProcessId, ThreadId, Status, StartedAt)
                VALUES (?, ?, ?, ?, ?, 'Running', datetime('now', 'localtime'))
            """
            
            result = self.DatabaseService.ExecuteNonQuery(query, (ServiceName, JobType, QueueId, ProcessId, ThreadId))
            
            if result > 0:
                # Get the inserted ID from DatabaseService
                job_id = self.DatabaseService.LastInsertId
                
                LoggingService.LogInfo(f"Created active job {job_id} for {ServiceName} - JobType: {JobType}, QueueId: {QueueId}", "DatabaseManager", "CreateActiveJob")
                return job_id
            else:
                LoggingService.LogError(f"Failed to create active job for {ServiceName}", "DatabaseManager", "CreateActiveJob")
                return 0
                
        except Exception as e:
            LoggingService.LogException("Exception creating active job", e, "DatabaseManager", "CreateActiveJob")
            return 0
    
    def CompleteActiveJob(self, JobId: int, Success: bool = True, ErrorMessage: str = None) -> bool:
        """Complete an active job and remove it from tracking."""
        try:
            LoggingService.LogFunctionEntry("CompleteActiveJob", "DatabaseManager", JobId, Success, ErrorMessage)
            
            status = "Completed" if Success else "Failed"
            
            # Update the job status first
            update_query = """
                UPDATE ActiveJobs 
                SET Status = ?, UpdatedAt = datetime('now', 'localtime')
                WHERE Id = ?
            """
            
            self.DatabaseService.ExecuteNonQuery(update_query, (status, JobId))
            
            # Log the completion
            if Success:
                LoggingService.LogInfo(f"Active job {JobId} completed successfully", "DatabaseManager", "CompleteActiveJob")
            else:
                LoggingService.LogError(f"Active job {JobId} failed: {ErrorMessage}", "DatabaseManager", "CompleteActiveJob")
            
            # Remove from ActiveJobs table
            delete_query = "DELETE FROM ActiveJobs WHERE Id = ?"
            result = self.DatabaseService.ExecuteNonQuery(delete_query, (JobId,))
            
            return result > 0
            
        except Exception as e:
            LoggingService.LogException("Exception completing active job", e, "DatabaseManager", "CompleteActiveJob")
            return False
    
    def GetActiveJobByQueueId(self, ServiceName: str, QueueId: int) -> Optional[Dict[str, Any]]:
        """Get active job by service name and queue ID."""
        try:
            query = """
                SELECT Id, ServiceName, JobType, QueueId, ProcessId, ThreadId, 
                       StartedAt, Status, CreatedAt, UpdatedAt
                FROM ActiveJobs 
                WHERE ServiceName = ? AND QueueId = ? AND Status = 'Running'
            """
            
            rows = self.DatabaseService.ExecuteQuery(query, (ServiceName, QueueId))
            
            if rows:
                return dict(rows[0])
            return None
            
        except Exception as e:
            LoggingService.LogException("Exception getting active job by queue ID", e, "DatabaseManager", "GetActiveJobByQueueId")
            return None
    
    def GetActiveJobsByService(self, ServiceName: str) -> List[Dict[str, Any]]:
        """Get all active jobs for a specific service."""
        try:
            query = """
                SELECT Id, ServiceName, JobType, QueueId, ProcessId, ThreadId, 
                       StartedAt, Status, CreatedAt, UpdatedAt
                FROM ActiveJobs 
                WHERE ServiceName = ? AND Status = 'Running'
                ORDER BY StartedAt ASC
            """
            
            rows = self.DatabaseService.ExecuteQuery(query, (ServiceName,))
            return [dict(row) for row in rows]
            
        except Exception as e:
            LoggingService.LogException("Exception getting active jobs by service", e, "DatabaseManager", "GetActiveJobsByService")
            return []
    
    def GetAllActiveJobs(self) -> List[Dict[str, Any]]:
        """Get all active jobs across all services."""
        try:
            query = """
                SELECT Id, ServiceName, JobType, QueueId, ProcessId, ThreadId, 
                       StartedAt, Status, CreatedAt, UpdatedAt
                FROM ActiveJobs 
                WHERE Status = 'Running'
                ORDER BY ServiceName, StartedAt ASC
            """
            
            rows = self.DatabaseService.ExecuteQuery(query)
            return [dict(row) for row in rows]
            
        except Exception as e:
            LoggingService.LogException("Exception getting all active jobs", e, "DatabaseManager", "GetAllActiveJobs")
            return []
    
    def CancelActiveJob(self, JobId: int) -> bool:
        """Cancel a specific active job by ID."""
        try:
            LoggingService.LogFunctionEntry("CancelActiveJob", "DatabaseManager", JobId)
            
            # Update job status to cancelled
            update_query = """
                UPDATE ActiveJobs 
                SET Status = 'Cancelled', UpdatedAt = datetime('now', 'localtime')
                WHERE Id = ?
            """
            
            result = self.DatabaseService.ExecuteNonQuery(update_query, (JobId,))
            
            if result > 0:
                LoggingService.LogInfo(f"Active job {JobId} cancelled successfully", "DatabaseManager", "CancelActiveJob")
                return True
            else:
                LoggingService.LogWarning(f"Active job {JobId} not found or already cancelled", "DatabaseManager", "CancelActiveJob")
                return False
                
        except Exception as e:
            LoggingService.LogException("Exception cancelling active job", e, "DatabaseManager", "CancelActiveJob")
            return False
    
    # Quality Testing Workflow Methods
    
    def CreateQualityTestingJob(self, TranscodeAttemptId: int) -> int:
        """Create a quality testing job from a completed transcode attempt."""
        try:
            LoggingService.LogFunctionEntry("CreateQualityTestingJob", "DatabaseManager", TranscodeAttemptId)
            
            # Get the transcode attempt details
            attempt_query = """
                SELECT Id, FilePath, ProfileName, VMAF
                FROM TranscodeAttempts 
                WHERE Id = ? AND Success = 1
            """
            
            attempt_rows = self.DatabaseService.ExecuteQuery(attempt_query, (TranscodeAttemptId,))
            
            if not attempt_rows:
                LoggingService.LogError(f"TranscodeAttempt {TranscodeAttemptId} not found or not successful", "DatabaseManager", "CreateQualityTestingJob")
                return 0
            
            attempt = dict(attempt_rows[0])
            
            # Create quality testing queue item
            insert_query = """
                INSERT INTO QualityTestingQueue (
                    TranscodeAttemptId, OriginalFilePath, TranscodedFilePath, FileName,
                    Status, Priority, DateAdded, QualityThreshold, StrategyType
                ) VALUES (?, ?, ?, ?, 'Pending', 50, datetime('now', 'localtime'), 90.0, 'Single')
            """
            
            # Extract file paths and name
            transcoded_path = attempt['FilePath']
            original_path = transcoded_path.replace('.transcoded', '')  # Assume original is without .transcoded
            file_name = os.path.basename(transcoded_path)
            
            result = self.DatabaseService.ExecuteNonQuery(insert_query, (
                TranscodeAttemptId, original_path, transcoded_path, file_name
            ))
            
            if result > 0:
                LoggingService.LogInfo(f"Created quality testing job for TranscodeAttempt {TranscodeAttemptId}", "DatabaseManager", "CreateQualityTestingJob")
                return result
            else:
                LoggingService.LogError(f"Failed to create quality testing job for TranscodeAttempt {TranscodeAttemptId}", "DatabaseManager", "CreateQualityTestingJob")
                return 0
                
        except Exception as e:
            LoggingService.LogException("Exception creating quality testing job", e, "DatabaseManager", "CreateQualityTestingJob")
            return 0
    
    def UpdateTranscodeAttemptVMAF(self, TranscodeAttemptId: int, VMAFScore: float) -> bool:
        """Update VMAF score for a transcode attempt."""
        try:
            LoggingService.LogFunctionEntry("UpdateTranscodeAttemptVMAF", "DatabaseManager", TranscodeAttemptId, VMAFScore)
            
            query = "UPDATE TranscodeAttempts SET VMAF = ? WHERE Id = ?"
            result = self.DatabaseService.ExecuteNonQuery(query, (VMAFScore, TranscodeAttemptId))
            
            if result > 0:
                LoggingService.LogInfo(f"Updated VMAF score for TranscodeAttempt {TranscodeAttemptId}: {VMAFScore}", "DatabaseManager", "UpdateTranscodeAttemptVMAF")
                return True
            else:
                LoggingService.LogError(f"Failed to update VMAF score for TranscodeAttempt {TranscodeAttemptId}", "DatabaseManager", "UpdateTranscodeAttemptVMAF")
                return False
                
        except Exception as e:
            LoggingService.LogException("Exception updating transcode attempt VMAF", e, "DatabaseManager", "UpdateTranscodeAttemptVMAF")
            return False
    
    def MarkQualityTestCompleted(self, TranscodeAttemptId: int) -> bool:
        """Mark quality test as completed for a transcode attempt."""
        try:
            LoggingService.LogFunctionEntry("MarkQualityTestCompleted", "DatabaseManager", TranscodeAttemptId)
            
            query = "UPDATE TranscodeAttempts SET QualityTestCompleted = 1 WHERE Id = ?"
            result = self.DatabaseService.ExecuteNonQuery(query, (TranscodeAttemptId,))
            
            if result > 0:
                LoggingService.LogInfo(f"Marked quality test as completed for TranscodeAttempt {TranscodeAttemptId}", "DatabaseManager", "MarkQualityTestCompleted")
                return True
            else:
                LoggingService.LogError(f"Failed to mark quality test as completed for TranscodeAttempt {TranscodeAttemptId}", "DatabaseManager", "MarkQualityTestCompleted")
                return False
                
        except Exception as e:
            LoggingService.LogException("Exception marking quality test as completed", e, "DatabaseManager", "MarkQualityTestCompleted")
            return False
    
    def GetQualityTestingJob(self, job_id: int) -> Optional[Dict[str, Any]]:
        """Get a quality testing job by ID"""
        try:
            LoggingService.LogInfo(f"Retrieving quality testing job {job_id}", "DatabaseManager", "GetQualityTestingJob")
            
            query = """
                SELECT Id, TranscodeAttemptId, OriginalFilePath, TranscodedFilePath, LocalSourcePath,
                       DateAdded, DateStarted, DateCompleted
                FROM QualityTestingQueue 
                WHERE Id = ?
            """
            
            rows = self.DatabaseService.ExecuteQuery(query, (job_id,))
            
            if rows:
                LoggingService.LogInfo(f"Successfully retrieved quality testing job {job_id}", "DatabaseManager", "GetQualityTestingJob")
                return dict(rows[0])
            else:
                LoggingService.LogWarning(f"Quality testing job {job_id} not found", "DatabaseManager", "GetQualityTestingJob")
                return None
            
        except Exception as e:
            LoggingService.LogException(f"Critical error getting quality testing job {job_id}", e, "DatabaseManager", "GetQualityTestingJob")
            return None
    
    # Note: SaveQualityTestingQueueItem method removed
    # because QualityTestingQueue no longer has Status, QualityScore, or Results columns
    # Status tracking is now handled in QualityTestResults table
    
    def SaveQualityTestProgress(self, transcode_attempt_id: int, progress_data: Dict[str, Any]) -> bool:
        """Save quality test progress - updates existing record or creates new one"""
        try:
            # First, check if a record exists for this transcode attempt
            check_query = "SELECT Id FROM QualityTestProgress WHERE TranscodeAttemptId = ?"
            existing_records = self.DatabaseService.ExecuteQuery(check_query, (transcode_attempt_id,))
            
            if existing_records:
                # Update existing record
                query = """
                    UPDATE QualityTestProgress SET
                        Status = ?, ProgressPercentage = ?, CurrentStep = ?, 
                        UpdatedAt = datetime('now', 'localtime'), CurrentTime = ?, CurrentFrame = ?, 
                        ProcessingSpeed = ?, ETA = ?
                    WHERE TranscodeAttemptId = ?
                """
                
                parameters = (
                    progress_data.get('Status', 'Running'),
                    progress_data.get('ProgressPercentage', 0),
                    progress_data.get('CurrentStep', 'Processing'),
                    progress_data.get('CurrentTime'),
                    progress_data.get('CurrentFrame', 0),
                    progress_data.get('ProcessingSpeed'),
                    progress_data.get('ETA'),
                    transcode_attempt_id
                )
            else:
                # Insert new record
                query = """
                    INSERT INTO QualityTestProgress 
                    (TranscodeAttemptId, Status, ProgressPercentage, CurrentStep, 
                     StartTime, UpdatedAt, CreatedAt, CurrentTime, CurrentFrame, 
                     ProcessingSpeed, ETA)
                    VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'), datetime('now', 'localtime'),
                            ?, ?, ?, ?)
                """
                
                parameters = (
                    transcode_attempt_id,
                    progress_data.get('Status', 'Running'),
                    progress_data.get('ProgressPercentage', 0),
                    progress_data.get('CurrentStep', 'Processing'),
                    progress_data.get('StartTime'),
                    progress_data.get('CurrentTime'),
                    progress_data.get('CurrentFrame', 0),
                    progress_data.get('ProcessingSpeed'),
                    progress_data.get('ETA')
                )
            
            rows_affected = self.DatabaseService.ExecuteNonQuery(query, parameters)
            return rows_affected > 0
            
        except Exception as e:
            LoggingService.LogException("Exception saving quality test progress", e, "DatabaseManager", "SaveQualityTestProgress")
            return False
    
    def CreateInitialQualityTestResult(self, JobId: int, JobDetails: dict, FFmpegCommand: str) -> int:
        """Create initial QualityTestResults record before test starts."""
        try:
            LoggingService.LogFunctionEntry("CreateInitialQualityTestResult", "DatabaseManager", JobId)
            
            TranscodeAttemptId = JobDetails.get('TranscodeAttemptId', 0)
            if not TranscodeAttemptId:
                LoggingService.LogError("TranscodeAttemptId not provided in JobDetails", "DatabaseManager", "CreateInitialQualityTestResult")
                return 0
            
            # Get ProfileName and ProfileId
            ProfileQuery = "SELECT ta.ProfileName FROM TranscodeAttempts ta WHERE ta.Id = ?"
            ProfileResults = self.DatabaseService.ExecuteQuery(ProfileQuery, (TranscodeAttemptId,))
            ProfileName = ProfileResults[0]['ProfileName'] if ProfileResults else 'Unknown'
            
            ProfileIdQuery = "SELECT Id FROM Profiles WHERE ProfileName = ?"
            ProfileIdResults = self.DatabaseService.ExecuteQuery(ProfileIdQuery, (ProfileName,))
            ProfileId = ProfileIdResults[0]['Id'] if ProfileIdResults else 0
            
            # Get file size
            FileSize = 0
            if JobDetails.get('TranscodedFilePath') and os.path.exists(JobDetails['TranscodedFilePath']):
                FileSize = os.path.getsize(JobDetails['TranscodedFilePath'])
                LoggingService.LogInfo(f"File size for {JobDetails['TranscodedFilePath']}: {FileSize} bytes", "DatabaseManager", "CreateInitialQualityTestResult")
            else:
                LoggingService.LogWarning(f"TranscodedFilePath not found or file doesn't exist: {JobDetails.get('TranscodedFilePath')}", "DatabaseManager", "CreateInitialQualityTestResult")
            
            # Insert with NULL values for fields we don't have yet
            Query = """
                INSERT INTO QualityTestResults 
                (TranscodeAttemptId, TestDuration, PassesThreshold, Rank, ErrorMessage, DateTested, FFmpegCommand, Status, VMAFScore)
                VALUES (?, NULL, NULL, NULL, NULL, datetime('now', 'localtime'), ?, 'Running', NULL)
            """
            
            Parameters = (TranscodeAttemptId, FFmpegCommand)
            
            try:
                RowsAffected = self.DatabaseService.ExecuteNonQuery(Query, Parameters)
                
                # Get the ID of the inserted record using lastrowid (more reliable than rowcount for INSERTs)
                ResultId = self.DatabaseService.GetLastInsertId()
                
                if ResultId > 0:
                    LoggingService.LogInfo(f"Successfully created initial quality test result record {ResultId} for job {JobId}", "DatabaseManager", "CreateInitialQualityTestResult")
                    return ResultId
                else:
                    LoggingService.LogError(
                        f"INSERT failed - no record ID returned. Query: {Query}, Params: {Parameters}, ParamCount: {len(Parameters)}, RowCount: {RowsAffected}",
                        "DatabaseManager", "CreateInitialQualityTestResult"
                    )
                    return 0
            except Exception as e:
                LoggingService.LogException(
                    f"Database error during INSERT. Query: {Query}, Params: {Parameters}, ParamCount: {len(Parameters)}",
                    e, "DatabaseManager", "CreateInitialQualityTestResult"
                )
                return 0
            
        except Exception as e:
            LoggingService.LogException("Exception creating initial quality test result", e, "DatabaseManager", "CreateInitialQualityTestResult")
            return 0

    def StoreQualityTestResult(self, JobId: int, JobDetails: dict, VMAFScore: float, ErrorMessage: str = None, TestDuration: float = 0.0, FFmpegCommand: str = None) -> bool:
        """Store quality test result in QualityTestResults table."""
        try:
            LoggingService.LogFunctionEntry("StoreQualityTestResult", "DatabaseManager", JobId, VMAFScore)
            
            TranscodeAttemptId = JobDetails.get('TranscodeAttemptId', 0)
            if not TranscodeAttemptId:
                LoggingService.LogError("TranscodeAttemptId not provided in JobDetails", "DatabaseManager", "StoreQualityTestResult")
                return False
            
            # Get ProfileName from TranscodeAttempt, then get ProfileId from Profiles table
            ProfileQuery = """
                SELECT ta.ProfileName
                FROM TranscodeAttempts ta
                WHERE ta.Id = ?
            """
            ProfileResults = self.DatabaseService.ExecuteQuery(ProfileQuery, (TranscodeAttemptId,))
            
            if not ProfileResults:
                LoggingService.LogError(f"TranscodeAttempt {TranscodeAttemptId} not found", "DatabaseManager", "StoreQualityTestResult")
                return False
            
            ProfileName = ProfileResults[0]['ProfileName'] if ProfileResults[0]['ProfileName'] else 'Unknown'
            
            # Get ProfileId from Profiles table using ProfileName
            ProfileIdQuery = """
                SELECT Id FROM Profiles WHERE ProfileName = ?
            """
            ProfileIdResults = self.DatabaseService.ExecuteQuery(ProfileIdQuery, (ProfileName,))
            ProfileId = ProfileIdResults[0]['Id'] if ProfileIdResults else 0
            
            # Get file size
            file_size = 0
            if JobDetails.get('TranscodedFilePath') and os.path.exists(JobDetails['TranscodedFilePath']):
                file_size = os.path.getsize(JobDetails['TranscodedFilePath'])
                LoggingService.LogInfo(f"File size for {JobDetails['TranscodedFilePath']}: {file_size} bytes", "DatabaseManager", "StoreQualityTestResult")
            else:
                LoggingService.LogWarning(f"TranscodedFilePath not found or file doesn't exist: {JobDetails.get('TranscodedFilePath')}", "DatabaseManager", "StoreQualityTestResult")
            
            query = """
                INSERT INTO QualityTestResults 
                (TranscodeAttemptId, TestDuration, PassesThreshold, Rank, ErrorMessage, DateTested, FFmpegCommand, Status, VMAFScore)
                VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'), ?, 'Success', ?)
            """
            
            parameters = (
                TranscodeAttemptId,
                TestDuration,  # TestDuration - actual duration from FFmpeg process
                VMAFScore >= 90.0,  # PassesThreshold - assuming 90+ is good
                1,  # Rank - could be calculated based on other results
                ErrorMessage,  # ErrorMessage - None for success, error text for failures
                FFmpegCommand,  # Add the FFmpeg command
                VMAFScore
            )
            
            try:
                rows_affected = self.DatabaseService.ExecuteNonQuery(query, parameters)
                if rows_affected > 0:
                    LoggingService.LogInfo(f"Successfully stored quality test result for job {JobId}, VMAF score: {VMAFScore}", "DatabaseManager", "StoreQualityTestResult")
                    return True
                else:
                    LoggingService.LogError(
                        f"INSERT returned 0 rows. Query: {query}, Params: {parameters}, ParamCount: {len(parameters)}",
                        "DatabaseManager", "StoreQualityTestResult"
                    )
                    return False
            except Exception as e:
                LoggingService.LogException(
                    f"Database error during INSERT. Query: {query}, Params: {parameters}, ParamCount: {len(parameters)}",
                    e, "DatabaseManager", "StoreQualityTestResult"
                )
                return False
            
        except Exception as e:
            LoggingService.LogException("Exception storing quality test result", e, "DatabaseManager", "StoreQualityTestResult")
            return False
    
    def RemoveFromQualityTestQueue(self, JobId: int) -> bool:
        """Remove completed job from QualityTestingQueue (revolving door)."""
        try:
            query = "DELETE FROM QualityTestingQueue WHERE Id = ?"
            rows_affected = self.DatabaseService.ExecuteNonQuery(query, (JobId,))
            if rows_affected > 0:
                LoggingService.LogInfo(f"Successfully removed job {JobId} from quality test queue", "DatabaseManager", "RemoveFromQualityTestQueue")
                return True
            else:
                LoggingService.LogError(f"Failed to remove job {JobId} from quality test queue - no rows affected", "DatabaseManager", "RemoveFromQualityTestQueue")
                return False
            
        except Exception as e:
            LoggingService.LogException("Exception removing from quality test queue", e, "DatabaseManager", "RemoveFromQualityTestQueue")
            return False
    
    def UpdateTranscodeAttemptVMAF(self, transcode_attempt_id: int, vmaf_score: float) -> bool:
        """Update TranscodeAttempts with VMAF score"""
        try:
            query = """
                UPDATE TranscodeAttempts 
                SET VMAF = ?
                WHERE Id = ?
            """
            
            rows_affected = self.DatabaseService.ExecuteNonQuery(query, (vmaf_score, transcode_attempt_id))
            return rows_affected > 0
            
        except Exception as e:
            LoggingService.LogException("Exception updating TranscodeAttempt VMAF", e, "DatabaseManager", "UpdateTranscodeAttemptVMAF")
            return False
    
    def MarkQualityTestCompleted(self, transcode_attempt_id: int) -> bool:
        """Mark quality test as completed in TranscodeAttempts"""
        try:
            query = """
                UPDATE TranscodeAttempts 
                SET QualityTestCompleted = 1
                WHERE Id = ?
            """
            
            rows_affected = self.DatabaseService.ExecuteNonQuery(query, (transcode_attempt_id,))
            return rows_affected > 0
            
        except Exception as e:
            LoggingService.LogException("Exception marking quality test completed", e, "DatabaseManager", "MarkQualityTestCompleted")
            return False
    
    def SkipQualityTest(self, transcode_attempt_id: int) -> bool:
        """Skip quality test for a transcode attempt"""
        try:
            query = """
                UPDATE TranscodeAttempts 
                SET QualityTestSkipped = 1, QualityTestCompleted = 1
                WHERE Id = ?
            """
            
            rows_affected = self.DatabaseService.ExecuteNonQuery(query, (transcode_attempt_id,))
            return rows_affected > 0
            
        except Exception as e:
            LoggingService.LogException("Exception skipping quality test", e, "DatabaseManager", "SkipQualityTest")
            return False
    
    
    def UpdateActiveJobThreadId(self, job_id: int, thread_id: int) -> bool:
        """Update active job with thread ID"""
        try:
            query = """
                UPDATE ActiveJobs 
                SET ThreadId = ?, UpdatedAt = datetime('now', 'localtime')
                WHERE Id = ?
            """
            
            rows_affected = self.DatabaseService.ExecuteNonQuery(query, (thread_id, job_id))
            return rows_affected > 0
            
        except Exception as e:
            LoggingService.LogException("Exception updating active job thread ID", e, "DatabaseManager", "UpdateActiveJobThreadId")
            return False
    
    def CompleteActiveJob(self, job_id: int, success: bool = True, error_message: Optional[str] = None) -> bool:
        """Complete an active job and log the result"""
        try:
            # Get job details before deletion
            get_job_query = """
                SELECT ServiceName, JobType, QueueId, ProcessId, ThreadId, StartedAt
                FROM ActiveJobs WHERE Id = ?
            """
            job_rows = self.DatabaseService.ExecuteQuery(get_job_query, (job_id,))
            
            if not job_rows:
                return False
            
            job = job_rows[0]
            
            # Log the result
            if success:
                LoggingService.LogInfo(f"Job completed successfully: {job['ServiceName']} {job['JobType']} QueueId={job['QueueId']}", 
                             "DatabaseManager", "CompleteActiveJob")
            else:
                error_msg = error_message or "Job failed"
                LoggingService.LogError(f"Job failed: {job['ServiceName']} {job['JobType']} QueueId={job['QueueId']} - {error_msg}", 
                             "DatabaseManager", "CompleteActiveJob")
            
            # Delete from ActiveJobs
            delete_query = "DELETE FROM ActiveJobs WHERE Id = ?"
            rows_affected = self.DatabaseService.ExecuteNonQuery(delete_query, (job_id,))
            
            if rows_affected > 0:
                LoggingService.LogInfo(f"Successfully removed active job {job_id} from ActiveJobs table", "DatabaseManager", "CompleteActiveJob")
                return True
            else:
                LoggingService.LogError(f"Failed to remove active job {job_id} from ActiveJobs table - no rows affected", "DatabaseManager", "CompleteActiveJob")
                return False
            
        except Exception as e:
            LoggingService.LogException("Exception completing active job", e, "DatabaseManager", "CompleteActiveJob")
            return False
    
    def GetActiveJobByQueueId(self, service_name: str, queue_id: int) -> Optional[Dict[str, Any]]:
        """Get active job by service and queue ID"""
        try:
            query = """
                SELECT Id, ServiceName, JobType, QueueId, ProcessId, ThreadId, 
                       StartedAt, Status, CreatedAt, UpdatedAt
                FROM ActiveJobs 
                WHERE ServiceName = ? AND QueueId = ?
            """
            
            rows = self.DatabaseService.ExecuteQuery(query, (service_name, queue_id))
            
            if rows:
                return dict(rows[0])
            
            return None
            
        except Exception as e:
            LoggingService.LogException("Exception getting active job by queue ID", e, "DatabaseManager", "GetActiveJobByQueueId")
            return None
    
    def GetActiveJobsByService(self, service_name: str) -> List[Dict[str, Any]]:
        """Get all active jobs for a service"""
        try:
            query = """
                SELECT Id, ServiceName, JobType, QueueId, ProcessId, ThreadId, 
                       StartedAt, Status, CreatedAt, UpdatedAt
                FROM ActiveJobs 
                WHERE ServiceName = ?
            """
            
            rows = self.DatabaseService.ExecuteQuery(query, (service_name,))
            return [dict(row) for row in rows]
            
        except Exception as e:
            LoggingService.LogException("Exception getting active jobs by service", e, "DatabaseManager", "GetActiveJobsByService")
            return []
    
    def GetAllActiveJobs(self) -> List[Dict[str, Any]]:
        """Get all active jobs"""
        try:
            query = """
                SELECT Id, ServiceName, JobType, QueueId, ProcessId, ThreadId, 
                       StartedAt, Status, CreatedAt, UpdatedAt
                FROM ActiveJobs
            """
            
            rows = self.DatabaseService.ExecuteQuery(query)
            return [dict(row) for row in rows]
            
        except Exception as e:
            LoggingService.LogException("Exception getting all active jobs", e, "DatabaseManager", "GetAllActiveJobs")
            return []
    
    def CancelActiveJob(self, job_id: int) -> bool:
        """Cancel a specific active job"""
        try:
            # Get job details
            get_job_query = "SELECT ServiceName, JobType, QueueId FROM ActiveJobs WHERE Id = ?"
            job_rows = self.DatabaseService.ExecuteNonQuery(get_job_query, (job_id,))
            
            if not job_rows:
                return False
            
            # Log cancellation
            self.LogError(f"Job cancelled: {job_rows[0]['ServiceName']} {job_rows[0]['JobType']} QueueId={job_rows[0]['QueueId']}", 
                         "DatabaseManager", "CancelActiveJob")
            
            # Delete from ActiveJobs
            delete_query = "DELETE FROM ActiveJobs WHERE Id = ?"
            rows_affected = self.DatabaseService.ExecuteNonQuery(delete_query, (job_id,))
            
            return rows_affected > 0
            
        except Exception as e:
            LoggingService.LogException("Exception cancelling active job", e, "DatabaseManager", "CancelActiveJob")
            return False
    
    def GetMaxConcurrentJobs(self) -> int:
        """Get the maximum concurrent jobs limit from ServiceStatus."""
        try:
            query = "SELECT MaxConcurrentJobs FROM ServiceStatus WHERE ServiceName = 'QualityTestingService'"
            result = self.DatabaseService.ExecuteQuery(query)
            
            if result and len(result) > 0:
                return result[0][0] or 1  # Default to 1 if not set
            
            return 1  # Default value
            
        except Exception as e:
            LoggingService.LogException("Exception getting max concurrent jobs", e, "DatabaseManager", "GetMaxConcurrentJobs")
            return 1
    
    def CancelActiveJobs(self, service_name: str) -> bool:
        """Cancel all active jobs for a specific service."""
        try:
            # Get all active jobs for the service
            get_jobs_query = "SELECT Id, JobType, QueueId FROM ActiveJobs WHERE ServiceName = ? AND Status = 'Running'"
            jobs = self.DatabaseService.ExecuteQuery(get_jobs_query, (service_name,))
            
            if not jobs:
                return True  # No active jobs to cancel
            
            # Log cancellation for each job
            for job in jobs:
                self.LogError(f"Cancelling job: {service_name} {job[1]} QueueId={job[2]}", 
                             "DatabaseManager", "CancelActiveJobs")
            
            # Delete all active jobs for the service
            delete_query = "DELETE FROM ActiveJobs WHERE ServiceName = ? AND Status = 'Running'"
            rows_affected = self.DatabaseService.ExecuteNonQuery(delete_query, (service_name,))
            
            return rows_affected >= 0  # Return True even if no rows affected
            
        except Exception as e:
            LoggingService.LogException("Exception cancelling active jobs", e, "DatabaseManager", "CancelActiveJobs")
            return False
    
    # Simple QualityTest Methods
    def GetQualityTestJob(self, JobId: int) -> dict:
        """Get a quality test job by ID"""
        try:
            query = """SELECT Id, TranscodeAttemptId, OriginalFilePath, LocalSourcePath, TranscodedFilePath, DateAdded, DateStarted, DateCompleted 
                       FROM QualityTestingQueue WHERE Id = ?"""
            rows = self.DatabaseService.ExecuteQuery(query, (JobId,))
            
            if rows:
                row = rows[0]
                return {
                    "Id": row["Id"],
                    "TranscodeAttemptId": row["TranscodeAttemptId"],
                    "OriginalFilePath": row["OriginalFilePath"],
                    "LocalSourcePath": row["LocalSourcePath"],
                    "TranscodedFilePath": row["TranscodedFilePath"],
                    "DateAdded": row["DateAdded"],
                    "DateStarted": row["DateStarted"],
                    "DateCompleted": row["DateCompleted"]
                }
            return None
            
        except Exception as e:
            LoggingService.LogException("Exception getting quality test job", e, "DatabaseManager", "GetQualityTestJob")
            return None
    
    def GetQualityTestQueue(self) -> list:
        """Get all quality test jobs in queue ordered by priority and date"""
        try:
            query = """
                SELECT Id, TranscodeAttemptId, OriginalFilePath, TranscodedFilePath, LocalSourcePath,
                       DateAdded, DateStarted, DateCompleted
                FROM QualityTestingQueue 
                ORDER BY DateAdded ASC
            """
            rows = self.DatabaseService.ExecuteQuery(query)
            
            jobs = []
            for row in rows:
                jobs.append({
                    "Id": row["Id"],
                    "TranscodeAttemptId": row["TranscodeAttemptId"],
                    "OriginalFilePath": row["OriginalFilePath"],
                    "TranscodedFilePath": row["TranscodedFilePath"],
                    "LocalSourcePath": row["LocalSourcePath"],
                    "DateAdded": row["DateAdded"],
                    "DateStarted": row["DateStarted"],
                    "DateCompleted": row["DateCompleted"]
                })
            return jobs
            
        except Exception as e:
            LoggingService.LogException("Exception getting quality test queue", e, "DatabaseManager", "GetQualityTestQueue")
            return []
    
    # Note: UpdateQualityTestStatus and ResetQualityTestJobForRetry methods removed
    # because QualityTestingQueue no longer has Status, VMAFScore, RetryCount, or ErrorMessage columns
    # Status tracking is now handled in QualityTestResults table
    
    def GetQualityTestResults(self, Limit: int = 10) -> list:
        """Get recent quality test results from QualityTestResults table joined with TranscodeAttempts"""
        try:
            query = """
                SELECT 
                    qtr.Id, qtr.TranscodeAttemptId, qtr.VMAFScore, 
                    qtr.TestDuration, qtr.PassesThreshold, qtr.Rank, qtr.ErrorMessage, qtr.DateTested,
                    qtr.FFmpegCommand, qtr.Status,
                    ta.ProfileName, ta.FilePath, ta.OldSizeBytes, ta.NewSizeBytes, ta.SizeReductionBytes, 
                    ta.SizeReductionPercent, ta.TranscodeDurationSeconds, ta.ProfileName as TranscodeProfileName,
                    ta.Quality, ta.AttemptDate, ta.NewSizeBytes as FileSize, ta.FfpmpegCommand
                FROM QualityTestResults qtr
                LEFT JOIN TranscodeAttempts ta ON qtr.TranscodeAttemptId = ta.Id
                ORDER BY qtr.DateTested DESC 
                LIMIT ?
            """
            rows = self.DatabaseService.ExecuteQuery(query, (Limit,))
            
            results = []
            for row in rows:
                # Parse FFmpeg command to get transcoded file path
                TranscodedFilePath = None
                TranscodedFileName = None
                if row["FfpmpegCommand"] is not None and row["FfpmpegCommand"] != "":
                    _, OutputPath = self.ParseFFmpegCommand(row["FfpmpegCommand"])
                    if OutputPath:
                        TranscodedFilePath = OutputPath
                        # Extract just the filename from the full path
                        import os
                        TranscodedFileName = os.path.basename(OutputPath)
                
                results.append({
                    "Id": row["Id"],
                    "TranscodeAttemptId": row["TranscodeAttemptId"],
                    "VMAFScore": row["VMAFScore"],
                    "ProfileName": row["ProfileName"],
                    "FileSize": row["FileSize"],
                    "TestDuration": row["TestDuration"],
                    "PassesThreshold": row["PassesThreshold"],
                    "Rank": row["Rank"],
                    "ErrorMessage": row["ErrorMessage"],
                    "DateTested": row["DateTested"],
                    "FFmpegCommand": row["FFmpegCommand"],
                    "Status": row["Status"],
                    "FilePath": row["FilePath"],
                    "TranscodedFilePath": TranscodedFilePath,
                    "TranscodedFileName": TranscodedFileName,
                    "OldSizeBytes": row["OldSizeBytes"],
                    "NewSizeBytes": row["NewSizeBytes"],
                    "SizeReductionBytes": row["SizeReductionBytes"],
                    "SizeReductionPercent": row["SizeReductionPercent"],
                    "TranscodeDurationSeconds": row["TranscodeDurationSeconds"],
                    "Quality": row["Quality"],
                    "TranscodeProfileName": row["TranscodeProfileName"],
                    "AttemptDate": row["AttemptDate"],
                    "Success": row["PassesThreshold"] and not row["ErrorMessage"]
                })
            return results
            
        except Exception as e:
            LoggingService.LogException("Exception getting quality test results", e, "DatabaseManager", "GetQualityTestResults")
            return []
    
    def GetRunningQualityTestProgress(self) -> dict:
        """Get running quality test progress from QualityTestProgress table with file information"""
        try:
            query = """
                SELECT 
                    qtp.Id,
                    qtp.TranscodeAttemptId,
                    qtp.Status,
                    qtp.ProgressPercentage,
                    qtp.CurrentStep,
                    qtp.CurrentFrame,
                    qtp.CurrentTime,
                    qtp.ProcessingSpeed,
                    qtp.ETA, 
                    qtp.StartTime, 
                    qtp.UpdatedAt,
                    qtq.OriginalFilePath,
                    qtq.TranscodedFilePath,
                    qtq.LocalSourcePath
                FROM QualityTestProgress qtp
                LEFT JOIN QualityTestingQueue qtq ON qtp.TranscodeAttemptId = qtq.TranscodeAttemptId
                WHERE qtp.Status = 'Processing' 
                ORDER BY qtp.StartTime DESC 
                LIMIT 1
            """
            rows = self.DatabaseService.ExecuteQuery(query)
            
            if rows and len(rows) > 0:
                row = rows[0]
                return {
                    "Id": row["Id"],
                    "TranscodeAttemptId": row["TranscodeAttemptId"],
                    "Status": row["Status"],
                    "ProgressPercentage": row["ProgressPercentage"],
                    "CurrentStep": row["CurrentStep"],
                    "CurrentFrame": row["CurrentFrame"],
                    "CurrentTime": row["CurrentTime"],
                    "ProcessingSpeed": row["ProcessingSpeed"],
                    "ETA": row["ETA"],
                    "StartTime": row["StartTime"],
                    "UpdatedAt": row["UpdatedAt"],
                    "FileName": os.path.basename(row["OriginalFilePath"]) if row["OriginalFilePath"] else f"TranscodeAttempt_{row['TranscodeAttemptId']}",
                    "OriginalFilePath": row["OriginalFilePath"] or f"TranscodeAttempt_{row['TranscodeAttemptId']}",
                    "TranscodedFilePath": row["TranscodedFilePath"] or f"TranscodeAttempt_{row['TranscodeAttemptId']}",
                    "LocalSourcePath": row["LocalSourcePath"],
                    "EndTime": None,
                    "ErrorMessage": None
                }
            return None
            
        except Exception as e:
            LoggingService.LogException("Exception getting running quality test progress", e, "DatabaseManager", "GetRunningQualityTestProgress")
            return None
    
    def ClaimQualityTestJob(self) -> dict:
        """Atomically claim a pending quality test job to prevent race conditions."""
        try:
            # First, get the job to claim
            select_query = """
                SELECT Id, TranscodeAttemptId, OriginalFilePath, LocalSourcePath, TranscodedFilePath, DateAdded
                FROM QualityTestingQueue 
                WHERE DateStarted IS NULL 
                ORDER BY DateAdded ASC 
                LIMIT 1
            """
            
            jobs = self.DatabaseService.ExecuteQuery(select_query)
            if not jobs or len(jobs) == 0:
                LoggingService.LogDebug("No pending quality test jobs available to claim", "DatabaseManager", "ClaimQualityTestJob")
                return None
            
            job_to_claim = jobs[0]
            job_id = job_to_claim["Id"]
            
            # Now atomically claim the job
            update_query = """
                UPDATE QualityTestingQueue 
                SET DateStarted = datetime('now', 'localtime')
                WHERE Id = ? AND DateStarted IS NULL
            """
            
            rows_affected = self.DatabaseService.ExecuteNonQuery(update_query, (job_id,))
            
            if rows_affected > 0:
                LoggingService.LogInfo(f"Successfully claimed quality test job {job_id}", "DatabaseManager", "ClaimQualityTestJob")
                return {
                    "Id": job_to_claim["Id"],
                    "TranscodeAttemptId": job_to_claim["TranscodeAttemptId"],
                    "OriginalFilePath": job_to_claim["OriginalFilePath"],
                    "LocalSourcePath": job_to_claim["LocalSourcePath"],
                    "TranscodedFilePath": job_to_claim["TranscodedFilePath"],
                    "DateAdded": job_to_claim["DateAdded"]
                }
            else:
                LoggingService.LogDebug(f"Job {job_id} was already claimed by another worker", "DatabaseManager", "ClaimQualityTestJob")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception claiming quality test job", e, "DatabaseManager", "ClaimQualityTestJob")
            return None
    
    def CreateQualityTestQueueEntry(self, TranscodeAttemptId: int, OriginalFilePath: str, LocalSourcePath: str, TranscodedFilePath: str) -> Optional[int]:
        """Create a new quality test queue entry with all three file paths."""
        try:
            LoggingService.LogFunctionEntry("CreateQualityTestQueueEntry", "DatabaseManager", 
                                          TranscodeAttemptId, OriginalFilePath, LocalSourcePath, TranscodedFilePath)
            
            # Normalize paths to use single backslashes
            NormalizedOriginalFilePath = self.PrivateNormalizeFilePath(OriginalFilePath)
            NormalizedTranscodedFilePath = self.PrivateNormalizeFilePath(TranscodedFilePath)
            
            # Extract filename from normalized original path
            FileName = os.path.basename(NormalizedOriginalFilePath)
            
            # If LocalSourcePath is not provided or empty, construct it from SystemSettings
            if not LocalSourcePath or LocalSourcePath.strip() == "":
                TemporarySourceDir = self.GetSystemSetting("TemporarySourceDirectory")
                if TemporarySourceDir:
                    # Ensure path ends with backslash
                    if not TemporarySourceDir.endswith('\\'):
                        TemporarySourceDir += '\\'
                    NormalizedLocalSourcePath = self.PrivateNormalizeFilePath(TemporarySourceDir + FileName)
                    LoggingService.LogInfo(f"Constructed LocalSourcePath from SystemSettings: {NormalizedLocalSourcePath}", 
                                         "DatabaseManager", "CreateQualityTestQueueEntry")
                else:
                    LoggingService.LogError("TemporarySourceDirectory not found in SystemSettings, using OriginalFilePath as fallback", 
                                          "DatabaseManager", "CreateQualityTestQueueEntry")
                    NormalizedLocalSourcePath = NormalizedOriginalFilePath
            else:
                NormalizedLocalSourcePath = self.PrivateNormalizeFilePath(LocalSourcePath)
            
            query = """
                INSERT INTO QualityTestingQueue (
                    TranscodeAttemptId, OriginalFilePath, TranscodedFilePath, LocalSourcePath,
                    DateAdded, DateStarted, DateCompleted
                ) VALUES (?, ?, ?, ?, datetime('now', 'localtime'), ?, ?)
            """
            
            params = (
                TranscodeAttemptId,
                NormalizedOriginalFilePath,
                NormalizedTranscodedFilePath,
                NormalizedLocalSourcePath,
                None,  # DateStarted
                None   # DateCompleted
            )
            
            JobId = self.DatabaseService.ExecuteNonQuery(query, params)
            
            if JobId:
                LoggingService.LogInfo(f"Created quality test queue entry with ID {JobId} for TranscodeAttempt {TranscodeAttemptId}", 
                                     "DatabaseManager", "CreateQualityTestQueueEntry")
                return JobId
            else:
                LoggingService.LogError(f"Failed to create quality test queue entry for TranscodeAttempt {TranscodeAttemptId}", 
                                      "DatabaseManager", "CreateQualityTestQueueEntry")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception creating quality test queue entry", e, "DatabaseManager", "CreateQualityTestQueueEntry")
            return None
    
    def ParseFFmpegCommand(self, FfpmpegCommand: str) -> tuple:
        """
        Parse FFmpeg command to extract input and output file paths.
        
        Args:
            FfpmpegCommand: The full FFmpeg command string
            
        Returns:
            tuple: (InputFilePath, OutputFilePath) or (None, None) if parsing fails
        """
        try:
            import re
            
            if not FfpmpegCommand or FfpmpegCommand.strip() == "":
                LoggingService.LogWarning("Empty FFmpeg command provided", "DatabaseManager", "ParseFFmpegCommand")
                return None, None
            
            # Find input file path after -i flag
            InputMatch = re.search(r'-i\s+"([^"]+)"', FfpmpegCommand)
            InputPath = InputMatch.group(1) if InputMatch else None
            
            # Find output file path (last quoted string in the command)
            OutputMatches = re.findall(r'"([^"]+)"', FfpmpegCommand)
            OutputPath = OutputMatches[-1] if OutputMatches else None
            
            if InputPath and OutputPath:
                LoggingService.LogInfo(f"Successfully parsed FFmpeg command - Input: {InputPath}, Output: {OutputPath}", 
                                     "DatabaseManager", "ParseFFmpegCommand")
                return InputPath, OutputPath
            else:
                LoggingService.LogWarning(f"Could not parse FFmpeg command: {FfpmpegCommand}", 
                                        "DatabaseManager", "ParseFFmpegCommand")
                return None, None
            
        except Exception as e:
            LoggingService.LogException("Exception parsing FFmpeg command", e, "DatabaseManager", "ParseFFmpegCommand")
            return None, None
    
    def DeleteQualityTestRecordsByAttemptId(self, TranscodeAttemptId: int) -> bool:
        """
        Delete existing quality test records for a specific transcode attempt.
        
        Args:
            TranscodeAttemptId: The ID of the transcode attempt
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            LoggingService.LogFunctionEntry("DeleteQualityTestRecordsByAttemptId", "DatabaseManager", TranscodeAttemptId)
            
            # Delete from QualityTestingQueue
            QueueQuery = "DELETE FROM QualityTestingQueue WHERE TranscodeAttemptId = ?"
            QueueRowsAffected = self.DatabaseService.ExecuteNonQuery(QueueQuery, (TranscodeAttemptId,))
            
            # Delete from QualityTestProgress
            ProgressQuery = "DELETE FROM QualityTestProgress WHERE TranscodeAttemptId = ?"
            ProgressRowsAffected = self.DatabaseService.ExecuteNonQuery(ProgressQuery, (TranscodeAttemptId,))
            
            TotalRowsAffected = QueueRowsAffected + ProgressRowsAffected
            
            if TotalRowsAffected > 0:
                LoggingService.LogInfo(f"Deleted {TotalRowsAffected} quality test records for TranscodeAttempt {TranscodeAttemptId} "
                                     f"(Queue: {QueueRowsAffected}, Progress: {ProgressRowsAffected})", 
                                     "DatabaseManager", "DeleteQualityTestRecordsByAttemptId")
                return True
            else:
                LoggingService.LogInfo(f"No quality test records found for TranscodeAttempt {TranscodeAttemptId}", 
                                     "DatabaseManager", "DeleteQualityTestRecordsByAttemptId")
                return True  # Still return True as this is not an error condition
                
        except Exception as e:
            LoggingService.LogException("Exception deleting quality test records", e, "DatabaseManager", "DeleteQualityTestRecordsByAttemptId")
            return False
    
    def CreateTemporaryFilePath(self, TranscodeAttemptId: int, OriginalPath: str, LocalSourcePath: str) -> Optional[int]:
        """Create a new temporary file path record."""
        try:
            LoggingService.LogFunctionEntry("CreateTemporaryFilePath", "DatabaseManager", 
                                          TranscodeAttemptId, OriginalPath, LocalSourcePath)
            
            # Validate TranscodeAttemptId exists
            if not self.PrivateValidateTranscodeAttemptId(TranscodeAttemptId):
                LoggingService.LogError(f"Invalid TranscodeAttemptId: {TranscodeAttemptId}", "DatabaseManager", "CreateTemporaryFilePath")
                return None
            
            # Normalize paths to use single backslashes
            NormalizedOriginalPath = self.PrivateNormalizeFilePath(OriginalPath)
            NormalizedLocalSourcePath = self.PrivateNormalizeFilePath(LocalSourcePath)
            
            query = """
                INSERT INTO TemporaryFilePaths (
                    TranscodeAttemptId, OriginalPath, LocalSourcePath, CreatedDate
                ) VALUES (?, ?, ?, datetime('now', 'localtime'))
            """
            
            params = (TranscodeAttemptId, NormalizedOriginalPath, NormalizedLocalSourcePath)
            
            RecordId = self.DatabaseService.ExecuteNonQuery(query, params)
            
            if RecordId:
                LoggingService.LogInfo(f"Created temporary file path record with ID {RecordId} for TranscodeAttempt {TranscodeAttemptId}", 
                                     "DatabaseManager", "CreateTemporaryFilePath")
                self.PrivateLogTemporaryFilePathOperation("CREATE", TranscodeAttemptId, RecordId, "SUCCESS")
                return RecordId
            else:
                LoggingService.LogError(f"Failed to create temporary file path record for TranscodeAttempt {TranscodeAttemptId}", 
                                      "DatabaseManager", "CreateTemporaryFilePath")
                self.PrivateLogTemporaryFilePathOperation("CREATE", TranscodeAttemptId, None, "FAILED")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception creating temporary file path record", e, "DatabaseManager", "CreateTemporaryFilePath")
            self.PrivateLogTemporaryFilePathOperation("CREATE", TranscodeAttemptId, None, "EXCEPTION", str(e))
            return None
    
    def UpdateTemporaryFilePath(self, TranscodeAttemptId: int, LocalOutputPath: str) -> bool:
        """Update temporary file path record with local output path."""
        try:
            LoggingService.LogFunctionEntry("UpdateTemporaryFilePath", "DatabaseManager", 
                                          TranscodeAttemptId, LocalOutputPath)
            
            # Validate TranscodeAttemptId exists
            if not self.PrivateValidateTranscodeAttemptId(TranscodeAttemptId):
                LoggingService.LogError(f"Invalid TranscodeAttemptId: {TranscodeAttemptId}", "DatabaseManager", "UpdateTemporaryFilePath")
                return False
            
            # Normalize path to use single backslashes
            NormalizedLocalOutputPath = self.PrivateNormalizeFilePath(LocalOutputPath)
            
            query = """
                UPDATE TemporaryFilePaths 
                SET LocalOutputPath = ?
                WHERE TranscodeAttemptId = ?
            """
            
            params = (NormalizedLocalOutputPath, TranscodeAttemptId)
            
            RowsAffected = self.DatabaseService.ExecuteNonQuery(query, params)
            
            if RowsAffected > 0:
                LoggingService.LogInfo(f"Updated temporary file path record for TranscodeAttempt {TranscodeAttemptId} with LocalOutputPath: {LocalOutputPath}", 
                                     "DatabaseManager", "UpdateTemporaryFilePath")
                self.PrivateLogTemporaryFilePathOperation("UPDATE", TranscodeAttemptId, None, "SUCCESS")
                return True
            else:
                LoggingService.LogWarning(f"No temporary file path record found for TranscodeAttempt {TranscodeAttemptId}", 
                                        "DatabaseManager", "UpdateTemporaryFilePath")
                self.PrivateLogTemporaryFilePathOperation("UPDATE", TranscodeAttemptId, None, "NOT_FOUND")
                return False
                
        except Exception as e:
            LoggingService.LogException("Exception updating temporary file path record", e, "DatabaseManager", "UpdateTemporaryFilePath")
            self.PrivateLogTemporaryFilePathOperation("UPDATE", TranscodeAttemptId, None, "EXCEPTION", str(e))
            return False
    
    def GetTemporaryFilePath(self, TranscodeAttemptId: int) -> Optional[Dict[str, Any]]:
        """Get temporary file path record by TranscodeAttemptId."""
        try:
            LoggingService.LogFunctionEntry("GetTemporaryFilePath", "DatabaseManager", TranscodeAttemptId)
            
            query = """
                SELECT Id, TranscodeAttemptId, OriginalPath, LocalSourcePath, LocalOutputPath, CreatedDate
                FROM TemporaryFilePaths 
                WHERE TranscodeAttemptId = ?
            """
            
            results = self.DatabaseService.ExecuteQuery(query, (TranscodeAttemptId,))
            
            if results:
                Record = results[0]
                LoggingService.LogInfo(f"Retrieved temporary file path record for TranscodeAttempt {TranscodeAttemptId}", 
                                     "DatabaseManager", "GetTemporaryFilePath")
                self.PrivateLogTemporaryFilePathOperation("SELECT", TranscodeAttemptId, Record.get('Id'), "SUCCESS")
                return Record
            else:
                LoggingService.LogWarning(f"No temporary file path record found for TranscodeAttempt {TranscodeAttemptId}", 
                                        "DatabaseManager", "GetTemporaryFilePath")
                self.PrivateLogTemporaryFilePathOperation("SELECT", TranscodeAttemptId, None, "NOT_FOUND")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception getting temporary file path record", e, "DatabaseManager", "GetTemporaryFilePath")
            self.PrivateLogTemporaryFilePathOperation("SELECT", TranscodeAttemptId, None, "EXCEPTION", str(e))
            return None
    
    def DeleteTemporaryFilePath(self, TranscodeAttemptId: int) -> bool:
        """Delete temporary file path record by TranscodeAttemptId."""
        try:
            LoggingService.LogFunctionEntry("DeleteTemporaryFilePath", "DatabaseManager", TranscodeAttemptId)
            
            query = """
                DELETE FROM TemporaryFilePaths 
                WHERE TranscodeAttemptId = ?
            """
            
            RowsAffected = self.DatabaseService.ExecuteNonQuery(query, (TranscodeAttemptId,))
            
            if RowsAffected > 0:
                LoggingService.LogInfo(f"Deleted temporary file path record for TranscodeAttempt {TranscodeAttemptId}", 
                                     "DatabaseManager", "DeleteTemporaryFilePath")
                self.PrivateLogTemporaryFilePathOperation("DELETE", TranscodeAttemptId, None, "SUCCESS")
                return True
            else:
                LoggingService.LogWarning(f"No temporary file path record found to delete for TranscodeAttempt {TranscodeAttemptId}", 
                                        "DatabaseManager", "DeleteTemporaryFilePath")
                self.PrivateLogTemporaryFilePathOperation("DELETE", TranscodeAttemptId, None, "NOT_FOUND")
                return False
                
        except Exception as e:
            LoggingService.LogException("Exception deleting temporary file path record", e, "DatabaseManager", "DeleteTemporaryFilePath")
            self.PrivateLogTemporaryFilePathOperation("DELETE", TranscodeAttemptId, None, "EXCEPTION", str(e))
            return False
    
    def PrivateValidateTranscodeAttemptId(self, TranscodeAttemptId: int) -> bool:
        """Private method to validate TranscodeAttemptId exists."""
        try:
            query = "SELECT COUNT(*) as Count FROM TranscodeAttempts WHERE Id = ?"
            results = self.DatabaseService.ExecuteQuery(query, (TranscodeAttemptId,))
            return results[0]['Count'] > 0 if results else False
        except Exception as e:
            LoggingService.LogException("Exception validating TranscodeAttemptId", e, "DatabaseManager", "PrivateValidateTranscodeAttemptId")
            return False
    
    def PrivateLogTemporaryFilePathOperation(self, Operation: str, TranscodeAttemptId: int, RecordId: Optional[int], Status: str, ErrorMessage: str = None):
        """Private method to log temporary file path operations."""
        try:
            Message = f"TemporaryFilePath {Operation} - TranscodeAttemptId: {TranscodeAttemptId}"
            if RecordId:
                Message += f", RecordId: {RecordId}"
            Message += f", Status: {Status}"
            if ErrorMessage:
                Message += f", Error: {ErrorMessage}"
            
            LogLevel = "ERROR" if Status in ["FAILED", "EXCEPTION"] else "INFO"
            LoggingService.Log(LogLevel, Message, "DatabaseManager", "PrivateLogTemporaryFilePathOperation")
        except Exception as e:
            LoggingService.LogException("Exception logging temporary file path operation", e, "DatabaseManager", "PrivateLogTemporaryFilePathOperation")
    
    def GetSystemSetting(self, SettingKey: str) -> Optional[str]:
        """Get a system setting value by key."""
        try:
            LoggingService.LogFunctionEntry("GetSystemSetting", "DatabaseManager", SettingKey)
            
            query = "SELECT SettingValue FROM SystemSettings WHERE SettingKey = ?"
            results = self.DatabaseService.ExecuteQuery(query, (SettingKey,))
            
            if results:
                SettingValue = results[0]['SettingValue']
                LoggingService.LogInfo(f"Retrieved system setting '{SettingKey}': '{SettingValue}'", 
                                     "DatabaseManager", "GetSystemSetting")
                return SettingValue
            else:
                LoggingService.LogWarning(f"System setting not found: {SettingKey}", 
                                        "DatabaseManager", "GetSystemSetting")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception getting system setting", e, "DatabaseManager", "GetSystemSetting")
            return None

    def PrivateNormalizeFilePath(self, FilePath: str) -> str:
        """Private method to normalize file paths to use single backslashes."""
        try:
            if not FilePath:
                return FilePath

            # Replace double backslashes with single backslashes
            # This handles cases where paths might be escaped
            NormalizedPath = FilePath.replace('\\\\', '\\')

            # Log the normalization for debugging
            if NormalizedPath != FilePath:
                LoggingService.LogInfo(f"Normalized file path: '{FilePath}' -> '{NormalizedPath}'",
                                     "DatabaseManager", "PrivateNormalizeFilePath")

            return NormalizedPath

        except Exception as e:
            LoggingService.LogException("Exception normalizing file path", e, "DatabaseManager", "PrivateNormalizeFilePath")
            return FilePath
    
    # Crash Recovery Methods
    
    def GetActiveJobDetails(self, JobId: int) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific active job."""
        try:
            LoggingService.LogFunctionEntry("GetActiveJobDetails", "DatabaseManager", JobId)
            
            query = """
                SELECT Id, ServiceName, JobType, QueueId, ProcessId, ThreadId, 
                       StartedAt, Status, CreatedAt, UpdatedAt
                FROM ActiveJobs 
                WHERE Id = ?
            """
            
            rows = self.DatabaseService.ExecuteQuery(query, (JobId,))
            
            if rows:
                job_details = dict(rows[0])
                LoggingService.LogInfo(f"Retrieved active job details for ID {JobId}", "DatabaseManager", "GetActiveJobDetails")
                return job_details
            else:
                LoggingService.LogWarning(f"Active job not found: {JobId}", "DatabaseManager", "GetActiveJobDetails")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception getting active job details", e, "DatabaseManager", "GetActiveJobDetails")
            return None
    
    def DeleteActiveJob(self, JobId: int) -> bool:
        """Delete a specific active job record."""
        try:
            LoggingService.LogFunctionEntry("DeleteActiveJob", "DatabaseManager", JobId)
            
            query = "DELETE FROM ActiveJobs WHERE Id = ?"
            affected_rows = self.DatabaseService.ExecuteNonQuery(query, (JobId,))
            
            if affected_rows > 0:
                LoggingService.LogInfo(f"Deleted active job {JobId}", "DatabaseManager", "DeleteActiveJob")
                return True
            else:
                LoggingService.LogWarning(f"Active job {JobId} not found for deletion", "DatabaseManager", "DeleteActiveJob")
                return False
                
        except Exception as e:
            LoggingService.LogException("Exception deleting active job", e, "DatabaseManager", "DeleteActiveJob")
            return False
    
    def DeleteActiveJobsByService(self, ServiceName: str) -> int:
        """Delete all active jobs for a specific service. Returns count of deleted jobs."""
        try:
            LoggingService.LogFunctionEntry("DeleteActiveJobsByService", "DatabaseManager", ServiceName)
            
            query = "DELETE FROM ActiveJobs WHERE ServiceName = ?"
            affected_rows = self.DatabaseService.ExecuteNonQuery(query, (ServiceName,))
            
            LoggingService.LogInfo(f"Deleted {affected_rows} active jobs for service {ServiceName}", "DatabaseManager", "DeleteActiveJobsByService")
            return affected_rows
            
        except Exception as e:
            LoggingService.LogException("Exception deleting active jobs by service", e, "DatabaseManager", "DeleteActiveJobsByService")
            return 0
    
    def ResetQueueJobsToPending(self, QueueIds: List[int], QueueTable: str) -> int:
        """Reset multiple queue jobs to Pending status. Returns count of reset jobs."""
        try:
            LoggingService.LogFunctionEntry("ResetQueueJobsToPending", "DatabaseManager", QueueIds, QueueTable)
            
            if not QueueIds:
                return 0
            
            # Validate queue table name to prevent SQL injection
            valid_tables = ['TranscodeQueue', 'QualityTestingQueue']
            if QueueTable not in valid_tables:
                LoggingService.LogError(f"Invalid queue table name: {QueueTable}", "DatabaseManager", "ResetQueueJobsToPending")
                return 0
            
            # Reset status to Pending and clear DateStarted
            query = f"""
                UPDATE {QueueTable} 
                SET Status = 'Pending', DateStarted = NULL 
                WHERE Id IN ({','.join('?' * len(QueueIds))})
            """
            
            affected_rows = self.DatabaseService.ExecuteNonQuery(query, QueueIds)
            
            LoggingService.LogInfo(f"Reset {affected_rows} jobs to Pending in {QueueTable}", "DatabaseManager", "ResetQueueJobsToPending")
            return affected_rows
            
        except Exception as e:
            LoggingService.LogException("Exception resetting queue jobs to pending", e, "DatabaseManager", "ResetQueueJobsToPending")
            return 0
    
    def UpdateActiveJobProcessId(self, ActiveJobId: int, ProcessId: int) -> bool:
        """Update the ProcessId for an active job (for FFmpeg PID tracking)."""
        try:
            LoggingService.LogFunctionEntry("UpdateActiveJobProcessId", "DatabaseManager", ActiveJobId, ProcessId)
            
            query = "UPDATE ActiveJobs SET ProcessId = ?, UpdatedAt = datetime('now', 'localtime') WHERE Id = ?"
            affected_rows = self.DatabaseService.ExecuteNonQuery(query, (ProcessId, ActiveJobId))
            
            if affected_rows > 0:
                LoggingService.LogInfo(f"Updated ActiveJob {ActiveJobId} with ProcessId {ProcessId}", 
                                      "DatabaseManager", "UpdateActiveJobProcessId")
                return True
            else:
                LoggingService.LogWarning(f"No rows updated for ActiveJob {ActiveJobId}", 
                                         "DatabaseManager", "UpdateActiveJobProcessId")
                return False
                
        except Exception as e:
            LoggingService.LogException("Exception updating active job process ID", e, 
                                       "DatabaseManager", "UpdateActiveJobProcessId")
            return False
    
    def CreateQualityTestResult(self, TranscodeAttemptId: int, Status: str = "Running", TestDate: datetime = None) -> int:
        """Create a quality test result record at the start of testing."""
        try:
            LoggingService.LogFunctionEntry("CreateQualityTestResult", "DatabaseManager", TranscodeAttemptId, Status)
            
            from Models.QualityTestResultModel import QualityTestResultModel
            
            result = QualityTestResultModel(
                TranscodeAttemptId=TranscodeAttemptId,
                Status=Status,
                DateTested=TestDate or datetime.now(),
                VMAFScore=0.0 if Status == "Running" else None,  # Use 0.0 for running tests
                ErrorMessage=None
            )
            
            # Verify TranscodeAttemptId exists
            check_query = "SELECT Id FROM TranscodeAttempts WHERE Id = ?"
            check_result = self.DatabaseService.ExecuteQuery(check_query, (TranscodeAttemptId,))
            
            if not check_result:
                LoggingService.LogError(
                    f"TranscodeAttemptId {TranscodeAttemptId} does not exist in TranscodeAttempts table",
                    "DatabaseManager", "CreateQualityTestResult"
                )
                return 0
            
            # Insert into database with all required fields
            query = """
                INSERT INTO QualityTestResults 
                (TranscodeAttemptId, TestDuration, PassesThreshold, Rank, ErrorMessage, DateTested, FFmpegCommand, Status, VMAFScore)
                VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'), ?, ?, ?)
            """
            
            params = (
                result.TranscodeAttemptId,
                0.0,  # TestDuration
                False,  # PassesThreshold
                0,  # Rank
                result.ErrorMessage,
                # DateTested removed - using CURRENT_TIMESTAMP in SQL
                "",  # FFmpegCommand
                result.Status,
                result.VMAFScore
            )
            
            LoggingService.LogInfo(f"Inserting QualityTestResult with params: {params}", "DatabaseManager", "CreateQualityTestResult")
            
            try:
                affected_rows = self.DatabaseService.ExecuteNonQuery(query, params)
                
                # Get the ID of the inserted record using lastrowid (more reliable than rowcount for INSERTs)
                result_id = self.DatabaseService.GetLastInsertId()
                
                if result_id > 0:
                    LoggingService.LogInfo(f"Created QualityTestResult {result_id} for TranscodeAttempt {TranscodeAttemptId}", 
                                          "DatabaseManager", "CreateQualityTestResult")
                    return result_id
                else:
                    LoggingService.LogError(
                        f"INSERT failed - no record ID returned. Query: {query}, Params: {params}, ParamCount: {len(params)}, RowCount: {affected_rows}",
                        "DatabaseManager", "CreateQualityTestResult"
                    )
                    return 0
            except Exception as e:
                LoggingService.LogException(
                    f"Database error during INSERT. Query: {query}, Params: {params}, ParamCount: {len(params)}",
                    e, "DatabaseManager", "CreateQualityTestResult"
                )
                return 0
                
        except Exception as e:
            LoggingService.LogException("Error creating quality test result", e, 
                                       "DatabaseManager", "CreateQualityTestResult")
            return 0
    
    def UpdateQualityTestResultFailure(self, ResultId: int, ErrorMessage: str) -> bool:
        """Update a quality test result with failure details."""
        try:
            LoggingService.LogFunctionEntry("UpdateQualityTestResultFailure", "DatabaseManager", ResultId, ErrorMessage)
            
            query = "UPDATE QualityTestResults SET Status = 'Failed', ErrorMessage = ? WHERE Id = ?"
            affected_rows = self.DatabaseService.ExecuteNonQuery(query, (ErrorMessage, ResultId))
            
            if affected_rows > 0:
                LoggingService.LogInfo(f"Updated QualityTestResult {ResultId} with failure status", "DatabaseManager", "UpdateQualityTestResultFailure")
                return True
            else:
                LoggingService.LogWarning(f"No rows updated for QualityTestResult {ResultId}", 
                                         "DatabaseManager", "UpdateQualityTestResultFailure")
                return False
                
        except Exception as e:
            LoggingService.LogException("Error updating quality test failure", e, 
                                       "DatabaseManager", "UpdateQualityTestResultFailure")
            return False
    
    def DeleteQualityTestQueueItem(self, JobId: int) -> bool:
        """Delete a job from the quality testing queue."""
        try:
            LoggingService.LogFunctionEntry("DeleteQualityTestQueueItem", "DatabaseManager", JobId)
            
            query = "DELETE FROM QualityTestingQueue WHERE Id = ?"
            affected_rows = self.DatabaseService.ExecuteNonQuery(query, (JobId,))
            
            if affected_rows > 0:
                LoggingService.LogInfo(f"Deleted QualityTestingQueue item {JobId}", "DatabaseManager", "DeleteQualityTestQueueItem")
                return True
            else:
                LoggingService.LogWarning(f"No rows deleted for QualityTestingQueue item {JobId}", 
                                         "DatabaseManager", "DeleteQualityTestQueueItem")
                return False
                
        except Exception as e:
            LoggingService.LogException("Error deleting quality test queue item", e, 
                                       "DatabaseManager", "DeleteQualityTestQueueItem")
            return False
    
    def GetMissedQualityTests(self, Limit: int = 100) -> List[Dict[str, Any]]:
        """Get successful transcode attempts that need quality testing but don't have successful quality test results."""
        try:
            LoggingService.LogFunctionEntry("GetMissedQualityTests", "DatabaseManager", Limit)
            
            query = """
                SELECT ta.Id, ta.FilePath, ta.FfpmpegCommand
                FROM TranscodeAttempts ta
                WHERE ta.Success = 1
                  AND ta.QualityTestRequired = 1
                  AND ta.QualityTestCompleted = 0
                  AND ta.Id NOT IN (
                      SELECT TranscodeAttemptId 
                      FROM QualityTestResults 
                      WHERE TranscodeAttemptId IS NOT NULL
                        AND Status = 'Success'
                  )
                ORDER BY ta.AttemptDate DESC
                LIMIT ?
            """
            
            Rows = self.DatabaseService.ExecuteQuery(query, (Limit,))
            
            Results = []
            for Row in Rows:
                Results.append({
                    "Id": Row["Id"],
                    "FilePath": Row["FilePath"],
                    "FfpmpegCommand": Row["FfpmpegCommand"]
                })
            
            LoggingService.LogInfo(f"Found {len(Results)} missed quality tests", "DatabaseManager", "GetMissedQualityTests")
            return Results
            
        except Exception as e:
            LoggingService.LogException("Exception getting missed quality tests", e, "DatabaseManager", "GetMissedQualityTests")
            return []