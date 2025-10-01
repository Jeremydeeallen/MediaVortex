#!/usr/bin/env python3
"""
Test script to demonstrate audio compression functionality for hearing accessibility.
This script shows how the CommandBuilder will generate FFmpeg commands with dynamic range compression.
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


def TestAudioCompressionCommands():
    """Test the CommandBuilder with different audio compression settings for hearing accessibility."""
    
    print("MediaVortex Audio Compression Test - Hearing Accessibility")
    print("=" * 60)
    
    # Create a mock job and media file
    Job = TranscodeQueueModel(
        Id=1,
        FilePath="C:\\Test\\ActionMovie.mkv",
        FileName="ActionMovie.mkv",
        Directory="C:\\Test",
        SizeBytes=2000000000,
        SizeMB=2000.0,
        Priority=1,
        Status="Pending",
        DateAdded="2024-01-01 12:00:00",
        DateStarted=None
    )
    
    MediaFile = MediaFileModel(
        Id=1,
        SeasonId=1,
        FilePath="C:\\Test\\ActionMovie.mkv",
        FileName="ActionMovie.mkv",
        SizeMB=2000.0,
        VideoBitrateKbps=8000,
        AudioBitrateKbps=192,
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
        AudioChannels=6,  # 5.1 surround sound
        AudioSampleRate=48000,
        AudioSampleFormat="fltp",
        AudioChannelLayout="5.1",
        ContainerFormat="matroska",
        OverallBitrate=8192,
        TranscodedByMediaVortex=False
    )
    
    CommandBuilderInstance = CommandBuilder()
    
    # Test Case 1: No audio processing (current behavior)
    print("\n1. NO AUDIO PROCESSING (Current Behavior):")
    print("-" * 50)
    print("Result: Explosions too loud, dialogue too quiet")
    
    ProfileSettings1 = {
        'Codec': 'libsvtav1',
        'Quality': 25,
        'AudioBitrateKbps': 192,
        'ContainerType': 'mp4',
        'AudioNormalizationEnabled': False,
        'AudioCompressionEnabled': False
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
    
    # Test Case 2: Light compression for mild hearing issues
    print("\n2. LIGHT COMPRESSION (Mild Hearing Issues):")
    print("-" * 50)
    print("Result: Slightly reduces loud sounds, slightly boosts quiet dialogue")
    
    ProfileSettings2 = {
        'Codec': 'libsvtav1',
        'Quality': 25,
        'AudioBitrateKbps': 192,
        'ContainerType': 'mp4',
        'AudioNormalizationEnabled': True,
        'TargetLoudness': -23,
        'LoudnessRange': 7,
        'TruePeak': -2,
        'AudioCompressionEnabled': True,
        'CompressionThreshold': -15,    # Start compression at -15dB (louder threshold)
        'CompressionRatio': 3,          # 3:1 ratio (gentle compression)
        'CompressionAttack': 10,        # 10ms attack (slower)
        'CompressionRelease': 100,      # 100ms release (slower)
        'CompressionMakeup': 1          # 1dB makeup gain (subtle boost)
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
    
    # Test Case 3: Moderate compression for moderate hearing issues
    print("\n3. MODERATE COMPRESSION (Moderate Hearing Issues):")
    print("-" * 50)
    print("Result: Good balance - reduces explosions, boosts dialogue significantly")
    
    ProfileSettings3 = {
        'Codec': 'libsvtav1',
        'Quality': 25,
        'AudioBitrateKbps': 192,
        'ContainerType': 'mp4',
        'AudioNormalizationEnabled': True,
        'TargetLoudness': -23,
        'LoudnessRange': 7,
        'TruePeak': -2,
        'AudioCompressionEnabled': True,
        'CompressionThreshold': -20,    # Start compression at -20dB (standard)
        'CompressionRatio': 4,          # 4:1 ratio (moderate compression)
        'CompressionAttack': 5,         # 5ms attack (standard)
        'CompressionRelease': 50,       # 50ms release (standard)
        'CompressionMakeup': 2          # 2dB makeup gain (noticeable boost)
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
    
    # Test Case 4: Heavy compression for significant hearing issues
    print("\n4. HEAVY COMPRESSION (Significant Hearing Issues):")
    print("-" * 50)
    print("Result: Dramatically reduces loud sounds, significantly boosts quiet dialogue")
    
    ProfileSettings4 = {
        'Codec': 'libsvtav1',
        'Quality': 25,
        'AudioBitrateKbps': 192,
        'ContainerType': 'mp4',
        'AudioNormalizationEnabled': True,
        'TargetLoudness': -23,
        'LoudnessRange': 7,
        'TruePeak': -2,
        'AudioCompressionEnabled': True,
        'CompressionThreshold': -25,    # Start compression at -25dB (lower threshold)
        'CompressionRatio': 8,          # 8:1 ratio (heavy compression)
        'CompressionAttack': 3,         # 3ms attack (faster)
        'CompressionRelease': 30,       # 30ms release (faster)
        'CompressionMakeup': 4          # 4dB makeup gain (strong boost)
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
    
    # Test Case 5: Audio-only transcoding with compression (fastest option)
    print("\n5. AUDIO-ONLY TRANSCODING + COMPRESSION (Fastest Option):")
    print("-" * 50)
    print("Result: Video copied without re-encoding, only audio compressed")
    
    ProfileSettings5 = {
        'Codec': 'copy',                # Copy video without re-encoding
        'Quality': 25,
        'AudioBitrateKbps': 192,
        'ContainerType': 'mp4',
        'AudioNormalizationEnabled': True,
        'TargetLoudness': -23,
        'LoudnessRange': 7,
        'TruePeak': -2,
        'AudioCompressionEnabled': True,
        'CompressionThreshold': -20,    # Standard compression
        'CompressionRatio': 4,          # 4:1 ratio
        'CompressionAttack': 5,         # 5ms attack
        'CompressionRelease': 50,       # 50ms release
        'CompressionMakeup': 2          # 2dB makeup gain
    }
    
    CommandData5 = {
        'Job': Job,
        'MediaFile': MediaFile,
        'ProfileSettings': ProfileSettings5,
        'CodecFlags': {},
        'CodecParameters': [],
        'SourceResolution': '1080p',
        'TargetResolution': '1080p',
        'ScaleFilter': None
    }
    
    Command5 = CommandBuilderInstance.BuildCommand(CommandData5)
    print(f"Generated Command:\n{Command5}")
    
    print("\n" + "=" * 60)
    print("Audio Compression Test Complete!")
    print("\n🎯 RECOMMENDED SETTINGS FOR YOUR HEARING ISSUES:")
    print("=" * 60)
    print("For your specific problem (hard to hear dialogue, explosions too loud):")
    print("\n✅ RECOMMENDED: Test Case 3 (Moderate Compression)")
    print("   - CompressionThreshold: -20dB")
    print("   - CompressionRatio: 4:1")
    print("   - CompressionMakeup: 2dB")
    print("   - This will reduce loud explosions and boost quiet dialogue")
    print("\n🔧 HOW IT WORKS:")
    print("   - Sounds above -20dB get compressed (reduced in volume)")
    print("   - Sounds below -20dB get boosted by 2dB")
    print("   - 4:1 ratio means loud sounds are reduced to 1/4 their original level")
    print("   - Dialogue becomes more audible, explosions become manageable")
    print("\n⚡ FASTEST OPTION: Test Case 5 (Audio-Only Transcoding)")
    print("   - Same compression settings as Test Case 3")
    print("   - Video copied without re-encoding (much faster)")
    print("   - Only audio gets processed")
    print("\n🎛️ FINE-TUNING:")
    print("   - Increase CompressionMakeup (3-4dB) if dialogue still too quiet")
    print("   - Decrease CompressionThreshold (-25dB) if explosions still too loud")
    print("   - Increase CompressionRatio (6-8:1) for more aggressive compression")


if __name__ == "__main__":
    TestAudioCompressionCommands()

