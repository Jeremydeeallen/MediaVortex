from typing import List, Optional, Dict, Any
from datetime import datetime
from Models.TranscodeProfileModel import TranscodeProfileModel
from Models.ProfileThresholdModel import ProfileThresholdModel
from Services.ProfileService import ProfileService
from Services.DebugService import DebugService


class ProfileManagementViewModel:
    """ViewModel for managing transcoding profiles in the UI."""
    
    def __init__(self, profile_service: ProfileService = None):
        self.ProfileService = profile_service or ProfileService()
        self.Profiles: List[TranscodeProfileModel] = []
        self.SelectedProfile: Optional[TranscodeProfileModel] = None
        self.SelectedProfileThresholds: List[ProfileThresholdModel] = []
        self.ErrorMessage: str = ""
        self.SuccessMessage: str = ""
    
    def LoadProfiles(self) -> bool:
        """Load all profiles from the database."""
        try:
            self.Profiles = self.ProfileService.GetAllProfiles()
            self.ErrorMessage = ""
            return True
        except Exception as e:
            self.ErrorMessage = f"Failed to load profiles: {str(e)}"
            return False
    
    def SelectProfile(self, profile_id: int) -> bool:
        """Select a profile and load its thresholds."""
        try:
            profile_data = self.ProfileService.GetProfileWithThresholds(profile_id)
            if profile_data:
                self.SelectedProfile = profile_data['profile']
                self.SelectedProfileThresholds = profile_data['thresholds']
                self.ErrorMessage = ""
                return True
            else:
                self.ErrorMessage = "Profile not found"
                return False
        except Exception as e:
            self.ErrorMessage = f"Failed to load profile: {str(e)}"
            return False
    
    def CreateProfile(self, profile_name: str, description: str = "") -> bool:
        """Create a new profile."""
        try:
            if not profile_name.strip():
                self.ErrorMessage = "Profile name is required"
                return False
            
            # Check if profile name already exists
            existing_profiles = [p for p in self.Profiles if p.ProfileName.lower() == profile_name.lower()]
            if existing_profiles:
                self.ErrorMessage = "A profile with this name already exists"
                return False
            
            new_profile = self.ProfileService.CreateProfile(profile_name, description)
            self.Profiles.append(new_profile)
            self.SuccessMessage = f"Profile '{profile_name}' created successfully"
            self.ErrorMessage = ""
            return True
        except Exception as e:
            self.ErrorMessage = f"Failed to create profile: {str(e)}"
            return False
    
    def CreateProfileWithThresholds(self, profile_name: str, description: str, thresholds: List[dict]) -> bool:
        """Create a new profile with multiple thresholds."""
        try:
            DebugService.LogFunctionEntry("CreateProfileWithThresholds", profile_name, description, len(thresholds))
            DebugService.LogData("Thresholds data", thresholds)
            
            if not profile_name.strip():
                self.ErrorMessage = "Profile name is required"
                return False
            
            # Check if profile name already exists
            existing_profiles = [p for p in self.Profiles if p.ProfileName.lower() == profile_name.lower()]
            if existing_profiles:
                self.ErrorMessage = "A profile with this name already exists"
                return False
            
            # Create the profile first
            DebugService.Log("Creating profile...")
            new_profile = self.ProfileService.CreateProfile(profile_name, description)
            DebugService.Log("Profile created with ID: {}", new_profile.Id)
            
            # Add all thresholds
            DebugService.Log("Adding {} thresholds...", len(thresholds))
            for i, threshold_data in enumerate(thresholds):
                DebugService.Log("Adding threshold {}: {}", i+1, threshold_data)
                self.ProfileService.AddThreshold(
                    new_profile.Id,
                    threshold_data['Resolution'],
                    threshold_data['Under30MinMB'],
                    threshold_data['Under65MinMB'],
                    threshold_data['Over65MinMB'],
                    threshold_data['VideoBitrateKbps'],
                    threshold_data['AudioBitrateKbps'],
                    threshold_data['FallbackVideoBitrateKbps'],
                    threshold_data['FallbackAudioBitrateKbps'],
                    threshold_data['TranscodeDownTo']
                )
                DebugService.Log("Threshold {} added successfully", i+1)
            
            # Reload profiles to get updated data
            DebugService.Log("Reloading profiles...")
            self.LoadProfiles()
            self.SuccessMessage = f"Profile '{profile_name}' created successfully with {len(thresholds)} thresholds"
            self.ErrorMessage = ""
            DebugService.LogFunctionExit("CreateProfileWithThresholds", True)
            return True
        except Exception as e:
            DebugService.LogException("Exception in CreateProfileWithThresholds", e)
            self.ErrorMessage = f"Failed to create profile: {str(e)}"
            return False
    
    def UpdateProfile(self, profile: TranscodeProfileModel) -> bool:
        """Update an existing profile."""
        try:
            if not profile.ProfileName.strip():
                self.ErrorMessage = "Profile name is required"
                return False
            
            # Check if another profile has the same name
            existing_profiles = [p for p in self.Profiles if p.ProfileName.lower() == profile.ProfileName.lower() and p.Id != profile.Id]
            if existing_profiles:
                self.ErrorMessage = "A profile with this name already exists"
                return False
            
            updated_profile = self.ProfileService.UpdateProfile(profile)
            
            # Update the profile in our list
            for i, p in enumerate(self.Profiles):
                if p.Id == updated_profile.Id:
                    self.Profiles[i] = updated_profile
                    break
            
            # Update selected profile if it's the one being updated
            if self.SelectedProfile and self.SelectedProfile.Id == updated_profile.Id:
                self.SelectedProfile = updated_profile
            
            self.SuccessMessage = f"Profile '{profile.ProfileName}' updated successfully"
            self.ErrorMessage = ""
            return True
        except Exception as e:
            self.ErrorMessage = f"Failed to update profile: {str(e)}"
            return False
    
    def UpdateProfileWithThresholds(self, profile_id: int, profile_name: str, description: str, thresholds: List[dict]) -> bool:
        """Update an existing profile with multiple thresholds."""
        try:
            DebugService.LogFunctionEntry("UpdateProfileWithThresholds", profile_id, profile_name, description, len(thresholds))
            DebugService.LogData("Thresholds data", thresholds)
            
            if not profile_name.strip():
                self.ErrorMessage = "Profile name is required"
                DebugService.Log("Profile name validation failed")
                return False
            
            # Check if another profile has the same name
            existing_profiles = [p for p in self.Profiles if p.ProfileName.lower() == profile_name.lower() and p.Id != profile_id]
            if existing_profiles:
                self.ErrorMessage = "A profile with this name already exists"
                DebugService.Log("Profile name already exists")
                return False
            
            # Update the profile - get existing profile to preserve CreatedDate
            DebugService.Log("Getting existing profile to preserve CreatedDate...")
            existing_profile = self.ProfileService.GetProfileById(profile_id)
            if not existing_profile:
                self.ErrorMessage = f"Profile with ID {profile_id} not found"
                DebugService.Log("Profile not found for update")
                return False
            
            DebugService.Log("Creating profile model for update...")
            profile = TranscodeProfileModel(
                Id=profile_id,
                ProfileName=profile_name,
                Description=description,
                CreatedDate=existing_profile.CreatedDate,  # Preserve original CreatedDate
                LastModified=datetime.now()
            )
            DebugService.Log("Updating profile in database...")
            updated_profile = self.ProfileService.UpdateProfile(profile)
            DebugService.Log("Profile updated successfully with ID: {}", updated_profile.Id)
            
            # Delete existing thresholds
            DebugService.Log("Getting existing thresholds...")
            existing_thresholds = self.ProfileService.GetProfileThresholds(profile_id)
            DebugService.Log("Found {} existing thresholds to delete", len(existing_thresholds))
            for threshold in existing_thresholds:
                DebugService.Log("Deleting threshold ID: {}", threshold.Id)
                self.ProfileService.DeleteThreshold(threshold.Id)
            
            # Add new thresholds
            DebugService.Log("Adding {} new thresholds...", len(thresholds))
            for i, threshold_data in enumerate(thresholds):
                DebugService.Log("Adding threshold {}: {}", i+1, threshold_data)
                self.ProfileService.AddThreshold(
                    profile_id,
                    threshold_data['Resolution'],
                    threshold_data['Under30MinMB'],
                    threshold_data['Under65MinMB'],
                    threshold_data['Over65MinMB'],
                    threshold_data['VideoBitrateKbps'],
                    threshold_data['AudioBitrateKbps'],
                    threshold_data['FallbackVideoBitrateKbps'],
                    threshold_data['FallbackAudioBitrateKbps'],
                    threshold_data['TranscodeDownTo']
                )
                DebugService.Log("Threshold {} added successfully", i+1)
            
            # Reload profiles to get updated data
            DebugService.Log("Reloading profiles...")
            self.LoadProfiles()
            self.SuccessMessage = f"Profile '{profile_name}' updated successfully with {len(thresholds)} thresholds"
            self.ErrorMessage = ""
            DebugService.LogFunctionExit("UpdateProfileWithThresholds", True)
            return True
        except Exception as e:
            DebugService.LogException("Exception in UpdateProfileWithThresholds", e)
            self.ErrorMessage = f"Failed to update profile: {str(e)}"
            return False
    
    def DeleteProfile(self, profile_id: int) -> bool:
        """Delete a profile."""
        try:
            profile = next((p for p in self.Profiles if p.Id == profile_id), None)
            if not profile:
                self.ErrorMessage = "Profile not found"
                return False
            
            success = self.ProfileService.DeleteProfile(profile_id)
            if success:
                self.Profiles = [p for p in self.Profiles if p.Id != profile_id]
                if self.SelectedProfile and self.SelectedProfile.Id == profile_id:
                    self.SelectedProfile = None
                    self.SelectedProfileThresholds = []
                self.SuccessMessage = f"Profile '{profile.ProfileName}' deleted successfully"
                self.ErrorMessage = ""
                return True
            else:
                self.ErrorMessage = "Failed to delete profile"
                return False
        except Exception as e:
            self.ErrorMessage = f"Failed to delete profile: {str(e)}"
            return False
    
    def AddThreshold(self, profile_id: int, resolution: str, 
                    under_30_min_mb: int, under_65_min_mb: int, over_65_min_mb: int,
                    video_bitrate_kbps: int, audio_bitrate_kbps: int,
                    fallback_video_bitrate_kbps: int, fallback_audio_bitrate_kbps: int,
                    transcode_down_to: str) -> bool:
        """Add a threshold to a profile."""
        try:
            # Check if resolution already exists for this profile
            existing_thresholds = [t for t in self.SelectedProfileThresholds if t.Resolution.lower() == resolution.lower()]
            if existing_thresholds:
                self.ErrorMessage = f"Resolution '{resolution}' already exists for this profile"
                return False
            
            threshold = self.ProfileService.AddThreshold(
                profile_id, resolution, under_30_min_mb, under_65_min_mb, over_65_min_mb,
                video_bitrate_kbps, audio_bitrate_kbps, fallback_video_bitrate_kbps,
                fallback_audio_bitrate_kbps, transcode_down_to
            )
            
            self.SelectedProfileThresholds.append(threshold)
            self.SuccessMessage = f"Threshold for '{resolution}' added successfully"
            self.ErrorMessage = ""
            return True
        except Exception as e:
            self.ErrorMessage = f"Failed to add threshold: {str(e)}"
            return False
    
    def UpdateThreshold(self, threshold: ProfileThresholdModel) -> bool:
        """Update a threshold."""
        try:
            # Check if another threshold has the same resolution
            existing_thresholds = [t for t in self.SelectedProfileThresholds if t.Resolution.lower() == threshold.Resolution.lower() and t.Id != threshold.Id]
            if existing_thresholds:
                self.ErrorMessage = f"Resolution '{threshold.Resolution}' already exists for this profile"
                return False
            
            updated_threshold = self.ProfileService.UpdateThreshold(threshold)
            
            # Update the threshold in our list
            for i, t in enumerate(self.SelectedProfileThresholds):
                if t.Id == updated_threshold.Id:
                    self.SelectedProfileThresholds[i] = updated_threshold
                    break
            
            self.SuccessMessage = f"Threshold for '{threshold.Resolution}' updated successfully"
            self.ErrorMessage = ""
            return True
        except Exception as e:
            self.ErrorMessage = f"Failed to update threshold: {str(e)}"
            return False
    
    def DeleteThreshold(self, threshold_id: int) -> bool:
        """Delete a threshold."""
        try:
            threshold = next((t for t in self.SelectedProfileThresholds if t.Id == threshold_id), None)
            if not threshold:
                self.ErrorMessage = "Threshold not found"
                return False
            
            success = self.ProfileService.DeleteThreshold(threshold_id)
            if success:
                self.SelectedProfileThresholds = [t for t in self.SelectedProfileThresholds if t.Id != threshold_id]
                self.SuccessMessage = f"Threshold for '{threshold.Resolution}' deleted successfully"
                self.ErrorMessage = ""
                return True
            else:
                self.ErrorMessage = "Failed to delete threshold"
                return False
        except Exception as e:
            self.ErrorMessage = f"Failed to delete threshold: {str(e)}"
            return False
    
    def ClearMessages(self):
        """Clear error and success messages."""
        self.ErrorMessage = ""
        self.SuccessMessage = ""
    
    def GetProfilesAsDict(self) -> List[Dict[str, Any]]:
        """Get profiles as dictionaries for JSON serialization."""
        return [
            {
                'Id': profile.Id,
                'ProfileName': profile.ProfileName,
                'Description': profile.Description,
                'CreatedDate': profile.CreatedDate if profile.CreatedDate else None,
                'LastModified': profile.LastModified if profile.LastModified else None
            }
            for profile in self.Profiles
        ]
    
    def GetSelectedProfileAsDict(self) -> Optional[Dict[str, Any]]:
        """Get selected profile as dictionary for JSON serialization."""
        if not self.SelectedProfile:
            return None
        
        return {
            'Id': self.SelectedProfile.Id,
            'ProfileName': self.SelectedProfile.ProfileName,
            'Description': self.SelectedProfile.Description,
            'CreatedDate': self.SelectedProfile.CreatedDate if self.SelectedProfile.CreatedDate else None,
            'LastModified': self.SelectedProfile.LastModified if self.SelectedProfile.LastModified else None,
            'Thresholds': [
                {
                    'Id': threshold.Id,
                    'ProfileId': threshold.ProfileId,
                    'Resolution': threshold.Resolution,
                    'Under30MinMB': threshold.Under30MinMB,
                    'Under65MinMB': threshold.Under65MinMB,
                    'Over65MinMB': threshold.Over65MinMB,
                    'VideoBitrateKbps': threshold.VideoBitrateKbps,
                    'AudioBitrateKbps': threshold.AudioBitrateKbps,
                    'FallbackVideoBitrateKbps': threshold.FallbackVideoBitrateKbps,
                    'FallbackAudioBitrateKbps': threshold.FallbackAudioBitrateKbps,
                    'TranscodeDownTo': threshold.TranscodeDownTo
                }
                for threshold in self.SelectedProfileThresholds
            ]
        }
