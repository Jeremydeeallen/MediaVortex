#!/usr/bin/env python3
"""
Test script for Phase 3.1 setup implementation.
This script tests the directory setup, filename resolution, and FFmpeg transcoding services.
"""

import sys
import os
from pathlib import Path

# Add the parent directory to the path so we can import our services
sys.path.append(str(Path(__file__).parent.parent))

from Services.FileManagerService import FileManagerService
from Services.FilenameResolutionService import FilenameResolutionService
from Services.FFmpegTranscodingService import FFmpegTranscodingService
from Services.LoggingService import LoggingService


def TestDirectorySetup():
    """Test T003: Directory setup functionality."""
    print("=" * 60)
    print("Testing T003: Directory Setup")
    print("=" * 60)
    
    try:
        fileManager = FileManagerService()
        result = fileManager.SetupTranscodingDirectories()
        
        print(f"Directory Setup Result: {result['Success']}")
        print(f"HandBrake Source Dir: {result['HandBrakeSourceDir']}")
        print(f"HandBrake Temp Dir: {result['HandBrakeTempDir']}")
        print(f"Created Directories: {result['CreatedDirectories']}")
        
        if result['Errors']:
            print(f"Errors: {result['Errors']}")
        
        return result['Success']
        
    except Exception as e:
        print(f"Error testing directory setup: {e}")
        return False


def TestFilenameResolution():
    """Test T004: Filename resolution functionality."""
    print("\n" + "=" * 60)
    print("Testing T004: Filename Resolution")
    print("=" * 60)
    
    try:
        filenameService = FilenameResolutionService()
        
        # Test cases
        testFiles = [
            "Movie - 1080p BluRay.mkv",
            "TV Show S01E01 - 2160p UHD.mp4",
            "Documentary - 4K HDR.avi",
            "Old Movie - HD Quality.mov",
            "Simple File Name.mp4"
        ]
        
        for testFile in testFiles:
            print(f"\nTesting: {testFile}")
            
            # Extract resolution
            resolution = filenameService.ExtractResolutionFromFilename(testFile)
            print(f"  Extracted Resolution: {resolution}")
            
            # Generate output filename
            outputFilename = filenameService.GenerateOutputFilename(testFile, "720p")
            print(f"  Output Filename: {outputFilename}")
            
            # Validate resolution
            validation = filenameService.ValidateFilenameResolution(testFile)
            print(f"  Needs Resolution Change: {validation['NeedsResolutionChange']}")
            print(f"  New Filename: {validation['NewFileName']}")
        
        return True
        
    except Exception as e:
        print(f"Error testing filename resolution: {e}")
        return False


def TestFFmpegTranscoding():
    """Test T005: FFmpeg transcoding service."""
    print("\n" + "=" * 60)
    print("Testing T005: FFmpeg Transcoding Service")
    print("=" * 60)
    
    try:
        transcodingService = FFmpegTranscodingService()
        
        # Test availability
        isAvailable = transcodingService.CheckAvailability()
        print(f"FFmpeg Transcoding Available: {isAvailable}")
        
        # Test quality settings validation
        testSettings = {
            'VideoBitrateKbps': 2000,
            'AudioBitrateKbps': 128,
            'TargetResolution': '720p',
            'Codec': 'libx264'
        }
        
        print(f"\nTesting Quality Settings Validation:")
        print(f"Test Settings: {testSettings}")
        
        validation = transcodingService.ValidateTranscodingSettings(testSettings)
        print(f"Validation Success: {validation['Success']}")
        print(f"Errors: {validation['Errors']}")
        print(f"Warnings: {validation['Warnings']}")
        
        # Test scale filter generation
        print(f"\nTesting Scale Filter Generation:")
        for resolution in ['720p', '1080p', '480p', '360p']:
            scaleFilter = transcodingService.GetScaleFilter(resolution)
            print(f"  {resolution}: {scaleFilter}")
        
        return True
        
    except Exception as e:
        print(f"Error testing FFmpeg transcoding: {e}")
        return False


def Main():
    """Main test function."""
    print("Phase 3.1 Setup Implementation Test")
    print("Testing directory setup, filename resolution, and FFmpeg transcoding services")
    
    # Initialize logging
    LoggingService.LogInfo("Starting Phase 3.1 setup tests", "TestPhase31Setup", "Main")
    
    # Run tests
    testResults = []
    
    testResults.append(("Directory Setup", TestDirectorySetup()))
    testResults.append(("Filename Resolution", TestFilenameResolution()))
    testResults.append(("FFmpeg Transcoding", TestFFmpegTranscoding()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    
    allPassed = True
    for testName, result in testResults:
        status = "PASS" if result else "FAIL"
        print(f"{testName}: {status}")
        if not result:
            allPassed = False
    
    print(f"\nOverall Result: {'ALL TESTS PASSED' if allPassed else 'SOME TESTS FAILED'}")
    
    if allPassed:
        print("\n✅ Phase 3.1 Setup Implementation Complete!")
        print("Ready to proceed to Phase 3.2 (Tests First)")
    else:
        print("\n❌ Phase 3.1 Setup Implementation Issues Detected")
        print("Please review and fix the failing tests before proceeding")
    
    return allPassed


if __name__ == "__main__":
    success = Main()
    sys.exit(0 if success else 1)
