#!/usr/bin/env python3
"""
Test script for CommandBuilder using real database data.
Tests AV1 transcoding with CGI profile and Garfield Show file.
"""

import sys
import os
from typing import Dict, Any, Optional

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from Repositories.DatabaseManager import DatabaseManager
from Models.CommandBuilder import CommandBuilder
from Models.TranscodeQueueModel import TranscodeQueueModel
from Models.MediaFileModel import MediaFileModel
from Services.CommandBuilderService import CommandBuilderService
from Services.ResolutionService import ResolutionService

def CreateTestData() -> Dict[str, Any]:
    """Create test data using real database values."""
    print("Creating test data from database...")
    
    # Initialize database manager
    db_manager = DatabaseManager()
    
    # Get CGI profile (assuming it exists)
    try:
        # Get a profile - we'll use the first one we find, or create test data
        profiles = db_manager.GetAllProfiles()
        if profiles:
            test_profile = profiles[0]
            print(f"Using profile: {test_profile.ProfileName}")
        else:
            print("No profiles found, creating test profile data...")
            test_profile = None
    except Exception as e:
        print(f"Error getting profiles: {e}")
        test_profile = None
    
    # Get libsvtav1 codec flags
    try:
        codec_flags = db_manager.GetCodecFlagsByCodecName('libsvtav1')
        if codec_flags:
            print(f"Found libsvtav1 codec: {codec_flags['DisplayName']}")
        else:
            print("ERROR: libsvtav1 codec not found in database!")
            return None
    except Exception as e:
        print(f"Error getting codec flags: {e}")
        return None
    
    # Get codec parameters
    try:
        codec_parameters = db_manager.GetCodecParametersByCodecFlagsId(codec_flags['Id'])
        if codec_parameters:
            print(f"Found {len(codec_parameters)} codec parameters")
        else:
            print("ERROR: No codec parameters found!")
            return None
    except Exception as e:
        print(f"Error getting codec parameters: {e}")
        return None
    
    # Create test media file (Garfield Show)
    test_media_file = MediaFileModel(
        Id=999,
        FileName="The Garfield Show - S01E01 - Pasta Wars WEBDL-1080p.mkv",
        FilePath="c:\\MediaVortex\\Source\\The Garfield Show - S01E01 - Pasta Wars WEBDL-1080p.mkv",
        Resolution="1080p",
        AssignedProfile=test_profile.ProfileName if test_profile else "Test Profile"
    )
    
    # Create test transcode queue job
    test_job = TranscodeQueueModel(
        Id=999,
        FilePath=test_media_file.FilePath,
        FileName=test_media_file.FileName,
        Directory="c:\\MediaVortex\\Source\\",
        Status="Pending",
        AssignedProfile=test_media_file.AssignedProfile
    )
    
    # Get real profile settings from database
    try:
        real_profile_settings = db_manager.GetProfileSettingsForTargetResolution(
            test_profile.ProfileName, '1080p'  # Source resolution
        )
        if real_profile_settings:
            print(f"Found real profile settings: {real_profile_settings}")
            # Use real settings from database
            profile_settings = {
                'Codec': real_profile_settings.get('Codec', 'libsvtav1'),
                'Preset': real_profile_settings.get('Preset', 6),  # Preset from database
                'Quality': real_profile_settings.get('Quality', 30),  # CRF from database
                'FilmGrain': real_profile_settings.get('FilmGrain', 0),  # Film grain from Profiles table
                'AudioBitrateKbps': real_profile_settings.get('AudioBitrateKbps'),  # Audio bitrate from database
                'ContainerType': 'mp4',  # MP4 container for faststart
                'YadifMode': real_profile_settings.get('YadifMode', 1),
                'YadifParity': real_profile_settings.get('YadifParity', 1),
                'YadifDeint': real_profile_settings.get('YadifDeint', 1)
            }
        else:
            print("No profile settings found in database, using defaults")
            profile_settings = {
                'Codec': 'libsvtav1',
                'Preset': 6,
                'Quality': 30,
                'Grain': 0,
                'AudioBitrateKbps': None,
                'ContainerType': 'mp4',
                'YadifMode': 1,
                'YadifParity': 1,
                'YadifDeint': 1
            }
    except Exception as e:
        print(f"Error getting profile settings: {e}")
        # Fallback to defaults
        profile_settings = {
            'Codec': 'libsvtav1',
            'Preset': 6,
            'Quality': 30,
            'Grain': 0,
            'AudioBitrateKbps': None,
            'ContainerType': 'mp4',
            'YadifMode': 1,
            'YadifParity': 1,
            'YadifDeint': 1
        }
    
    return {
        'Job': test_job,
        'MediaFile': test_media_file,
        'ProfileSettings': profile_settings,
        'CodecFlags': codec_flags,
        'CodecParameters': codec_parameters,
        'SourceResolution': '1080p',
        'TargetResolution': '720p',
        'ScaleFilter': 'scale=1280:720'
    }

def TestCommandBuilder():
    """Test the CommandBuilder with real database data."""
    print("=" * 60)
    print("AV1 CommandBuilder Test")
    print("=" * 60)
    
    # Create test data
    test_data = CreateTestData()
    if not test_data:
        print("Failed to create test data!")
        return
    
    print("\nTest Data Created:")
    print(f"  Media File: {test_data['MediaFile'].FileName}")
    print(f"  Source Resolution: {test_data['SourceResolution']}")
    print(f"  Target Resolution: {test_data['TargetResolution']}")
    print(f"  Codec: {test_data['ProfileSettings']['Codec']}")
    print(f"  Preset: {test_data['ProfileSettings']['Preset']}")
    print(f"  CRF: {test_data['ProfileSettings']['Quality']}")
    print(f"  Film Grain: {test_data['ProfileSettings']['FilmGrain']}")
    
    # Test CommandBuilder
    print("\nTesting CommandBuilder...")
    try:
        command_builder = CommandBuilder()
        generated_command = command_builder.BuildCommand(test_data)
        
        if generated_command:
            print("\nGenerated Command:")
            print(generated_command)
            
            # Build expected command based on actual database values
            expected_quality = test_data['ProfileSettings'].get('Quality', 30)
            expected_grain = test_data['ProfileSettings'].get('FilmGrain', 0)
            expected_audio = test_data['ProfileSettings'].get('AudioBitrateKbps')
            
            # Build expected command with actual database values
            expected_parts = [
                'C:\\Code\\Automation\\MediaVortex\\FFmpegMaster\\bin\\ffmpeg.exe',
                '-i', f'"c:\\MediaVortex\\Source\\The Garfield Show - S01E01 - Pasta Wars WEBDL-1080p.mkv"',
                '-c:v', 'libsvtav1',
                '-crf', str(expected_quality),
                '-preset', '6',
                '-c:a', 'copy' if not expected_audio else f'aac -b:a {expected_audio}k',
                '-vf', '"yadif=1:1:1,scale=1280:720"',
                '-movflags', '+faststart',
                '-y', f'"c:\\MediaVortex\\The Garfield Show - S01E01 - Pasta Wars WEBDL-720p.mp4"'
            ]
            
            # Add film grain if present in database
            if expected_grain and expected_grain > 0:
                # Insert film grain after video filters
                grain_index = expected_parts.index('-movflags')
                expected_parts.insert(grain_index, f'film-grain={expected_grain}')
                expected_parts.insert(grain_index, '-svtav1-params')
            
            expected_command = ' '.join(expected_parts)
            
            print("\nExpected Command:")
            print(expected_command)
            
            print("\nComparison:")
            if generated_command.strip() == expected_command.strip():
                print("✅ SUCCESS: Generated command matches expected command!")
            else:
                print("❌ MISMATCH: Generated command differs from expected")
                print("\nDifferences:")
                # Simple diff
                gen_lines = generated_command.split()
                exp_lines = expected_command.split()
                differences = []
                for i, (gen, exp) in enumerate(zip(gen_lines, exp_lines)):
                    if gen != exp:
                        differences.append(f"  Position {i}: Generated='{gen}' vs Expected='{exp}'")
                        print(f"  Position {i}: Generated='{gen}' vs Expected='{exp}'")
                
                # Summary at bottom
                print("\n" + "="*60)
                print("SUMMARY OF ISSUES:")
                print("="*60)
                if differences:
                    for diff in differences:
                        print(diff)
                else:
                    print("  - Length mismatch: Generated has different number of parameters")
                print("="*60)
        else:
            print("❌ ERROR: CommandBuilder returned None")
            
    except Exception as e:
        print(f"❌ ERROR: Exception in CommandBuilder: {e}")
        import traceback
        traceback.print_exc()

def TestCommandBuilderService():
    """Test the full CommandBuilderService workflow."""
    print("\n" + "=" * 60)
    print("Testing CommandBuilderService Workflow")
    print("=" * 60)
    
    try:
        # Initialize services
        db_manager = DatabaseManager()
        command_builder_service = CommandBuilderService()
        
        # Create test data
        test_data = CreateTestData()
        if not test_data:
            print("Failed to create test data!")
            return
        
        # Test the service workflow
        transcoding_settings = {
            'ProfileSettings': test_data['ProfileSettings'],
            'CodecFlags': test_data['CodecFlags'],
            'CodecParameters': test_data['CodecParameters'],
            'SourceResolution': test_data['SourceResolution']
        }
        
        generated_command = command_builder_service.BuildCommand(
            test_data['Job'],
            test_data['MediaFile'],
            transcoding_settings
        )
        
        if generated_command:
            print("\nCommandBuilderService Generated Command:")
            print(generated_command)
        else:
            print("❌ ERROR: CommandBuilderService returned None")
            
    except Exception as e:
        print(f"❌ ERROR: Exception in CommandBuilderService: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    import sys
    from datetime import datetime
    
    # Redirect output to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"test_command_builder_output_{timestamp}.txt"
    
    print(f"Starting AV1 CommandBuilder Test...")
    print(f"Output will be written to: {output_file}")
    
    # Redirect stdout to file
    original_stdout = sys.stdout
    with open(output_file, 'w') as f:
        sys.stdout = f
        
        print("Starting AV1 CommandBuilder Test...")
        
        # Test 1: Direct CommandBuilder
        TestCommandBuilder()
        
        # Test 2: CommandBuilderService workflow
        TestCommandBuilderService()
        
        print("\n" + "=" * 60)
        print("Test Complete")
        print("=" * 60)
    
    # Restore stdout
    sys.stdout = original_stdout
    
    print(f"Test completed. Results written to: {output_file}")
    print("You can now share this file for analysis.")
