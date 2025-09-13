from typing import List, Optional
from datetime import datetime
from Models.TranscodeProfileModel import TranscodeProfileModel
from Models.ProfileThresholdModel import ProfileThresholdModel
from Repositories.DatabaseManager import DatabaseManager
from Services.DebugService import DebugService


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
            DebugService.LogFunctionEntry("CreateProfile", profile_name, description)
            profile = TranscodeProfileModel(
                ProfileName=profile_name,
                Description=description,
                CreatedDate=datetime.now(),
                LastModified=datetime.now()
            )
            
            DebugService.Log("Saving profile to database...")
            profile_id = self.DatabaseManager.SaveProfile(profile)
            profile.Id = profile_id
            DebugService.Log("Profile saved with ID: {}", profile_id)
            
            DebugService.LogFunctionExit("CreateProfile", profile_id)
            return profile
        except Exception as e:
            DebugService.LogException("Exception in ProfileService.CreateProfile", e)
            raise
    
    def UpdateProfile(self, profile: TranscodeProfileModel) -> TranscodeProfileModel:
        """Update an existing transcoding profile."""
        try:
            DebugService.LogFunctionEntry("UpdateProfile", profile.Id, profile.ProfileName, profile.Description)
            profile.LastModified = datetime.now()
            DebugService.Log("Saving profile to database...")
            profile_id = self.DatabaseManager.SaveProfile(profile)
            profile.Id = profile_id
            DebugService.Log("Profile updated successfully with ID: {}", profile_id)
            DebugService.LogFunctionExit("UpdateProfile", profile_id)
            return profile
        except Exception as e:
            DebugService.LogException("Exception in ProfileService.UpdateProfile", e)
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
            DebugService.LogFunctionEntry("AddThreshold", profile_id, resolution, 
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
            
            DebugService.Log("Saving threshold to database...")
            threshold_id = self.DatabaseManager.SaveThreshold(threshold)
            threshold.Id = threshold_id
            DebugService.Log("Threshold saved with ID: {}", threshold_id)
            
            DebugService.LogFunctionExit("AddThreshold", threshold_id)
            return threshold
        except Exception as e:
            DebugService.LogException("Exception in ProfileService.AddThreshold", e)
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
