#!/usr/bin/env python3
"""
Add VR resolution thresholds to all existing profiles.
This script adds support for VR video transcoding with appropriate bitrate settings.
"""

import sys
import os

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Repositories.DatabaseManager import DatabaseManager
from Models.ProfileThresholdModel import ProfileThresholdModel
from Services.LoggingService import LoggingService

def AddVRThresholds():
    """Add VR resolution thresholds to all existing profiles."""
    try:
        LoggingService.LogInfo("Starting VR thresholds addition process", "AddVRThresholds", "MigrationScript")
        
        DatabaseManagerInstance = DatabaseManager()
        
        # Get all existing profiles
        Profiles = DatabaseManagerInstance.GetAllProfiles()
        if not Profiles:
            LoggingService.LogWarning("No profiles found in database", "AddVRThresholds", "MigrationScript")
            return False
        
        LoggingService.LogInfo(f"Found {len(Profiles)} profiles to update", "AddVRThresholds", "MigrationScript")
        
        ProfilesUpdated = 0
        
        for Profile in Profiles:
            # Check if this profile already has VR thresholds
            ExistingThresholds = DatabaseManagerInstance.GetThresholdsByProfileId(Profile.Id)
            HasVRThresholds = any(t.Resolution in ["7680x3840", "3840x3840", "5760x2880", "2880x2880"] for t in ExistingThresholds)
            
            if HasVRThresholds:
                LoggingService.LogInfo(f"Profile '{Profile.ProfileName}' already has VR thresholds, skipping", "AddVRThresholds", "MigrationScript")
                continue
            
            # Create VR thresholds with appropriate settings
            VRThresholds = [
                # 360° VR - High Resolution
                ProfileThresholdModel(
                    ProfileId=Profile.Id,
                    Resolution="7680x3840",  # 360° VR
                    Under30MinMB=2000,  # VR files are typically very large
                    Under65MinMB=3000,
                    Over65MinMB=5000,
                    VideoBitrateKbps=14000,  # High bitrate for 360° VR
                    AudioBitrateKbps=256,    # High audio quality for VR
                    FallbackVideoBitrateKbps=12000,
                    FallbackAudioBitrateKbps=192,
                    TranscodeDownTo="",      # No scaling for VR
                    Quality=23,              # Good quality
                    Grain=True               # Help with VR compression
                ),
                # 180° VR - High Resolution
                ProfileThresholdModel(
                    ProfileId=Profile.Id,
                    Resolution="3840x3840",  # 180° VR
                    Under30MinMB=1500,
                    Under65MinMB=2500,
                    Over65MinMB=4000,
                    VideoBitrateKbps=10000,  # Lower bitrate than 360° VR
                    AudioBitrateKbps=192,
                    FallbackVideoBitrateKbps=8000,
                    FallbackAudioBitrateKbps=128,
                    TranscodeDownTo="",      # No scaling for VR
                    Quality=24,
                    Grain=True
                ),
                # 360° VR - Medium Resolution
                ProfileThresholdModel(
                    ProfileId=Profile.Id,
                    Resolution="5760x2880",  # 360° VR (lower res)
                    Under30MinMB=1200,
                    Under65MinMB=2000,
                    Over65MinMB=3500,
                    VideoBitrateKbps=10000,
                    AudioBitrateKbps=192,
                    FallbackVideoBitrateKbps=8000,
                    FallbackAudioBitrateKbps=128,
                    TranscodeDownTo="",
                    Quality=24,
                    Grain=True
                ),
                # 180° VR - Medium Resolution
                ProfileThresholdModel(
                    ProfileId=Profile.Id,
                    Resolution="2880x2880",  # 180° VR (lower res)
                    Under30MinMB=800,
                    Under65MinMB=1500,
                    Over65MinMB=2500,
                    VideoBitrateKbps=8000,
                    AudioBitrateKbps=128,
                    FallbackVideoBitrateKbps=6000,
                    FallbackAudioBitrateKbps=96,
                    TranscodeDownTo="",
                    Quality=25,
                    Grain=True
                )
            ]
            
            # Save all VR thresholds for this profile
            for Threshold in VRThresholds:
                ThresholdId = DatabaseManagerInstance.SaveThreshold(Threshold)
                LoggingService.LogInfo(f"Added VR threshold '{Threshold.Resolution}' (ID: {ThresholdId}) to profile '{Profile.ProfileName}'", "AddVRThresholds", "MigrationScript")
            
            ProfilesUpdated += 1
        
        LoggingService.LogInfo(f"Successfully added VR thresholds to {ProfilesUpdated} profiles", "AddVRThresholds", "MigrationScript")
        return True
        
    except Exception as e:
        LoggingService.LogException("Error adding VR thresholds", e, "AddVRThresholds", "MigrationScript")
        return False

if __name__ == "__main__":
    Success = AddVRThresholds()
    if Success:
        print("VR thresholds added successfully!")
    else:
        print("Failed to add VR thresholds. Check logs for details.")
        sys.exit(1)
