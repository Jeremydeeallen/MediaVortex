#!/usr/bin/env python3
"""
Test script to demonstrate audio normalization functionality.
This script shows how the CommandBuilder will generate FFmpeg commands with audio normalization.
"""

import os
import sys
from pathlib import Path

# Add the project root to the Python path
ProjectRoot = Path(__file__).parent.parent
sys.path.insert(0, str(ProjectRoot))

from Models.CommandBuilder import CommandBuilder
from Models.TranscodeQueueModel import TranscodeQueueModel
from Models.MediaFileModel import MediaFileModel


def TestAudioNormalizationCommands():
    """Test the CommandBuilder with different audio normalization settings."""
    
    print("MediaVortex Audio Normalization Test")
    print("=" * 50)
    
    # Create a mock job and media file
    Job = TranscodeQueueModel(
        Id=1,
        FilePath="C:\\Test\\SampleVideo.mkv",
        FileName="SampleVideo.mkv",
        Directory="C:\\Test",
        SizeBytes=1000000000,
        SizeMB=1000.0,
        Priority=1,
        Status="Pending",
        DateAdded="2024-01-01 12:00:00",
        DateStarted=None
    )
    
    MediaFile = MediaFileModel(
        Id=1,
        SeasonId=1,
        FilePath="C:\\Test\\SampleVideo.mkv",
        FileName="SampleVideo.mkv",
        SizeMB=1000.0,
        VideoBitrateKbps=5000,
        AudioBitrateKbps=128,
        Resolution="1080p",
        Codec="h264",
        DurationMinutes=120.0,
        FrameRate=23.976,
        LastScannedDate=None,  # Will be set by __post_init__
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
    
    CommandBuilderInstance = CommandBuilder()
    
    # Test Case 1: Audio normalization disabled (current behavior)
    print("\n1. Audio Normalization DISABLED (Current Behavior):")
    print("-" * 50)
    
    ProfileSettings1 = {
        'Codec': 'libsvtav1',
        'Quality': 25,
        'AudioBitrateKbps': 128,
        'ContainerType': 'mp4',
        'AudioNormalizationEnabled': False,  # Disabled
        'TargetLoudness': -23,
        'LoudnessRange': 7,
        'TruePeak': -2
    }
    
    CommandData1 = {
        'Job': Job,
        'MediaFile': MediaFile,
        'ProfileSettings': ProfileSettings1,
        'CodecFlags': {},
        'CodecParameters': [],
        'SourceResolution': '1080p',
        'TargetResolution': '1080p',
        'ScaleFilter': None
    }
    
    Command1 = CommandBuilderInstance.BuildCommand(CommandData1)
    print(f"Generated Command:\n{Command1}")
    
    # Test Case 2: Audio normalization enabled with EBU R128 standard
    print("\n2. Audio Normalization ENABLED (EBU R128 Standard):")
    print("-" * 50)
    
    ProfileSettings2 = {
        'Codec': 'libsvtav1',
        'Quality': 25,
        'AudioBitrateKbps': 128,
        'ContainerType': 'mp4',
        'AudioNormalizationEnabled': True,   # Enabled
        'TargetLoudness': -23,               # EBU R128 standard
        'LoudnessRange': 7,                  # EBU R128 standard
        'TruePeak': -2                       # EBU R128 standard
    }
    
    CommandData2 = {
        'Job': Job,
        'MediaFile': MediaFile,
        'ProfileSettings': ProfileSettings2,
        'CodecFlags': {},
        'CodecParameters': [],
        'SourceResolution': '1080p',
        'TargetResolution': '1080p',
        'ScaleFilter': None
    }
    
    Command2 = CommandBuilderInstance.BuildCommand(CommandData2)
    print(f"Generated Command:\n{Command2}")
    
    # Test Case 3: Audio normalization with custom settings (louder)
    print("\n3. Audio Normalization ENABLED (Custom - Louder):")
    print("-" * 50)
    
    ProfileSettings3 = {
        'Codec': 'libsvtav1',
        'Quality': 25,
        'AudioBitrateKbps': 128,
        'ContainerType': 'mp4',
        'AudioNormalizationEnabled': True,   # Enabled
        'TargetLoudness': -16,               # Louder than EBU R128
        'LoudnessRange': 11,                 # More dynamic range
        'TruePeak': -1.5                     # Higher peak level
    }
    
    CommandData3 = {
        'Job': Job,
        'MediaFile': MediaFile,
        'ProfileSettings': ProfileSettings3,
        'CodecFlags': {},
        'CodecParameters': [],
        'SourceResolution': '1080p',
        'TargetResolution': '1080p',
        'ScaleFilter': None
    }
    
    Command3 = CommandBuilderInstance.BuildCommand(CommandData3)
    print(f"Generated Command:\n{Command3}")
    
    # Test Case 4: Audio normalization with video copy (audio-only transcoding)
    print("\n4. Audio Normalization + Video Copy (Audio-Only Transcoding):")
    print("-" * 50)
    
    ProfileSettings4 = {
        'Codec': 'copy',                     # Copy video without re-encoding
        'Quality': 25,
        'AudioBitrateKbps': 128,
        'ContainerType': 'mp4',
        'AudioNormalizationEnabled': True,   # Enabled
        'TargetLoudness': -23,               # EBU R128 standard
        'LoudnessRange': 7,                  # EBU R128 standard
        'TruePeak': -2                       # EBU R128 standard
    }
    
    CommandData4 = {
        'Job': Job,
        'MediaFile': MediaFile,
        'ProfileSettings': ProfileSettings4,
        'CodecFlags': {},
        'CodecParameters': [],
        'SourceResolution': '1080p',
        'TargetResolution': '1080p',
        'ScaleFilter': None
    }
    
    Command4 = CommandBuilderInstance.BuildCommand(CommandData4)
    print(f"Generated Command:\n{Command4}")
    
    print("\n" + "=" * 50)
    print("Audio Normalization Test Complete!")
    print("\nKey Benefits:")
    print("- Consistent volume levels across all shows")
    print("- No more manual volume adjustments")
    print("- Industry-standard EBU R128 loudness normalization")
    print("- Configurable target levels per profile")
    print("- Can be combined with video copy for fast audio-only processing")


if __name__ == "__main__":
    TestAudioNormalizationCommands()
