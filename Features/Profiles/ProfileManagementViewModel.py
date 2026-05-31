from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from Features.Profiles.Models.TranscodeProfileModel import TranscodeProfileModel
from Features.Profiles.Models.ProfileThresholdModel import ProfileThresholdModel
from Features.Profiles.ProfileService import ProfileService
from Core.Logging.LoggingService import LoggingService


# directive: nvenc-rate-anchored-remediation
class ProfileManagementViewModel:
    """ViewModel for managing transcoding profiles in the UI."""

    # directive: nvenc-rate-anchored-remediation
    def __init__(self, profile_service: ProfileService = None):
        self.ProfileService = profile_service or ProfileService()
        self.Profiles: List[TranscodeProfileModel] = []
        self.SelectedProfile: Optional[TranscodeProfileModel] = None
        self.SelectedProfileThresholds: List[ProfileThresholdModel] = []
        self.ErrorMessage: str = ""
        self.SuccessMessage: str = ""

    # directive: nvenc-rate-anchored-remediation
    def LoadProfiles(self) -> bool:
        """Load all profiles from the database."""
        try:
            self.Profiles = self.ProfileService.GetAllProfiles()
            self.ErrorMessage = ""
            return True
        except Exception as e:
            self.ErrorMessage = f"Failed to load profiles: {str(e)}"
            return False

    # directive: nvenc-rate-anchored-remediation
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

    # directive: nvenc-rate-anchored-remediation
    def CreateProfile(self, profile_name: str, description: str = "") -> bool:
        """Create a new profile."""
        try:
            if not profile_name.strip():
                self.ErrorMessage = "Profile name is required"
                return False

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

    # directive: nvenc-rate-anchored-remediation
    def CreateProfileWithThresholds(self, profile_name: str, description: str, thresholds: List[dict],
                                   codec: str = "libsvtav1", preset: int = 6, film_grain: int = 10,
                                   yadif_mode: int = 1, yadif_parity: int = 1, yadif_deint: int = 1,
                                   use_nvidia_hardware: int = 0) -> bool:
        """Create a new profile with multiple thresholds."""
        try:
            LoggingService.LogFunctionEntry("CreateProfileWithThresholds", "ProfileManagementViewModel", profile_name, description, len(thresholds))
            LoggingService.LogInfo(f"Thresholds data: {thresholds}", "ProfileManagementViewModel", "CreateProfileWithThresholds")

            if not profile_name.strip():
                self.ErrorMessage = "Profile name is required"
                return False

            existing_profiles = [p for p in self.Profiles if p.ProfileName.lower() == profile_name.lower()]
            if existing_profiles:
                self.ErrorMessage = "A profile with this name already exists"
                return False

            LoggingService.LogInfo("Creating profile...", "ProfileManagementViewModel", "CreateProfileWithThresholds")
            new_profile = self.ProfileService.CreateProfile(profile_name, description, codec, preset, film_grain, yadif_mode, yadif_parity, yadif_deint, use_nvidia_hardware)
            LoggingService.LogInfo(f"Profile created with ID: {new_profile.Id}", "ProfileManagementViewModel", "CreateProfileWithThresholds")

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

    # directive: nvenc-rate-anchored-remediation
    def UpdateProfile(self, profile: TranscodeProfileModel) -> bool:
        """Update an existing profile."""
        try:
            if not profile.ProfileName.strip():
                self.ErrorMessage = "Profile name is required"
                return False

            existing_profiles = [p for p in self.Profiles if p.ProfileName.lower() == profile.ProfileName.lower() and p.Id != profile.Id]
            if existing_profiles:
                self.ErrorMessage = "A profile with this name already exists"
                return False

            updated_profile = self.ProfileService.UpdateProfile(profile)

            for i, p in enumerate(self.Profiles):
                if p.Id == updated_profile.Id:
                    self.Profiles[i] = updated_profile
                    break

            if self.SelectedProfile and self.SelectedProfile.Id == updated_profile.Id:
                self.SelectedProfile = updated_profile

            self.SuccessMessage = f"Profile '{profile.ProfileName}' updated successfully"
            self.ErrorMessage = ""
            return True
        except Exception as e:
            self.ErrorMessage = f"Failed to update profile: {str(e)}"
            return False

    # directive: nvenc-rate-anchored-remediation
    def UpdateProfileWithThresholds(self, profile_id: int, profile_name: str, description: str, thresholds: List[dict],
                                   codec: str = "libsvtav1", preset: int = 6, film_grain: int = 10,
                                   yadif_mode: int = 1, yadif_parity: int = 1, yadif_deint: int = 1,
                                   use_nvidia_hardware: int = 0) -> bool:
        """Update an existing profile with multiple thresholds."""
        try:
            LoggingService.LogFunctionEntry("UpdateProfileWithThresholds", "ProfileManagementViewModel", profile_id, profile_name, description, len(thresholds))
            LoggingService.LogInfo(f"Thresholds data: {thresholds}", "ProfileManagementViewModel", "UpdateProfileWithThresholds")

            if not profile_name.strip():
                self.ErrorMessage = "Profile name is required"
                LoggingService.LogInfo("Profile name validation failed")
                return False

            existing_profiles = [p for p in self.Profiles if p.ProfileName.lower() == profile_name.lower() and p.Id != profile_id]
            if existing_profiles:
                self.ErrorMessage = "A profile with this name already exists"
                LoggingService.LogInfo("Profile name already exists")
                return False

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
                CreatedDate=existing_profile.CreatedDate,
                LastModified=datetime.now(timezone.utc),
                Codec=codec,
                Preset=preset,
                FilmGrain=film_grain,
                YadifMode=yadif_mode,
                YadifParity=yadif_parity,
                YadifDeint=yadif_deint,
                UseNvidiaHardware=use_nvidia_hardware
            )
            LoggingService.LogInfo("Updating profile in database...")
            updated_profile = self.ProfileService.UpdateProfile(profile)
            LoggingService.LogInfo(f"Profile updated successfully with ID: {updated_profile.Id}", "UpdateProfileWithThresholds", "ProfileManagementViewModel")

            LoggingService.LogInfo("Getting existing thresholds...")
            ExistingThresholds = self.ProfileService.GetProfileThresholds(profile_id)
            LoggingService.LogInfo(f"Found {len(ExistingThresholds)} existing thresholds", "UpdateProfileWithThresholds", "ProfileManagementViewModel")

            ExistingThresholdMap = {t.Resolution: t for t in ExistingThresholds}
            NewThresholdMap = {t['Resolution']: t for t in thresholds}

            UpdatedCount = 0
            for resolution, threshold_data in NewThresholdMap.items():
                if resolution in ExistingThresholdMap:
                    ExistingThreshold = ExistingThresholdMap[resolution]
                    LoggingService.LogInfo(f"Updating existing threshold for {resolution} (ID: {ExistingThreshold.Id})", "UpdateProfileWithThresholds", "ProfileManagementViewModel")

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

            DeletedCount = 0
            for resolution, existing_threshold in ExistingThresholdMap.items():
                if resolution not in NewThresholdMap:
                    LoggingService.LogInfo(f"Deleting threshold for {resolution} (ID: {existing_threshold.Id})", "UpdateProfileWithThresholds", "ProfileManagementViewModel")
                    self.ProfileService.DeleteThreshold(existing_threshold.Id)
                    DeletedCount += 1

            LoggingService.LogInfo(f"Threshold update complete: {UpdatedCount} updated, {len(NewThresholdMap) - UpdatedCount} added, {DeletedCount} deleted", "UpdateProfileWithThresholds", "ProfileManagementViewModel")

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

    # directive: nvenc-rate-anchored-remediation
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

    # directive: nvenc-rate-anchored-remediation
    def AddThreshold(self, profile_id: int, resolution: str,
                    under_30_min_mb: int, under_65_min_mb: int, over_65_min_mb: int,
                    video_bitrate_kbps: int, audio_bitrate_kbps: int,
                    fallback_video_bitrate_kbps: int, fallback_audio_bitrate_kbps: int,
                    transcode_down_to: str, quality: int = None) -> bool:
        """Add a threshold to a profile."""
        try:
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

    # directive: nvenc-rate-anchored-remediation
    def UpdateThreshold(self, threshold: ProfileThresholdModel) -> bool:
        """Update a threshold."""
        try:
            existing_thresholds = [t for t in self.SelectedProfileThresholds if t.Resolution.lower() == threshold.Resolution.lower() and t.Id != threshold.Id]
            if existing_thresholds:
                self.ErrorMessage = f"Resolution '{threshold.Resolution}' already exists for this profile"
                return False

            updated_threshold = self.ProfileService.UpdateThreshold(threshold)

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

    # directive: nvenc-rate-anchored-remediation
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

    # directive: nvenc-rate-anchored-remediation
    def ClearMessages(self):
        """Clear error and success messages."""
        self.ErrorMessage = ""
        self.SuccessMessage = ""

    # directive: nvenc-rate-anchored-remediation
    def GetProfilesAsDict(self) -> List[Dict[str, Any]]:
        """Profile list including lifted NVENC knob columns (Tune, Multipass, PixelFormat, Audio*, Container, FastStart)."""
        from Core.Database.DatabaseService import DatabaseService
        Db = DatabaseService()
        KnobRows = Db.ExecuteQuery(
            "SELECT Id, Tune, Multipass, PixelFormat, AudioCodec, AudioBitrateKbps, "
            "       AudioChannels, AudioFilter, Container, FastStart, RateControlMode "
            "FROM Profiles",
            (),
        )
        KnobsByProfileId = {Row['Id']: Row for Row in KnobRows}

        Result = []
        for profile in self.Profiles:
            Extra = KnobsByProfileId.get(profile.Id, {})
            Result.append({
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
                'YadifDeint': profile.YadifDeint,
                'UseNvidiaHardware': profile.UseNvidiaHardware,
                'SortOrder': profile.SortOrder,
                'Tune': Extra.get('Tune'),
                'Multipass': Extra.get('Multipass'),
                'PixelFormat': Extra.get('PixelFormat'),
                'AudioCodec': Extra.get('AudioCodec'),
                'AudioBitrateKbps': Extra.get('AudioBitrateKbps'),
                'AudioChannels': Extra.get('AudioChannels'),
                'AudioFilter': Extra.get('AudioFilter'),
                'Container': Extra.get('Container'),
                'FastStart': Extra.get('FastStart'),
                'RateControlMode': Extra.get('RateControlMode'),
            })
        return Result

    # directive: nvenc-rate-anchored-remediation
    def GetSelectedProfileAsDict(self) -> Optional[Dict[str, Any]]:
        """Selected profile + thresholds including every lifted NVENC knob column."""
        if not self.SelectedProfile:
            return None

        from Core.Database.DatabaseService import DatabaseService
        Db = DatabaseService()
        Pid = self.SelectedProfile.Id
        ProfileExtras = Db.ExecuteQuery(
            "SELECT Tune, Multipass, PixelFormat, AudioCodec, AudioBitrateKbps, "
            "       AudioChannels, AudioFilter, Container, FastStart, RateControlMode "
            "FROM Profiles WHERE Id = %s",
            (Pid,),
        )
        ProfileExtra = ProfileExtras[0] if ProfileExtras else {}

        ThresholdExtras = Db.ExecuteQuery(
            "SELECT Id, RcLookahead, BFrames, BRefMode, ScaleHeight, PreserveAspect, "
            "       MaxBitrateMultiplier, SourceBitratePercent, MinBitrateKbps, "
            "       MaxBitrateKbps, Gop "
            "FROM ProfileThresholds WHERE ProfileId = %s",
            (Pid,),
        )
        ExtraByThresholdId = {Row['Id']: Row for Row in ThresholdExtras}

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
            'UseNvidiaHardware': self.SelectedProfile.UseNvidiaHardware,
            'Tune': ProfileExtra.get('Tune'),
            'Multipass': ProfileExtra.get('Multipass'),
            'PixelFormat': ProfileExtra.get('PixelFormat'),
            'AudioCodec': ProfileExtra.get('AudioCodec'),
            'AudioBitrateKbps': ProfileExtra.get('AudioBitrateKbps'),
            'AudioChannels': ProfileExtra.get('AudioChannels'),
            'AudioFilter': ProfileExtra.get('AudioFilter'),
            'Container': ProfileExtra.get('Container'),
            'FastStart': ProfileExtra.get('FastStart'),
            'RateControlMode': ProfileExtra.get('RateControlMode'),
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
                    'Quality': threshold.Quality,
                    'RcLookahead': ExtraByThresholdId.get(threshold.Id, {}).get('RcLookahead'),
                    'BFrames': ExtraByThresholdId.get(threshold.Id, {}).get('BFrames'),
                    'BRefMode': ExtraByThresholdId.get(threshold.Id, {}).get('BRefMode'),
                    'ScaleHeight': ExtraByThresholdId.get(threshold.Id, {}).get('ScaleHeight'),
                    'PreserveAspect': ExtraByThresholdId.get(threshold.Id, {}).get('PreserveAspect'),
                    'MaxBitrateMultiplier': float(ExtraByThresholdId.get(threshold.Id, {}).get('MaxBitrateMultiplier')) if ExtraByThresholdId.get(threshold.Id, {}).get('MaxBitrateMultiplier') is not None else None,
                    'SourceBitratePercent': ExtraByThresholdId.get(threshold.Id, {}).get('SourceBitratePercent'),
                    'MinBitrateKbps': ExtraByThresholdId.get(threshold.Id, {}).get('MinBitrateKbps'),
                    'MaxBitrateKbps': ExtraByThresholdId.get(threshold.Id, {}).get('MaxBitrateKbps'),
                    'Gop': ExtraByThresholdId.get(threshold.Id, {}).get('Gop'),
                }
                for threshold in self.SelectedProfileThresholds
            ]
        }

    # directive: nvenc-rate-anchored-remediation
    def AssignProfileToRootFolder(self, RootFolderPath: str, ProfileId: int) -> Dict[str, Any]:
        """Assign a profile to all media files in a specific root folder."""
        try:
            LoggingService.LogFunctionEntry("AssignProfileToRootFolder", "ProfileManagementViewModel", RootFolderPath, ProfileId)

            self.ErrorMessage = ""
            self.SuccessMessage = ""

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
