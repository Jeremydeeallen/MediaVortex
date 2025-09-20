#!/usr/bin/env python3
"""
Simple script to add 4K (2160p) thresholds to existing profiles.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Repositories.DatabaseManager import DatabaseManager
from Models.ProfileThresholdModel import ProfileThresholdModel
from Services.LoggingService import LoggingService

def Add4KThresholds():
    """Add 4K (2160p) thresholds to all existing profiles."""
    try:
        LoggingService.LogInfo("Adding 4K thresholds to existing profiles", "Add4KThresholds", "MigrationScript")
        
        DatabaseManagerInstance = DatabaseManager()
        
        # Get all existing profiles
        Profiles = DatabaseManagerInstance.GetAllProfiles()
        LoggingService.LogInfo(f"Found {len(Profiles)} existing profiles", "Add4KThresholds", "MigrationScript")
        
        ProfilesUpdated = 0
        
        for Profile in Profiles:
            # Check if this profile already has 4K thresholds
            ExistingThresholds = DatabaseManagerInstance.GetThresholdsByProfileId(Profile.Id)
            Has4KThreshold = any(t.Resolution == "2160p" for t in ExistingThresholds)
            
            if Has4KThreshold:
                LoggingService.LogInfo(f"Profile '{Profile.ProfileName}' already has 4K thresholds, skipping", "Add4KThresholds", "MigrationScript")
                continue
            
            # Create 4K threshold with sensible defaults
            Threshold4K = ProfileThresholdModel(
                ProfileId=Profile.Id,
                Resolution="2160p",
                Under30MinMB=800,  # 4K files are typically larger
                Under65MinMB=1200,
                Over65MinMB=3000,
                VideoBitrateKbps=2000,  # Higher bitrate for 4K
                AudioBitrateKbps=128,   # Higher audio quality for 4K
                FallbackVideoBitrateKbps=1800,
                FallbackAudioBitrateKbps=128,
                TranscodeDownTo="1080p",  # Default downscaling to 1080p
                Quality=None  # Use bitrate mode by default
            )
            
            # Save the threshold
            ThresholdId = DatabaseManagerInstance.SaveThreshold(Threshold4K)
            LoggingService.LogInfo(f"Added 4K threshold (ID: {ThresholdId}) to profile '{Profile.ProfileName}'", "Add4KThresholds", "MigrationScript")
            ProfilesUpdated += 1
        
        LoggingService.LogInfo(f"Successfully added 4K thresholds to {ProfilesUpdated} profiles", "Add4KThresholds", "MigrationScript")
        return True
        
    except Exception as e:
        LoggingService.LogException("Error adding 4K thresholds", e, "Add4KThresholds", "MigrationScript")
        return False

if __name__ == "__main__":
    Success = Add4KThresholds()
    if Success:
        print("4K thresholds added successfully!")
        sys.exit(0)
    else:
        print("Failed to add 4K thresholds!")
        sys.exit(1)
