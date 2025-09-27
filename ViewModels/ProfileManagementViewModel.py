from typing import List, Optional, Dict, Any
from datetime import datetime
from Models.TranscodeProfileModel import TranscodeProfileModel
from Models.ProfileThresholdModel import ProfileThresholdModel
from Services.ProfileService import ProfileService
from Services.LoggingService import LoggingService


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
    
    def CreateProfileWithThresholds(self, profile_name: str, description: str, thresholds: List[dict],
                                   codec: str = "libsvtav1", preset: int = 6, film_grain: int = 10,
                                   ten_bit_encoding: bool = False, yadif_mode: int = 1, yadif_parity: int = 1, yadif_deint: int = 1) -> bool:
        """Create a new profile with multiple thresholds."""
        try:
            LoggingService.LogFunctionEntry("CreateProfileWithThresholds", "ProfileManagementViewModel", profile_name, description, len(thresholds))
            LoggingService.LogInfo(f"Thresholds data: {thresholds}", "ProfileManagementViewModel", "CreateProfileWithThresholds")
            
            if not profile_name.strip():
                self.ErrorMessage = "Profile name is required"
                return False
            
            # Check if profile name already exists
            existing_profiles = [p for p in self.Profiles if p.ProfileName.lower() == profile_name.lower()]
            if existing_profiles:
                self.ErrorMessage = "A profile with this name already exists"
                return False
            
            # Create the profile first
            LoggingService.LogInfo("Creating profile...", "ProfileManagementViewModel", "CreateProfileWithThresholds")
            new_profile = self.ProfileService.CreateProfile(profile_name, description, codec, preset, film_grain, ten_bit_encoding, yadif_mode, yadif_parity, yadif_deint)
            LoggingService.LogInfo(f"Profile created with ID: {new_profile.Id}", "ProfileManagementViewModel", "CreateProfileWithThresholds")
            
            # Add all thresholds
            LoggingService.LogInfo(f"Adding {len(thresholds)} thresholds...", "ProfileManagementViewModel", "CreateProfileWithThresholds")
            for i, threshold_data in enumerate(thresholds):
                LoggingService.LogInfo(f"Adding threshold {i+1}: {threshold_data}", "ProfileManagementViewModel", "CreateProfileWithThresholds")
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
                    threshold_data['TranscodeDownTo'],
                    threshold_data.get('Quality'),
                )
                LoggingService.LogInfo(f"Threshold {i+1} added successfully", "ProfileManagementViewModel", "CreateProfileWithThresholds")
            
            # Reload profiles to get updated data
            LoggingService.LogInfo("Reloading profiles...", "ProfileManagementViewModel", "CreateProfileWithThresholds")
            self.LoadProfiles()
            self.SuccessMessage = f"Profile '{profile_name}' created successfully with {len(thresholds)} thresholds"
            self.ErrorMessage = ""
            LoggingService.LogFunctionExit("CreateProfileWithThresholds", "ProfileManagementViewModel", True)
            return True
        except Exception as e:
            LoggingService.LogException("Exception in CreateProfileWithThresholds", e, "ProfileManagementViewModel", "CreateProfileWithThresholds")
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
    
    def UpdateProfileWithThresholds(self, profile_id: int, profile_name: str, description: str, thresholds: List[dict],
                                   codec: str = "libsvtav1", preset: int = 6, film_grain: int = 10,
                                   ten_bit_encoding: bool = False, yadif_mode: int = 1, yadif_parity: int = 1, yadif_deint: int = 1) -> bool:
        """Update an existing profile with multiple thresholds."""
        try:
            LoggingService.LogFunctionEntry("UpdateProfileWithThresholds", "ProfileManagementViewModel", profile_id, profile_name, description, len(thresholds))
            LoggingService.LogInfo(f"Thresholds data: {thresholds}", "ProfileManagementViewModel", "UpdateProfileWithThresholds")
            
            if not profile_name.strip():
                self.ErrorMessage = "Profile name is required"
                LoggingService.LogInfo("Profile name validation failed")
                return False
            
            # Check if another profile has the same name
            existing_profiles = [p for p in self.Profiles if p.ProfileName.lower() == profile_name.lower() and p.Id != profile_id]
            if existing_profiles:
                self.ErrorMessage = "A profile with this name already exists"
                LoggingService.LogInfo("Profile name already exists")
                return False
            
            # Update the profile - get existing profile to preserve CreatedDate
            LoggingService.LogInfo("Getting existing profile to preserve CreatedDate...")
            existing_profile = self.ProfileService.GetProfileById(profile_id)
            if not existing_profile:
                self.ErrorMessage = f"Profile with ID {profile_id} not found"
                LoggingService.LogInfo("Profile not found for update")
                return False
            
            LoggingService.LogInfo("Creating profile model for update...")
            profile = TranscodeProfileModel(
                Id=profile_id,
                ProfileName=profile_name,
                Description=description,
                CreatedDate=existing_profile.CreatedDate,  # Preserve original CreatedDate
                LastModified=datetime.now(),
                Codec=codec,
                Preset=preset,
                FilmGrain=film_grain,
                TenBitEncoding=ten_bit_encoding,
                YadifMode=yadif_mode,
                YadifParity=yadif_parity,
                YadifDeint=yadif_deint
            )
            LoggingService.LogInfo("Updating profile in database...")
            updated_profile = self.ProfileService.UpdateProfile(profile)
            LoggingService.LogInfo(f"Profile updated successfully with ID: {updated_profile.Id}", "UpdateProfileWithThresholds", "ProfileManagementViewModel")
            
            # Update thresholds efficiently
            LoggingService.LogInfo("Getting existing thresholds...")
            ExistingThresholds = self.ProfileService.GetProfileThresholds(profile_id)
            LoggingService.LogInfo(f"Found {len(ExistingThresholds)} existing thresholds", "UpdateProfileWithThresholds", "ProfileManagementViewModel")
            
            # Create lookup maps for efficient comparison
            ExistingThresholdMap = {t.Resolution: t for t in ExistingThresholds}
            NewThresholdMap = {t['Resolution']: t for t in thresholds}
            
            # Update existing thresholds that match resolution
            UpdatedCount = 0
            for resolution, threshold_data in NewThresholdMap.items():
                if resolution in ExistingThresholdMap:
                    # Update existing threshold
                    ExistingThreshold = ExistingThresholdMap[resolution]
                    LoggingService.LogInfo(f"Updating existing threshold for {resolution} (ID: {ExistingThreshold.Id})", "UpdateProfileWithThresholds", "ProfileManagementViewModel")
                    
                    # Create updated threshold model
                    UpdatedThreshold = ProfileThresholdModel(
                        Id=ExistingThreshold.Id,
                        ProfileId=profile_id,
                        Resolution=threshold_data['Resolution'],
                        Under30MinMB=threshold_data['Under30MinMB'],
                        Under65MinMB=threshold_data['Under65MinMB'],
                        Over65MinMB=threshold_data['Over65MinMB'],
                        VideoBitrateKbps=threshold_data['VideoBitrateKbps'],
                        AudioBitrateKbps=threshold_data['AudioBitrateKbps'],
                        FallbackVideoBitrateKbps=threshold_data['FallbackVideoBitrateKbps'],
                        FallbackAudioBitrateKbps=threshold_data['FallbackAudioBitrateKbps'],
                        TranscodeDownTo=threshold_data['TranscodeDownTo'],
                        Quality=threshold_data.get('Quality')
                    )
                    
                    self.ProfileService.UpdateThreshold(UpdatedThreshold)
                    UpdatedCount += 1
                else:
                    # Add new threshold
                    LoggingService.LogInfo(f"Adding new threshold for {resolution}", "UpdateProfileWithThresholds", "ProfileManagementViewModel")
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
                        threshold_data['TranscodeDownTo'],
                        threshold_data.get('Quality')
                    )
            
            # Delete thresholds that no longer exist
            DeletedCount = 0
            for resolution, existing_threshold in ExistingThresholdMap.items():
                if resolution not in NewThresholdMap:
                    LoggingService.LogInfo(f"Deleting threshold for {resolution} (ID: {existing_threshold.Id})", "UpdateProfileWithThresholds", "ProfileManagementViewModel")
                    self.ProfileService.DeleteThreshold(existing_threshold.Id)
                    DeletedCount += 1
            
            LoggingService.LogInfo(f"Threshold update complete: {UpdatedCount} updated, {len(NewThresholdMap) - UpdatedCount} added, {DeletedCount} deleted", "UpdateProfileWithThresholds", "ProfileManagementViewModel")
            
            # Reload profiles to get updated data
            LoggingService.LogInfo("Reloading profiles...", "ProfileManagementViewModel", "CreateProfileWithThresholds")
            self.LoadProfiles()
            self.SuccessMessage = f"Profile '{profile_name}' updated successfully with {len(thresholds)} thresholds"
            self.ErrorMessage = ""
            LoggingService.LogFunctionExit("UpdateProfileWithThresholds", True)
            return True
        except Exception as e:
            LoggingService.LogException("Exception in UpdateProfileWithThresholds", e)
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
                    transcode_down_to: str, quality: int = None) -> bool:
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
                fallback_audio_bitrate_kbps, transcode_down_to, quality
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
                'LastModified': profile.LastModified if profile.LastModified else None,
                'Codec': profile.Codec,
                'Preset': profile.Preset,
                'FilmGrain': profile.FilmGrain,
                'YadifMode': profile.YadifMode,
                'YadifParity': profile.YadifParity,
                'YadifDeint': profile.YadifDeint
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
            'Codec': self.SelectedProfile.Codec,
            'Preset': self.SelectedProfile.Preset,
            'FilmGrain': self.SelectedProfile.FilmGrain,
            'YadifMode': self.SelectedProfile.YadifMode,
            'YadifParity': self.SelectedProfile.YadifParity,
            'YadifDeint': self.SelectedProfile.YadifDeint,
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
                    'TranscodeDownTo': threshold.TranscodeDownTo,
                    'Quality': threshold.Quality
                }
                for threshold in self.SelectedProfileThresholds
            ]
        }
    
    def AssignProfileToRootFolder(self, RootFolderPath: str, ProfileId: int) -> Dict[str, Any]:
        """Assign a profile to all media files in a specific root folder."""
        try:
            LoggingService.LogFunctionEntry("AssignProfileToRootFolder", "ProfileManagementViewModel", RootFolderPath, ProfileId)
            
            self.ErrorMessage = ""
            self.SuccessMessage = ""
            
            # Call business service
            result = self.ProfileService.AssignProfileToRootFolder(RootFolderPath, ProfileId)
            
            if result.get("Success", False):
                self.SuccessMessage = result.get("Message", "Profile assigned successfully")
                LoggingService.LogInfo(f"Profile assignment successful: {self.SuccessMessage}", "ProfileManagementViewModel", "AssignProfileToRootFolder")
            else:
                self.ErrorMessage = result.get("ErrorMessage", "Failed to assign profile")
                LoggingService.LogError(self.ErrorMessage, "ProfileManagementViewModel", "AssignProfileToRootFolder")
            
            return result
            
        except Exception as e:
            errorMsg = f"Exception assigning profile to root folder: {str(e)}"
            self.ErrorMessage = errorMsg
            LoggingService.LogException(errorMsg, e, "ProfileManagementViewModel", "AssignProfileToRootFolder")
            return {"Success": False, "ErrorMessage": errorMsg, "FilesUpdated": 0}