#!/usr/bin/env python3
"""
Create a dedicated VR profile with optimized settings for VR video transcoding.
This profile is specifically designed for VR content with appropriate bitrate and quality settings.
"""

import sys
import os

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Repositories.DatabaseManager import DatabaseManager
from Models.ProfileThresholdModel import ProfileThresholdModel
from Models.TranscodeProfileModel import TranscodeProfileModel
from Services.LoggingService import LoggingService
from datetime import datetime

def CreateVRProfile():
    """Create a dedicated VR profile with optimized settings."""
    try:
        LoggingService.LogInfo("Starting VR profile creation process", "CreateVRProfile", "MigrationScript")
        
        DatabaseManagerInstance = DatabaseManager()
        
        # Check if VR profile already exists
        ExistingProfiles = DatabaseManagerInstance.GetAllProfiles()
        VRProfileExists = any(p.ProfileName == "VR" for p in ExistingProfiles)
        
        if VRProfileExists:
            LoggingService.LogInfo("VR profile already exists, skipping creation", "CreateVRProfile", "MigrationScript")
            return True
        
        # Create the VR profile
        VRProfile = TranscodeProfileModel(
            ProfileName="VR",
            Description="Optimized profile for VR video transcoding with appropriate bitrate and quality settings for immersive experiences",
            CreatedDate=datetime.now(),
            LastModified=datetime.now()
        )
        
        # Save the profile
        ProfileId = DatabaseManagerInstance.SaveProfile(VRProfile)
        LoggingService.LogInfo(f"Created VR profile with ID: {ProfileId}", "CreateVRProfile", "MigrationScript")
        
        # Create VR-specific thresholds
        VRThresholds = [
            # 360° VR - High Resolution (7680x3840)
            ProfileThresholdModel(
                ProfileId=ProfileId,
                Resolution="7680x3840",
                Under30MinMB=2000,
                Under65MinMB=3000,
                Over65MinMB=5000,
                VideoBitrateKbps=14000,  # 14 Mbps for high-quality 360° VR
                AudioBitrateKbps=256,    # High audio quality for immersive experience
                FallbackVideoBitrateKbps=12000,
                FallbackAudioBitrateKbps=192,
                TranscodeDownTo="",      # No scaling - keep original resolution
                Quality=23,              # High quality
                Grain=True               # Help with VR compression artifacts
            ),
            # 180° VR - High Resolution (3840x3840)
            ProfileThresholdModel(
                ProfileId=ProfileId,
                Resolution="3840x3840",
                Under30MinMB=1500,
                Under65MinMB=2500,
                Over65MinMB=4000,
                VideoBitrateKbps=10000,  # 10 Mbps for 180° VR
                AudioBitrateKbps=192,
                FallbackVideoBitrateKbps=8000,
                FallbackAudioBitrateKbps=128,
                TranscodeDownTo="",
                Quality=24,
                Grain=True
            ),
            # 360° VR - Medium Resolution (5760x2880)
            ProfileThresholdModel(
                ProfileId=ProfileId,
                Resolution="5760x2880",
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
            # 180° VR - Medium Resolution (2880x2880)
            ProfileThresholdModel(
                ProfileId=ProfileId,
                Resolution="2880x2880",
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
            ),
            # Standard resolutions for VR content that might be in different formats
            ProfileThresholdModel(
                ProfileId=ProfileId,
                Resolution="2160p",
                Under30MinMB=1000,
                Under65MinMB=2000,
                Over65MinMB=3000,
                VideoBitrateKbps=8000,
                AudioBitrateKbps=128,
                FallbackVideoBitrateKbps=6000,
                FallbackAudioBitrateKbps=96,
                TranscodeDownTo="",
                Quality=25,
                Grain=True
            ),
            ProfileThresholdModel(
                ProfileId=ProfileId,
                Resolution="1080p",
                Under30MinMB=500,
                Under65MinMB=1000,
                Over65MinMB=1500,
                VideoBitrateKbps=4000,
                AudioBitrateKbps=128,
                FallbackVideoBitrateKbps=3000,
                FallbackAudioBitrateKbps=96,
                TranscodeDownTo="",
                Quality=26,
                Grain=True
            )
        ]
        
        # Save all thresholds
        for Threshold in VRThresholds:
            ThresholdId = DatabaseManagerInstance.SaveThreshold(Threshold)
            LoggingService.LogInfo(f"Added VR threshold '{Threshold.Resolution}' (ID: {ThresholdId}) to VR profile", "CreateVRProfile", "MigrationScript")
        
        LoggingService.LogInfo("Successfully created VR profile with all thresholds", "CreateVRProfile", "MigrationScript")
        return True
        
    except Exception as e:
        LoggingService.LogException("Error creating VR profile", e, "CreateVRProfile", "MigrationScript")
        return False

if __name__ == "__main__":
    Success = CreateVRProfile()
    if Success:
        print("VR profile created successfully!")
    else:
        print("Failed to create VR profile. Check logs for details.")
        sys.exit(1)
