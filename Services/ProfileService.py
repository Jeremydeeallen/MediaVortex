from typing import List, Optional
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
    
    def CreateProfile(self, profile_name: str, description: str = "") -> TranscodeProfileModel:
        """Create a new transcoding profile."""
        try:
            LoggingService.LogFunctionEntry("CreateProfile", 'ProfileService', profile_name, description=description)
            profile = TranscodeProfileModel(
                ProfileName=profile_name,
                Description=description,
                CreatedDate=datetime.now(),
                LastModified=datetime.now()
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
                    transcode_down_to: str) -> ProfileThresholdModel:
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
                TranscodeDownTo=transcode_down_to
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
