#!/usr/bin/env python3
"""
Test script to debug audio settings in SystemSettings.
"""

import os
import sys
from pathlib import Path

# Add the project root to the Python path
ProjectRoot = Path(__file__).parent.parent
sys.path.insert(0, str(ProjectRoot))

from Repositories.DatabaseManager import DatabaseManager
from Models.CommandBuilder import CommandBuilder
from Models.TranscodeQueueModel import TranscodeQueueModel
from Models.MediaFileModel import MediaFileModel


def TestSystemSettings():
    """Test if SystemSettings are being read correctly."""
    print("Testing SystemSettings for Audio Compression...")
    print("=" * 50)
    
    try:
        DatabaseManagerInstance = DatabaseManager()
        
        # Check all audio-related settings
        AudioSettings = [
            'AudioCompressionEnabled',
            'AudioNormalizationEnabled', 
            'CompressionThreshold',
            'CompressionRatio',
            'CompressionAttack',
            'CompressionRelease',
            'CompressionMakeup',
            'TargetLoudness',
            'LoudnessRange',
            'TruePeak'
        ]
        
        print("Current SystemSettings:")
        for Setting in AudioSettings:
            Value = DatabaseManagerInstance.GetSystemSetting(Setting)
            print(f"  {Setting}: {Value}")
        
        print("\n" + "=" * 50)
        
        # Test CommandBuilder
        print("Testing CommandBuilder...")
        
        # Create mock data
        Job = TranscodeQueueModel(
            Id=1,
            FilePath="test.mkv",
            FileName="test.mkv",
            Directory="test",
            SizeBytes=1000000,
            SizeMB=1.0,
            Priority=1,
            Status="Pending",
            DateAdded="2024-01-01 12:00:00",
            DateStarted=None
        )
        
        MediaFile = MediaFileModel(
            Id=1,
            SeasonId=1,
            FilePath="test.mkv",
            FileName="test.mkv",
            SizeMB=1.0,
            VideoBitrateKbps=5000,
            AudioBitrateKbps=128,
            Resolution="1080p",
            Codec="h264",
            DurationMinutes=120.0,
            FrameRate=23.976,
            LastScannedDate=None,
            CompressionPotential="High",
            AssignedProfile="HighQuality",
            IsInterlaced=False,
            ResolutionCategory="HD",
            FileModificationTime=None,
            TotalFrames=172800,
            CodecProfile="High",
            ColorRange="Limited",
            FieldOrder="Progressive",
            HasBFrames=1,
            RefFrames=3,
            PixelFormat="yuv420p",
            Level=40,
            AudioChannels=2,
            AudioSampleRate=48000,
            AudioSampleFormat="fltp",
            AudioChannelLayout="stereo",
            ContainerFormat="matroska",
            OverallBitrate=5128,
            TranscodedByMediaVortex=False
        )
        
        ProfileSettings = {
            'Codec': 'libsvtav1',
            'Quality': 25,
            'AudioBitrateKbps': 96,
            'ContainerType': 'mp4'
        }
        
        CommandData = {
            'Job': Job,
            'MediaFile': MediaFile,
            'ProfileSettings': ProfileSettings,
            'CodecFlags': {},
            'CodecParameters': [],
            'SourceResolution': '1080p',
            'TargetResolution': '720p',
            'ScaleFilter': 'scale=1280:720'
        }
        
        # Test CommandBuilder
        CommandBuilderInstance = CommandBuilder()
        Command = CommandBuilderInstance.BuildCommand(CommandData)
        
        print(f"Generated Command:\n{Command}")
        
        # Check if audio filters are included
        if '-af' in Command:
            print("\n✅ Audio filters ARE included in the command!")
        else:
            print("\n❌ Audio filters are NOT included in the command!")
            
        return True
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    TestSystemSettings()
