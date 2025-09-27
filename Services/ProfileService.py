from typing import List, Optional, Dict, Any
from datetime import datetime
from Models.TranscodeProfileModel import TranscodeProfileModel
from Models.ProfileThresholdModel import ProfileThresholdModel
from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


class ProfileService:
    """Business service for managing transcoding profiles and their thresholds."""
    
    def __init__(self, database_manager: DatabaseManager = None):
        self.DatabaseManager = database_manager or DatabaseManager()
    
    def GetAllProfiles(self) -> List[TranscodeProfileModel]:
        """Get all transcoding profiles."""
        return self.DatabaseManager.GetAllProfiles()
    
    def GetProfileById(self, profile_id: int) -> Optional[TranscodeProfileModel]:
        """Get a specific profile by ID."""
        return self.DatabaseManager.GetProfileById(profile_id)
    
    def CreateProfile(self, profile_name: str, description: str = "", 
                     codec: str = "libsvtav1", preset: int = 6, film_grain: int = 10,
                     ten_bit_encoding: bool = False, yadif_mode: int = 1, yadif_parity: int = 1, yadif_deint: int = 1) -> TranscodeProfileModel:
        """Create a new transcoding profile."""
        try:
            LoggingService.LogFunctionEntry("CreateProfile", 'ProfileService', profile_name, description=description)
            profile = TranscodeProfileModel(
                ProfileName=profile_name,
                Description=description,
                CreatedDate=datetime.now(),
                LastModified=datetime.now(),
                Codec=codec,
                Preset=preset,
                FilmGrain=film_grain,
                TenBitEncoding=ten_bit_encoding,
                YadifMode=yadif_mode,
                YadifParity=yadif_parity,
                YadifDeint=yadif_deint
            )
            
            LoggingService.LogInfo("Saving profile to database...", 'CreateProfile', 'ProfileService')
            profile_id = self.DatabaseManager.SaveProfile(profile)
            profile.Id = profile_id
            LoggingService.LogInfo(f"Profile saved with ID: {profile_id}", 'CreateProfile', 'ProfileService')
            
            LoggingService.LogFunctionExit("CreateProfile", profile_id)
            return profile
        except Exception as e:
            LoggingService.LogException("Exception in ProfileService.CreateProfile", e, 'CreateProfile', 'ProfileService')
            raise
    
    def UpdateProfile(self, profile: TranscodeProfileModel) -> TranscodeProfileModel:
        """Update an existing transcoding profile."""
        try:
            LoggingService.LogFunctionEntry("UpdateProfile", 'ProfileService', profile.Id, profile.ProfileName, profile.Description)
            profile.LastModified = datetime.now()
            LoggingService.LogInfo("Saving profile to database...", 'CreateProfile', 'ProfileService')
            profile_id = self.DatabaseManager.SaveProfile(profile)
            profile.Id = profile_id
            LoggingService.LogInfo(f"Profile updated successfully with ID: {profile_id}", 'UpdateProfile', 'ProfileService')
            LoggingService.LogFunctionExit("UpdateProfile", profile_id)
            return profile
        except Exception as e:
            LoggingService.LogException("Exception in ProfileService.UpdateProfile", e, 'UpdateProfile', 'ProfileService')
            raise
    
    def DeleteProfile(self, profile_id: int) -> bool:
        """Delete a transcoding profile and all its associated thresholds."""
        return self.DatabaseManager.DeleteProfile(profile_id)
    
    def GetProfileThresholds(self, profile_id: int) -> List[ProfileThresholdModel]:
        """Get all thresholds for a specific profile."""
        return self.DatabaseManager.GetThresholdsByProfileId(profile_id)
    
    def AddThreshold(self, profile_id: int, resolution: str, 
                    under_30_min_mb: int, under_65_min_mb: int, over_65_min_mb: int,
                    video_bitrate_kbps: int, audio_bitrate_kbps: int,
                    fallback_video_bitrate_kbps: int, fallback_audio_bitrate_kbps: int,
                    transcode_down_to: str, quality: int = None) -> ProfileThresholdModel:
        """Add a new threshold to a profile."""
        try:
            LoggingService.LogFunctionEntry("AddThreshold", 'ProfileService', profile_id, resolution, 
                                           under_30_min_mb, under_65_min_mb, over_65_min_mb,
                                           video_bitrate_kbps, audio_bitrate_kbps,
                                           fallback_video_bitrate_kbps, fallback_audio_bitrate_kbps,
                                           transcode_down_to)
            threshold = ProfileThresholdModel(
                ProfileId=profile_id,
                Resolution=resolution,
                Under30MinMB=under_30_min_mb,
                Under65MinMB=under_65_min_mb,
                Over65MinMB=over_65_min_mb,
                VideoBitrateKbps=video_bitrate_kbps,
                AudioBitrateKbps=audio_bitrate_kbps,
                FallbackVideoBitrateKbps=fallback_video_bitrate_kbps,
                FallbackAudioBitrateKbps=fallback_audio_bitrate_kbps,
                TranscodeDownTo=transcode_down_to,
                Quality=quality
            )
            
            LoggingService.LogInfo("Saving threshold to database...", 'AddThreshold', 'ProfileService')
            threshold_id = self.DatabaseManager.SaveThreshold(threshold)
            threshold.Id = threshold_id
            LoggingService.LogInfo(f"Threshold saved with ID: {threshold_id}", 'AddThreshold', 'ProfileService')
            
            LoggingService.LogFunctionExit("AddThreshold", threshold_id)
            return threshold
        except Exception as e:
            LoggingService.LogException("Exception in ProfileService.AddThreshold", e, 'AddThreshold', 'ProfileService')
            raise
    
    def UpdateThreshold(self, threshold: ProfileThresholdModel) -> ProfileThresholdModel:
        """Update an existing threshold."""
        threshold_id = self.DatabaseManager.SaveThreshold(threshold)
        threshold.Id = threshold_id
        
        return threshold
    
    def DeleteThreshold(self, threshold_id: int) -> bool:
        """Delete a threshold."""
        return self.DatabaseManager.DeleteThreshold(threshold_id)
    
    def GetProfileWithThresholds(self, profile_id: int) -> Optional[dict]:
        """Get a profile with all its thresholds."""
        profile = self.GetProfileById(profile_id)
        if not profile:
            return None
        
        thresholds = self.GetProfileThresholds(profile_id)
        
        return {
            'profile': profile,
            'thresholds': thresholds
        }
    
    def AssignProfileToRootFolder(self, RootFolderPath: str, ProfileId: int) -> Dict[str, Any]:
        """Assign a profile to all media files in a specific root folder."""
        try:
            LoggingService.LogFunctionEntry("AssignProfileToRootFolder", "ProfileService", RootFolderPath, ProfileId)
            
            # Validate that profile exists
            profile = self.GetProfileById(ProfileId)
            if not profile:
                errorMsg = f"Profile with ID {ProfileId} not found"
                LoggingService.LogError(errorMsg, "ProfileService", "AssignProfileToRootFolder")
                return {"Success": False, "ErrorMessage": errorMsg, "FilesUpdated": 0}
            
            # Validate that root folder path is not empty
            if not RootFolderPath or not RootFolderPath.strip():
                errorMsg = "Root folder path cannot be empty"
                LoggingService.LogError(errorMsg, "ProfileService", "AssignProfileToRootFolder")
                return {"Success": False, "ErrorMessage": errorMsg, "FilesUpdated": 0}
            
            # Update media files in the root folder
            filesUpdated = self.DatabaseManager.UpdateMediaFilesProfileByRootFolder(RootFolderPath.strip(), ProfileId)
            
            if filesUpdated > 0:
                successMsg = f"Successfully assigned profile '{profile.ProfileName}' to {filesUpdated} files in root folder '{RootFolderPath}'"
                LoggingService.LogInfo(successMsg, "ProfileService", "AssignProfileToRootFolder")
                return {
                    "Success": True, 
                    "Message": successMsg,
                    "FilesUpdated": filesUpdated,
                    "ProfileName": profile.ProfileName,
                    "RootFolderPath": RootFolderPath
                }
            else:
                warningMsg = f"No files found in root folder '{RootFolderPath}' to assign profile '{profile.ProfileName}'"
                LoggingService.LogWarning(warningMsg, "ProfileService", "AssignProfileToRootFolder")
                return {
                    "Success": True, 
                    "Message": warningMsg,
                    "FilesUpdated": 0,
                    "ProfileName": profile.ProfileName,
                    "RootFolderPath": RootFolderPath
                }
            
        except Exception as e:
            errorMsg = f"Exception assigning profile to root folder: {str(e)}"
            LoggingService.LogException(errorMsg, e, "ProfileService", "AssignProfileToRootFolder")
            return {"Success": False, "ErrorMessage": errorMsg, "FilesUpdated": 0}