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
# VMAF models removed - using QualityTesting models instead
from Models.QualityTestingQueueModel import QualityTestingQueueModel
from Models.QualityTestProgressModel import QualityTestProgressModel
from Models.QualityTestingStrategyModel import QualityTestingStrategyModel
from Models.QualityTestResultModel import QualityTestResultModel
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
                          Codec, Preset, FilmGrain, TenBitEncoding, YadifMode, YadifParity, YadifDeint 
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
                TenBitEncoding=bool(row['TenBitEncoding']) if row['TenBitEncoding'] is not None else False,
                YadifMode=row['YadifMode'] if row['YadifMode'] is not None else 1,
                YadifParity=row['YadifParity'] if row['YadifParity'] is not None else 1,
                YadifDeint=row['YadifDeint'] if row['YadifDeint'] is not None else 1
            )
            profiles.append(profile)
        
        return profiles
    
    def GetProfileById(self, ProfileId: int) -> Optional[TranscodeProfileModel]:
        """Get a specific profile by ID."""
        query = """SELECT Id, ProfileName, Description, CreatedDate, LastModified, 
                          Codec, Preset, FilmGrain, TenBitEncoding, YadifMode, YadifParity, YadifDeint 
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
            TenBitEncoding=bool(row['TenBitEncoding']) if row['TenBitEncoding'] is not None else False,
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
                                             Codec, Preset, FilmGrain, TenBitEncoding, YadifMode, YadifParity, YadifDeint)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    parameters = (Profile.ProfileName, Profile.Description, Profile.CreatedDate, Profile.LastModified,
                                 Profile.Codec, Profile.Preset, Profile.FilmGrain, Profile.TenBitEncoding, Profile.YadifMode, 
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
                            Codec = ?, Preset = ?, FilmGrain = ?, TenBitEncoding = ?, YadifMode = ?, YadifParity = ?, YadifDeint = ?
                        WHERE Id = ?
                    """
                    parameters = (Profile.ProfileName, Profile.Description, Profile.LastModified,
                                 Profile.Codec, Profile.Preset, Profile.FilmGrain, Profile.TenBitEncoding, Profile.YadifMode, 
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
                    SET SettingValue = ?, Description = ?, DataType = ?, LastModified = CURRENT_TIMESTAMP
                    WHERE SettingKey = ?
                """
                self.DatabaseService.ExecuteNonQuery(query, (SettingValue, Description, DataType, SettingKey))
            else:
                # Insert new setting
                query = """
                    INSERT INTO SystemSettings (SettingKey, SettingValue, Description, DataType, LastModified)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
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
                        TotalFrames = ?, AverageFPS = ?, LastProgressUpdate = ?
                    WHERE TranscodeAttemptId = ?
                """
                parameters = (CurrentPhase, ProgressPercent, CurrentFrame, CurrentFPS,
                             CurrentBitrate, CurrentTime, CurrentSpeed, ETA,
                             TotalFrames, AverageFPS, datetime.now(), TranscodeAttemptId)
                
                result = self.DatabaseService.ExecuteNonQuery(updateQuery, parameters)
                LoggingService.LogDebug(f"Updated progress record for attempt {TranscodeAttemptId}: {CurrentPhase} ({ProgressPercent}%) - Frame: {CurrentFrame}, FPS: {CurrentFPS}, ETA: {ETA}", "DatabaseManager", "SaveTranscodeProgress")
                return result
            else:
                # Insert new record
                insertQuery = """
                    INSERT INTO TranscodeProgress 
                    (TranscodeAttemptId, PassNumber, PassType, CurrentPhase, ProgressPercent, CurrentFrame, CurrentFPS, 
                     CurrentBitrate, CurrentTime, CurrentSpeed, ETA, TotalFrames, AverageFPS, LastProgressUpdate)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                parameters = (TranscodeAttemptId, 1, "Encoding", CurrentPhase, ProgressPercent, CurrentFrame, CurrentFPS,
                             CurrentBitrate, CurrentTime, CurrentSpeed, ETA, TotalFrames, AverageFPS, datetime.now())
                
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
                    UpdatedAt = CURRENT_TIMESTAMP
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
                    ServiceStatus.get('ServiceName')
                )
            else:
                # Insert new status
                query = """
                INSERT INTO ServiceStatus (
                    ServiceName, Status, HealthStatus, StartTime, LastHealthCheck,
                    UptimeSeconds, MemoryUsage, CPUUsage, DatabaseConnection, DiskSpace,
                    ErrorCount, MaxErrors, ActiveJobsCount, IsProcessing, ProcessId,
                    Version, ServiceType, CreatedAt, UpdatedAt
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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
                    ServiceStatus.get('ServiceType')
                )
            
            self.DatabaseService.ExecuteQuery(query, parameters)
            LoggingService.LogInfo(f"Service status saved for {ServiceStatus.get('ServiceName')}", "DatabaseManager", "SaveServiceStatus")
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
            query = f"UPDATE ServiceStatus SET {', '.join(UpdateFields)}, UpdatedAt = CURRENT_TIMESTAMP WHERE ServiceName = ?"
            
            self.DatabaseService.ExecuteQuery(query, Parameters)
            LoggingService.LogInfo(f"Service status updated for {ServiceName}", "DatabaseManager", "UpdateServiceStatus")
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
                LoggingService.LogInfo(f"Retrieved service status for {ServiceName}", "DatabaseManager", "GetServiceStatus")
                return rows[0]
            else:
                LoggingService.LogInfo(f"No service status found for {ServiceName}", "DatabaseManager", "GetServiceStatus")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception getting service status", e, "DatabaseManager", "GetServiceStatus")
            return None
    
    def GetNextPendingQualityTest(self) -> Optional[QualityTestingQueueModel]:
        """Get next pending quality test from queue."""
        try:
            LoggingService.LogFunctionEntry("GetNextPendingQualityTest", "DatabaseManager")
            
            query = """
            SELECT * FROM QualityTestingQueue 
            WHERE Status = 'Pending' 
            ORDER BY Priority DESC, DateAdded ASC 
            LIMIT 1
            """
            rows = self.DatabaseService.ExecuteQuery(query)
            
            if rows:
                row = rows[0]
                QueueItem = QualityTestingQueueModel()
                QueueItem.Id = row['Id']
                QueueItem.TranscodeAttemptId = row['TranscodeAttemptId']
                QueueItem.OriginalFilePath = row['OriginalFilePath']
                QueueItem.TranscodedFilePath = row['TranscodedFilePath']
                QueueItem.FileName = row['FileName']
                QueueItem.Status = row['Status']
                QueueItem.Priority = row['Priority']
                QueueItem.DateAdded = row['DateAdded']
                QueueItem.DateStarted = row['DateStarted']
                QueueItem.DateCompleted = row['DateCompleted']
                QueueItem.QualityThreshold = row['QualityThreshold']
                QueueItem.StrategyType = row['StrategyType']
                QueueItem.VMAFScore = row['VMAFScore']
                QueueItem.Results = row['Results']
                QueueItem.RetryCount = row['RetryCount']
                QueueItem.MaxRetries = row['MaxRetries']
                QueueItem.ErrorMessage = row['ErrorMessage']
                
                LoggingService.LogInfo(f"Retrieved pending quality test {QueueItem.Id}", "DatabaseManager", "GetNextPendingQualityTest")
                return QueueItem
            else:
                LoggingService.LogDebug("No pending quality tests found", "DatabaseManager", "GetNextPendingQualityTest")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception getting next pending quality test", e, "DatabaseManager", "GetNextPendingQualityTest")
            return None
    
    def SaveQualityTestingQueueItem(self, QueueItem: QualityTestingQueueModel) -> int:
        """Save quality testing queue item to database."""
        try:
            LoggingService.LogFunctionEntry("SaveQualityTestingQueueItem", "DatabaseManager", QueueItem.Id)
            
            if QueueItem.Id and QueueItem.Id > 0:
                # Update existing item
                query = """
                UPDATE QualityTestingQueue SET 
                    TranscodeAttemptId = ?, OriginalFilePath = ?, TranscodedFilePath = ?,
                    FileName = ?, Status = ?, Priority = ?, DateAdded = ?, DateStarted = ?,
                    DateCompleted = ?, QualityThreshold = ?, StrategyType = ?, VMAFScore = ?,
                    Results = ?, RetryCount = ?, MaxRetries = ?, ErrorMessage = ?
                WHERE Id = ?
                """
                parameters = (
                    QueueItem.TranscodeAttemptId, QueueItem.OriginalFilePath, QueueItem.TranscodedFilePath,
                    QueueItem.FileName, QueueItem.Status, QueueItem.Priority, QueueItem.DateAdded,
                    QueueItem.DateStarted, QueueItem.DateCompleted, QueueItem.QualityThreshold,
                    QueueItem.StrategyType, QueueItem.VMAFScore, QueueItem.Results,
                    QueueItem.RetryCount, QueueItem.MaxRetries, QueueItem.ErrorMessage, QueueItem.Id
                )
                self.DatabaseService.ExecuteNonQuery(query, parameters)
                LoggingService.LogInfo(f"Updated quality testing queue item {QueueItem.Id}", "DatabaseManager", "SaveQualityTestingQueueItem")
                return QueueItem.Id
            else:
                # Insert new item
                query = """
                INSERT INTO QualityTestingQueue (
                    TranscodeAttemptId, OriginalFilePath, TranscodedFilePath, FileName,
                    Status, Priority, DateAdded, DateStarted, DateCompleted,
                    QualityThreshold, StrategyType, VMAFScore, Results,
                    RetryCount, MaxRetries, ErrorMessage
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                parameters = (
                    QueueItem.TranscodeAttemptId, QueueItem.OriginalFilePath, QueueItem.TranscodedFilePath,
                    QueueItem.FileName, QueueItem.Status, QueueItem.Priority, QueueItem.DateAdded,
                    QueueItem.DateStarted, QueueItem.DateCompleted, QueueItem.QualityThreshold,
                    QueueItem.StrategyType, QueueItem.VMAFScore, QueueItem.Results,
                    QueueItem.RetryCount, QueueItem.MaxRetries, QueueItem.ErrorMessage
                )
                # Execute the insert and get the last row ID
                connection = self.DatabaseService.GetConnection()
                try:
                    cursor = connection.cursor()
                    cursor.execute(query, parameters)
                    connection.commit()
                    QueueId = cursor.lastrowid
                    QueueItem.Id = QueueId
                finally:
                    connection.close()
                LoggingService.LogInfo(f"Created quality testing queue item {QueueId}", "DatabaseManager", "SaveQualityTestingQueueItem")
                return QueueId
                
        except Exception as e:
            LoggingService.LogException("Exception saving quality testing queue item", e, "DatabaseManager", "SaveQualityTestingQueueItem")
            return 0
    
    def GetRunningQualityTestingJobsCount(self) -> int:
        """Get count of currently running quality testing jobs."""
        try:
            LoggingService.LogFunctionEntry("GetRunningQualityTestingJobsCount", "DatabaseManager")
            
            query = "SELECT COUNT(*) as Count FROM QualityTestingQueue WHERE Status = 'Running'"
            rows = self.DatabaseService.ExecuteQuery(query)
            
            if rows:
                count = rows[0]['Count']
                LoggingService.LogInfo(f"Found {count} running quality testing jobs", "DatabaseManager", "GetRunningQualityTestingJobsCount")
                return count
            else:
                return 0
                
        except Exception as e:
            LoggingService.LogException("Exception getting running quality testing jobs count", e, "DatabaseManager", "GetRunningQualityTestingJobsCount")
            return 0
    
    def GetRunningQualityTestingJobs(self) -> List[QualityTestingQueueModel]:
        """Get all running quality testing jobs."""
        try:
            LoggingService.LogFunctionEntry("GetRunningQualityTestingJobs", "DatabaseManager")
            
            query = """
                SELECT Id, TranscodeAttemptId, OriginalFilePath, TranscodedFilePath, FileName,
                       Status, Priority, DateAdded, DateStarted, DateCompleted, QualityThreshold,
                       StrategyType, VMAFScore, Results, RetryCount, MaxRetries, ErrorMessage,
                       StrategyId, AlternativeProfileIds, CustomSettings, SelectedResultId
                FROM QualityTestingQueue 
                WHERE Status = 'Running'
                ORDER BY DateStarted ASC
            """
            
            rows = self.DatabaseService.ExecuteQuery(query)
            
            jobs = []
            for row in rows:
                job = QualityTestingQueueModel()
                job.Id = row['Id']
                job.TranscodeAttemptId = row['TranscodeAttemptId']
                job.OriginalFilePath = row['OriginalFilePath']
                job.TranscodedFilePath = row['TranscodedFilePath']
                job.FileName = row['FileName']
                job.Status = row['Status']
                job.Priority = row['Priority']
                job.DateAdded = row['DateAdded']
                job.DateStarted = row['DateStarted']
                job.DateCompleted = row['DateCompleted']
                job.QualityThreshold = row['QualityThreshold']
                job.StrategyType = row['StrategyType']
                job.VMAFScore = row['VMAFScore']
                job.Results = row['Results']
                job.RetryCount = row['RetryCount']
                job.MaxRetries = row['MaxRetries']
                job.ErrorMessage = row['ErrorMessage']
                job.StrategyId = row['StrategyId']
                job.AlternativeProfileIds = row['AlternativeProfileIds']
                job.CustomSettings = row['CustomSettings']
                job.SelectedResultId = row['SelectedResultId']
                jobs.append(job)
            
            LoggingService.LogInfo(f"Retrieved {len(jobs)} running quality testing jobs", "DatabaseManager", "GetRunningQualityTestingJobs")
            return jobs
            
        except Exception as e:
            LoggingService.LogException("Exception getting running quality testing jobs", e, "DatabaseManager", "GetRunningQualityTestingJobs")
            return []
    
    def GetQualityTestingQueueStatistics(self) -> Dict[str, Any]:
        """Get quality testing queue statistics."""
        try:
            LoggingService.LogFunctionEntry("GetQualityTestingQueueStatistics", "DatabaseManager")
            
            query = """
            SELECT 
                Status,
                COUNT(*) as Count
            FROM QualityTestingQueue 
            GROUP BY Status
            """
            rows = self.DatabaseService.ExecuteQuery(query)
            
            statistics = {}
            for row in rows:
                statistics[row['Status']] = row['Count']
            
            LoggingService.LogInfo(f"Retrieved quality testing queue statistics: {statistics}", "DatabaseManager", "GetQualityTestingQueueStatistics")
            return statistics
            
        except Exception as e:
            LoggingService.LogException("Exception getting quality testing queue statistics", e, "DatabaseManager", "GetQualityTestingQueueStatistics")
            return {}
    
    def GetStuckQualityTestingJobs(self, HoursThreshold: int = 2) -> List[Dict[str, Any]]:
        """Get quality testing jobs that have been running for more than the specified hours."""
        try:
            LoggingService.LogFunctionEntry("GetStuckQualityTestingJobs", "DatabaseManager", HoursThreshold)
            
            from datetime import datetime, timedelta
            cutoff_time = datetime.now() - timedelta(hours=HoursThreshold)
            
            query = """
                SELECT Id, TranscodeAttemptId, FileName, DateStarted, Status 
                FROM QualityTestingQueue 
                WHERE Status = 'Running' AND DateStarted < ?
                ORDER BY DateStarted ASC
            """
            
            rows = self.DatabaseService.ExecuteQuery(query, (cutoff_time,))
            
            stuck_jobs = []
            for row in rows:
                stuck_jobs.append({
                    'Id': row['Id'],
                    'TranscodeAttemptId': row['TranscodeAttemptId'],
                    'FileName': row['FileName'],
                    'DateStarted': row['DateStarted'],
                    'Status': row['Status']
                })
            
            LoggingService.LogInfo(f"Found {len(stuck_jobs)} stuck quality testing jobs", "DatabaseManager", "GetStuckQualityTestingJobs")
            return stuck_jobs
            
        except Exception as e:
            LoggingService.LogException("Exception getting stuck quality testing jobs", e, "DatabaseManager", "GetStuckQualityTestingJobs")
            return []
    
    def GetQualityTestingStrategyForProfile(self, ProfileId: int) -> Optional[QualityTestingStrategyModel]:
        """Get quality testing strategy for specific profile."""
        try:
            LoggingService.LogFunctionEntry("GetQualityTestingStrategyForProfile", "DatabaseManager", ProfileId)
            
            query = """
            SELECT * FROM QualityTestingStrategies 
            WHERE ProfileId = ? AND IsEnabled = 1
            """
            rows = self.DatabaseService.ExecuteQuery(query, (ProfileId,))
            
            if rows:
                row = rows[0]
                Strategy = QualityTestingStrategyModel()
                Strategy.Id = row['Id']
                Strategy.ProfileId = row['ProfileId']
                Strategy.StrategyType = row['StrategyType']
                Strategy.VMAFThreshold = row['VMAFThreshold']
                Strategy.MaxAttempts = row['MaxAttempts']
                Strategy.AlternativeProfileIds = row['AlternativeProfileIds']
                Strategy.CustomSettings = row['CustomSettings']
                Strategy.IsEnabled = bool(row['IsEnabled'])
                Strategy.CreatedDate = row['CreatedDate']
                Strategy.UpdatedDate = row['UpdatedDate']
                
                LoggingService.LogInfo(f"Retrieved quality testing strategy for profile {ProfileId}", "DatabaseManager", "GetQualityTestingStrategyForProfile")
                return Strategy
            else:
                LoggingService.LogInfo(f"No quality testing strategy found for profile {ProfileId}", "DatabaseManager", "GetQualityTestingStrategyForProfile")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception getting quality testing strategy for profile", e, "DatabaseManager", "GetQualityTestingStrategyForProfile")
            return None
    
    def SaveQualityTestingStrategy(self, Strategy: QualityTestingStrategyModel) -> int:
        """Save quality testing strategy to database."""
        try:
            LoggingService.LogFunctionEntry("SaveQualityTestingStrategy", "DatabaseManager", Strategy.Id)
            
            if Strategy.Id and Strategy.Id > 0:
                # Update existing strategy
                query = """
                UPDATE QualityTestingStrategies SET 
                    ProfileId = ?, StrategyType = ?, VMAFThreshold = ?, MaxAttempts = ?,
                    AlternativeProfileIds = ?, CustomSettings = ?, IsEnabled = ?,
                    UpdatedDate = CURRENT_TIMESTAMP
                WHERE Id = ?
                """
                parameters = (
                    Strategy.ProfileId, Strategy.StrategyType, Strategy.VMAFThreshold,
                    Strategy.MaxAttempts, Strategy.AlternativeProfileIds, Strategy.CustomSettings,
                    Strategy.IsEnabled, Strategy.Id
                )
                self.DatabaseService.ExecuteQuery(query, parameters)
                LoggingService.LogInfo(f"Updated quality testing strategy {Strategy.Id}", "DatabaseManager", "SaveQualityTestingStrategy")
                return Strategy.Id
            else:
                # Insert new strategy
                query = """
                INSERT INTO QualityTestingStrategies (
                    ProfileId, StrategyType, VMAFThreshold, MaxAttempts,
                    AlternativeProfileIds, CustomSettings, IsEnabled,
                    CreatedDate, UpdatedDate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
                parameters = (
                    Strategy.ProfileId, Strategy.StrategyType, Strategy.VMAFThreshold,
                    Strategy.MaxAttempts, Strategy.AlternativeProfileIds, Strategy.CustomSettings,
                    Strategy.IsEnabled
                )
                cursor = self.DatabaseService.GetCursor()
                cursor.execute(query, parameters)
                StrategyId = cursor.lastrowid
                Strategy.Id = StrategyId
                LoggingService.LogInfo(f"Created quality testing strategy {StrategyId}", "DatabaseManager", "SaveQualityTestingStrategy")
                return StrategyId
                
        except Exception as e:
            LoggingService.LogException("Exception saving quality testing strategy", e, "DatabaseManager", "SaveQualityTestingStrategy")
            return 0
    
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
            LoggingService.LogFunctionEntry("CheckDatabaseConnection", "DatabaseManager")
            
            # Test database connection with simple query
            testResult = self.DatabaseService.ExecuteQuery("SELECT 1")
            if testResult:
                LoggingService.LogInfo("Database connection successful", "DatabaseManager", "CheckDatabaseConnection")
                return True
            else:
                LoggingService.LogError("Database connection test failed", "DatabaseManager", "CheckDatabaseConnection")
                return False
                
        except Exception as e:
            LoggingService.LogException("Exception checking database connection", e, "DatabaseManager", "CheckDatabaseConnection")
            return False
    
    # Quality Test Progress Management Methods
    def SaveQualityTestProgress(self, VMAFQueueId: int, TranscodeAttemptId: int, Status: str, ProgressPercent: float, 
                               CurrentPhase: str, StartTime: datetime = None, EndTime: datetime = None,
                               ErrorMessage: str = None, StrategyType: str = None, ETA: str = None,
                               CurrentTime: str = None, CurrentFrame: int = None, TotalFrames: int = None,
                               ProcessingSpeed: str = None) -> int:
        """Save quality test progress to database."""
        try:
            LoggingService.LogFunctionEntry("SaveQualityTestProgress", "DatabaseManager", VMAFQueueId, TranscodeAttemptId, Status, ProgressPercent, CurrentPhase)
            
            # Check if progress record already exists for this quality test
            existingQuery = "SELECT Id FROM QualityTestProgress WHERE VMAFQueueId = ? AND TranscodeAttemptId = ?"
            existingRows = self.DatabaseService.ExecuteQuery(existingQuery, (VMAFQueueId, TranscodeAttemptId))
            
            if existingRows:
                # Update existing record - preserve original StartTime, only update changed fields
                updateQuery = """
                    UPDATE QualityTestProgress SET 
                        Status = ?, ProgressPercentage = ?, CurrentStep = ?, 
                        EndTime = ?, ErrorMessage = ?, 
                        StrategyType = ?, ETA = ?, CurrentTime = ?, 
                        CurrentFrame = ?, TotalFrames = ?, ProcessingSpeed = ?, UpdatedAt = ?
                    WHERE VMAFQueueId = ? AND TranscodeAttemptId = ?
                """
                parameters = (Status, ProgressPercent, CurrentPhase, EndTime, 
                            ErrorMessage, StrategyType, ETA, CurrentTime, 
                            CurrentFrame, TotalFrames, ProcessingSpeed, datetime.now(), VMAFQueueId, TranscodeAttemptId)
                
                result = self.DatabaseService.ExecuteNonQuery(updateQuery, parameters)
                LoggingService.LogDebug(f"Updated quality test progress for VMAFQueue {VMAFQueueId}, TranscodeAttempt {TranscodeAttemptId}: {CurrentPhase} ({ProgressPercent}%)", "DatabaseManager", "SaveQualityTestProgress")
                return result
            else:
                # Insert new record
                insertQuery = """
                    INSERT INTO QualityTestProgress 
                    (VMAFQueueId, TranscodeAttemptId, Status, ProgressPercentage, CurrentStep, StartTime, EndTime, 
                     ErrorMessage, StrategyType, ETA, CurrentTime, CurrentFrame, TotalFrames, ProcessingSpeed, CreatedAt, UpdatedAt)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                # Ensure StartTime is provided (required field)
                if StartTime is None:
                    StartTime = datetime.now()
                
                parameters = (VMAFQueueId, TranscodeAttemptId, Status, ProgressPercent, CurrentPhase, StartTime, EndTime,
                            ErrorMessage, StrategyType, ETA, CurrentTime, CurrentFrame, TotalFrames, ProcessingSpeed, datetime.now(), datetime.now())
                
                progressId = self.DatabaseService.ExecuteNonQuery(insertQuery, parameters)
                LoggingService.LogDebug(f"Inserted new quality test progress for VMAFQueue {VMAFQueueId}, TranscodeAttempt {TranscodeAttemptId}: {CurrentPhase} ({ProgressPercent}%)", "DatabaseManager", "SaveQualityTestProgress")
                return progressId
                
        except Exception as e:
            LoggingService.LogException("Exception saving quality test progress", e, "DatabaseManager", "SaveQualityTestProgress")
            return 0
    
    def GetQualityTestProgress(self, VMAFQueueId: int, TranscodeAttemptId: int) -> Optional[Dict[str, Any]]:
        """Get progress information for a quality test."""
        try:
            LoggingService.LogFunctionEntry("GetQualityTestProgress", "DatabaseManager", VMAFQueueId, TranscodeAttemptId)
            
            query = """
                SELECT Status, ProgressPercentage, CurrentStep, StartTime, EndTime, 
                       ErrorMessage, StrategyType, ETA, CurrentTime, CurrentFrame, 
                       TotalFrames, ProcessingSpeed, CreatedAt, UpdatedAt
                FROM QualityTestProgress 
                WHERE VMAFQueueId = ? AND TranscodeAttemptId = ? 
                ORDER BY UpdatedAt DESC 
                LIMIT 1
            """
            
            rows = self.DatabaseService.ExecuteQuery(query, (VMAFQueueId, TranscodeAttemptId))
            
            if rows:
                row = rows[0]
                progress = {
                    'Status': row['Status'],
                    'ProgressPercentage': row['ProgressPercentage'],
                    'CurrentStep': row['CurrentStep'],
                    'StartTime': row['StartTime'],
                    'EndTime': row['EndTime'],
                    'ErrorMessage': row['ErrorMessage'],
                    'StrategyType': row['StrategyType'],
                    'ETA': row['ETA'],
                    'CurrentTime': row['CurrentTime'],
                    'CurrentFrame': row['CurrentFrame'],
                    'TotalFrames': row['TotalFrames'],
                    'ProcessingSpeed': row['ProcessingSpeed'],
                    'CreatedAt': row['CreatedAt'],
                    'UpdatedAt': row['UpdatedAt']
                }
                LoggingService.LogDebug(f"Retrieved progress for VMAFQueue {VMAFQueueId}, TranscodeAttempt {TranscodeAttemptId}: {progress['CurrentStep']} ({progress['ProgressPercentage']}%)", "DatabaseManager", "GetQualityTestProgress")
                return progress
            else:
                LoggingService.LogDebug(f"No progress found for VMAFQueue {VMAFQueueId}, TranscodeAttempt {TranscodeAttemptId}", "DatabaseManager", "GetQualityTestProgress")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception getting quality test progress", e, "DatabaseManager", "GetQualityTestProgress")
            return None
    
    # Quality Test Results Management Methods
    def SaveQualityTestResult(self, VMAFQueueId: int, TranscodeAttemptId: int, VMAFScore: float, 
                             ProfileId: int = 0, ProfileName: str = "Unknown", FileSize: int = 0,
                             TestDuration: float = 0.0, PassesThreshold: bool = False, 
                             Rank: int = None, ErrorMessage: str = None) -> int:
        """Save quality test result to database."""
        try:
            LoggingService.LogFunctionEntry("SaveQualityTestResult", "DatabaseManager", VMAFQueueId, TranscodeAttemptId, VMAFScore)
            
            # Use direct database connection to get the inserted row ID
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()
                
                query = """
                    INSERT INTO QualityTestResults 
                    (VMAFQueueId, TranscodeAttemptId, VMAFScore, ProfileId, ProfileName, FileSize,
                     TestDuration, PassesThreshold, Rank, ErrorMessage, DateTested)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                parameters = (VMAFQueueId, TranscodeAttemptId, VMAFScore, ProfileId, ProfileName, FileSize,
                             TestDuration, PassesThreshold, Rank, ErrorMessage, datetime.now())
                
                cursor.execute(query, parameters)
                connection.commit()
                resultId = cursor.lastrowid
                
                LoggingService.LogInfo(f"Saved quality test result for VMAFQueue {VMAFQueueId}, TranscodeAttempt {TranscodeAttemptId}: VMAF Score {VMAFScore}, Result ID: {resultId}", "DatabaseManager", "SaveQualityTestResult")
                
                # CRITICAL: Update the TranscodeAttempts table with the VMAF score
                self.UpdateTranscodeAttemptVMAF(TranscodeAttemptId, VMAFScore)
                
                return resultId
                
            finally:
                connection.close()
            
        except Exception as e:
            LoggingService.LogException("Exception saving quality test result", e, "DatabaseManager", "SaveQualityTestResult")
            return 0
    
    def UpdateTranscodeAttemptVMAF(self, TranscodeAttemptId: int, VMAFScore: float) -> bool:
        """Update the VMAF score in the TranscodeAttempts table."""
        try:
            LoggingService.LogFunctionEntry("UpdateTranscodeAttemptVMAF", "DatabaseManager", TranscodeAttemptId, VMAFScore)
            
            query = """
                UPDATE TranscodeAttempts 
                SET VMAF = ?
                WHERE Id = ?
            """
            parameters = (VMAFScore, TranscodeAttemptId)
            
            result = self.DatabaseService.ExecuteNonQuery(query, parameters)
            LoggingService.LogInfo(f"Updated TranscodeAttempts.VMAF for attempt {TranscodeAttemptId} with score {VMAFScore}", "DatabaseManager", "UpdateTranscodeAttemptVMAF")
            return result > 0
            
        except Exception as e:
            LoggingService.LogException("Exception updating TranscodeAttempts VMAF", e, "DatabaseManager", "UpdateTranscodeAttemptVMAF")
            return False
    
    def GetQualityTestingHistory(self, Limit: int = 50) -> List[QualityTestingQueueModel]:
        """Get quality testing history from completed jobs."""
        try:
            LoggingService.LogFunctionEntry("GetQualityTestingHistory", "DatabaseManager", Limit)
            
            query = """
                SELECT Id, TranscodeAttemptId, OriginalFilePath, TranscodedFilePath, FileName,
                       Status, Priority, DateAdded, DateStarted, DateCompleted, VMAFScore,
                       QualityThreshold, StrategyType, Results, RetryCount, MaxRetries,
                       ErrorMessage, StrategyId, SelectedResultId, DateCreated
                FROM QualityTestingQueue
                WHERE Status IN ('Completed', 'Failed', 'Skipped')
                ORDER BY DateCompleted DESC
                LIMIT ?
            """
            
            rows = self.DatabaseService.ExecuteQuery(query, (Limit,))
            historyItems = []
            
            for row in rows:
                item = QualityTestingQueueModel()
                item.Id = row[0]
                item.TranscodeAttemptId = row[1]
                item.OriginalFilePath = row[2]
                item.TranscodedFilePath = row[3]
                item.FileName = row[4]
                item.Status = row[5]
                item.Priority = row[6]
                item.DateAdded = row[7]
                item.DateStarted = row[8]
                item.DateCompleted = row[9]
                item.VMAFScore = row[10]
                item.QualityThreshold = row[11]
                item.StrategyType = row[12]
                item.Results = row[13]
                item.RetryCount = row[14]
                item.MaxRetries = row[15]
                item.ErrorMessage = row[16]
                item.StrategyId = row[17]
                item.SelectedResultId = row[18]
                item.DateCreated = row[19]
                
                historyItems.append(item)
            
            LoggingService.LogDebug(f"Retrieved {len(historyItems)} quality testing history items", "DatabaseManager", "GetQualityTestingHistory")
            return historyItems
            
        except Exception as e:
            LoggingService.LogException("Exception getting quality testing history", e, "DatabaseManager", "GetQualityTestingHistory")
            return []

    def GetQualityTestResults(self, VMAFQueueId: int = None, TranscodeAttemptId: int = None, Limit: int = 50) -> List[Dict[str, Any]]:
        """Get quality test results."""
        try:
            LoggingService.LogFunctionEntry("GetQualityTestResults", "DatabaseManager", VMAFQueueId, TranscodeAttemptId, Limit)
            
            if VMAFQueueId and TranscodeAttemptId:
                query = """
                    SELECT qtr.Id, qtr.VMAFQueueId, qtr.TranscodeAttemptId, qtr.VMAFScore, qtr.ProfileId, qtr.ProfileName,
                           qtr.FileSize, qtr.TestDuration, qtr.PassesThreshold, qtr.Rank, qtr.ErrorMessage, qtr.DateTested,
                           ta.FilePath, ta.AttemptDate, ta.Quality, ta.OldSizeBytes, ta.NewSizeBytes, ta.Success,
                           ta.SizeReductionBytes, ta.SizeReductionPercent, ta.TranscodeDurationSeconds, ta.FfpmpegCommand,
                           ta.AudioBitrateKbps, ta.VideoBitrateKbps, ta.ProfileName as TranscodeProfileName
                    FROM QualityTestResults qtr
                    JOIN TranscodeAttempts ta ON qtr.TranscodeAttemptId = ta.Id
                    WHERE qtr.VMAFQueueId = ? AND qtr.TranscodeAttemptId = ?
                    ORDER BY qtr.DateTested DESC
                """
                parameters = (VMAFQueueId, TranscodeAttemptId)
            else:
                query = """
                    SELECT qtr.Id, qtr.VMAFQueueId, qtr.TranscodeAttemptId, qtr.VMAFScore, qtr.ProfileId, qtr.ProfileName,
                           qtr.FileSize, qtr.TestDuration, qtr.PassesThreshold, qtr.Rank, qtr.ErrorMessage, qtr.DateTested,
                           ta.FilePath, ta.AttemptDate, ta.Quality, ta.OldSizeBytes, ta.NewSizeBytes, ta.Success,
                           ta.SizeReductionBytes, ta.SizeReductionPercent, ta.TranscodeDurationSeconds, ta.FfpmpegCommand,
                           ta.AudioBitrateKbps, ta.VideoBitrateKbps, ta.ProfileName as TranscodeProfileName
                    FROM QualityTestResults qtr
                    JOIN TranscodeAttempts ta ON qtr.TranscodeAttemptId = ta.Id
                    ORDER BY qtr.DateTested DESC
                    LIMIT ?
                """
                parameters = (Limit,)
            
            rows = self.DatabaseService.ExecuteQuery(query, parameters)
            
            results = []
            for row in rows:
                result = {
                    'Id': row['Id'],
                    'VMAFQueueId': row['VMAFQueueId'],
                    'TranscodeAttemptId': row['TranscodeAttemptId'],
                    'VMAFScore': row['VMAFScore'],
                    'ProfileId': row['ProfileId'],
                    'ProfileName': row['ProfileName'],
                    'FileSize': row['FileSize'],
                    'TestDuration': row['TestDuration'],
                    'PassesThreshold': row['PassesThreshold'],
                    'Rank': row['Rank'],
                    'ErrorMessage': row['ErrorMessage'],
                    'DateTested': row['DateTested'],
                    'FilePath': row['FilePath'],
                    'AttemptDate': row['AttemptDate'],
                    'Quality': row['Quality'],
                    'OldSizeBytes': row['OldSizeBytes'],
                    'NewSizeBytes': row['NewSizeBytes'],
                    'Success': row['Success'],
                    'SizeReductionBytes': row['SizeReductionBytes'],
                    'SizeReductionPercent': row['SizeReductionPercent'],
                    'TranscodeDurationSeconds': row['TranscodeDurationSeconds'],
                    'FfpmpegCommand': row['FfpmpegCommand'],
                    'AudioBitrateKbps': row['AudioBitrateKbps'],
                    'VideoBitrateKbps': row['VideoBitrateKbps'],
                    'TranscodeProfileName': row['TranscodeProfileName']
                }
                results.append(result)
            
            LoggingService.LogInfo(f"Retrieved {len(results)} quality test results", "DatabaseManager", "GetQualityTestResults")
            return results
            
        except Exception as e:
            LoggingService.LogException("Exception getting quality test results", e, "DatabaseManager", "GetQualityTestResults")
            return []

    def GetAllQualityTestingQueueItems(self) -> List[QualityTestingQueueModel]:
        """Get all quality testing queue items."""
        try:
            LoggingService.LogFunctionEntry("GetAllQualityTestingQueueItems", "DatabaseManager")
            
            query = """
                SELECT Id, TranscodeAttemptId, OriginalFilePath, TranscodedFilePath, FileName, 
                       Status, Priority, DateAdded, DateStarted, DateCompleted, VMAFScore, 
                       QualityThreshold, ErrorMessage, RetryCount, MaxRetries, StrategyType, 
                       StrategyId, AlternativeProfileIds, CustomSettings, Results, SelectedResultId
                FROM QualityTestingQueue
                ORDER BY DateAdded DESC
            """
            
            rows = self.DatabaseService.ExecuteQuery(query)
            queueItems = []
            
            for row in rows:
                queueItem = QualityTestingQueueModel()
                queueItem.Id = row[0]
                queueItem.TranscodeAttemptId = row[1]
                queueItem.OriginalFilePath = row[2]
                queueItem.TranscodedFilePath = row[3]
                queueItem.FileName = row[4]
                queueItem.Status = row[5]
                queueItem.Priority = row[6]
                queueItem.DateAdded = row[7]
                queueItem.DateStarted = row[8]
                queueItem.DateCompleted = row[9]
                queueItem.VMAFScore = row[10]
                queueItem.QualityThreshold = row[11]
                queueItem.ErrorMessage = row[12]
                queueItem.RetryCount = row[13]
                queueItem.MaxRetries = row[14]
                queueItem.StrategyType = row[15]
                queueItem.StrategyId = row[16]
                queueItem.AlternativeProfileIds = row[17]
                queueItem.CustomSettings = row[18]
                queueItem.Results = row[19]
                queueItem.SelectedResultId = row[20]
                
                queueItems.append(queueItem)
            
            LoggingService.LogDebug(f"Retrieved {len(queueItems)} quality testing queue items", "DatabaseManager", "GetAllQualityTestingQueueItems")
            return queueItems
            
        except Exception as e:
            LoggingService.LogException("Exception getting all quality testing queue items", e, "DatabaseManager", "GetAllQualityTestingQueueItems")
            return []

    def GetRecentTranscodeAttempts(self, Limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent transcoding attempts."""
        try:
            LoggingService.LogFunctionEntry("GetRecentTranscodeAttempts", "DatabaseManager", Limit)
            
            query = """
                SELECT Id, FilePath, AttemptDate, Quality, OldSizeBytes, NewSizeBytes, 
                       Success, SizeReductionBytes, SizeReductionPercent, ErrorMessage, 
                       TranscodeDurationSeconds, FfpmpegCommand, AudioBitrateKbps, 
                       VideoBitrateKbps, ProfileName, VMAF
                FROM TranscodeAttempts
                ORDER BY AttemptDate DESC
                LIMIT ?
            """
            
            rows = self.DatabaseService.ExecuteQuery(query, (Limit,))
            attempts = []
            
            for row in rows:
                attempt = {
                    "Id": row[0],
                    "FilePath": row[1],
                    "AttemptDate": row[2],
                    "Quality": row[3],
                    "OldSizeBytes": row[4],
                    "NewSizeBytes": row[5],
                    "Success": row[6],
                    "SizeReductionBytes": row[7],
                    "SizeReductionPercent": row[8],
                    "ErrorMessage": row[9],
                    "TranscodeDurationSeconds": row[10],
                    "FfpmpegCommand": row[11],
                    "AudioBitrateKbps": row[12],
                    "VideoBitrateKbps": row[13],
                    "ProfileName": row[14],
                    "VMAF": row[15]
                }
                attempts.append(attempt)
            
            LoggingService.LogDebug(f"Retrieved {len(attempts)} recent transcoding attempts", "DatabaseManager", "GetRecentTranscodeAttempts")
            return attempts
            
        except Exception as e:
            LoggingService.LogException("Exception getting recent transcoding attempts", e, "DatabaseManager", "GetRecentTranscodeAttempts")
            return []
    
    def GetQualityTestingQueueItemByTranscodeAttemptId(self, TranscodeAttemptId: int) -> Optional[QualityTestingQueueModel]:
        """Get quality testing queue item by TranscodeAttemptId if it exists."""
        try:
            LoggingService.LogFunctionEntry("GetQualityTestingQueueItemByTranscodeAttemptId", "DatabaseManager", TranscodeAttemptId)
            
            query = """
                SELECT Id, TranscodeAttemptId, OriginalFilePath, TranscodedFilePath, FileName, 
                       Status, Priority, DateAdded, DateStarted, DateCompleted, VMAFScore, 
                       QualityThreshold, ErrorMessage, RetryCount, MaxRetries, StrategyType, 
                       StrategyId, AlternativeProfileIds, CustomSettings, Results, SelectedResultId
                FROM QualityTestingQueue
                WHERE TranscodeAttemptId = ?
                ORDER BY DateAdded DESC
                LIMIT 1
            """
            
            rows = self.DatabaseService.ExecuteQuery(query, (TranscodeAttemptId,))
            
            if rows:
                row = rows[0]
                queueItem = QualityTestingQueueModel()
                queueItem.Id = row[0]
                queueItem.TranscodeAttemptId = row[1]
                queueItem.OriginalFilePath = row[2] or ""
                queueItem.TranscodedFilePath = row[3] or ""
                queueItem.FileName = row[4] or ""
                queueItem.Status = row[5] or "Pending"
                queueItem.Priority = row[6] or 50
                queueItem.DateAdded = row[7]
                queueItem.DateStarted = row[8]
                queueItem.DateCompleted = row[9]
                queueItem.VMAFScore = row[10]
                queueItem.QualityThreshold = row[11] or 90.0
                queueItem.ErrorMessage = row[12]
                queueItem.RetryCount = row[13] or 0
                queueItem.MaxRetries = row[14] or 3
                queueItem.StrategyType = row[15] or "Single"
                queueItem.StrategyId = row[16]
                queueItem.AlternativeProfileIds = row[17]
                queueItem.CustomSettings = row[18]
                queueItem.Results = row[19]
                queueItem.SelectedResultId = row[20]
                
                LoggingService.LogDebug(f"Found existing quality test entry for TranscodeAttemptId {TranscodeAttemptId}", "DatabaseManager", "GetQualityTestingQueueItemByTranscodeAttemptId")
                return queueItem
            else:
                LoggingService.LogDebug(f"No existing quality test entry found for TranscodeAttemptId {TranscodeAttemptId}", "DatabaseManager", "GetQualityTestingQueueItemByTranscodeAttemptId")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception getting quality testing queue item by TranscodeAttemptId", e, "DatabaseManager", "GetQualityTestingQueueItemByTranscodeAttemptId")
            return None
    
    def DeleteQualityTestingQueueItem(self, QueueId: int) -> bool:
        """Delete a quality testing queue item by ID."""
        try:
            LoggingService.LogFunctionEntry("DeleteQualityTestingQueueItem", "DatabaseManager", QueueId)
            
            query = "DELETE FROM QualityTestingQueue WHERE Id = ?"
            rowsAffected = self.DatabaseService.ExecuteNonQuery(query, (QueueId,))
            
            if rowsAffected > 0:
                LoggingService.LogInfo(f"Deleted quality testing queue item {QueueId}", "DatabaseManager", "DeleteQualityTestingQueueItem")
                return True
            else:
                LoggingService.LogWarning(f"Quality testing queue item {QueueId} not found for deletion", "DatabaseManager", "DeleteQualityTestingQueueItem")
                return False
                
        except Exception as e:
            LoggingService.LogException("Exception deleting quality testing queue item", e, "DatabaseManager", "DeleteQualityTestingQueueItem")
            return False
    
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