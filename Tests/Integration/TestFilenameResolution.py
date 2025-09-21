"""
Integration test for filename resolution logic.
This test MUST FAIL before implementation begins (TDD approach).
"""

import unittest
import os
import tempfile
import shutil
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add the parent directory to the path so we can import our modules
sys.path.append(str(Path(__file__).parent.parent.parent))

from Services.FilenameResolutionService import FilenameResolutionService
from Services.FileManagerService import FileManagerService


class TestFilenameResolution(unittest.TestCase):
    """Integration test for filename resolution logic."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.FilenameService = FilenameResolutionService()
        self.FileManager = FileManagerService()
        
        # Test cases for different filename patterns
        self.TestCases = [
            {
                'Input': "Movie - 1080p BluRay.mkv",
                'ExpectedResolution': "1080p",
                'ExpectedOutput': "Movie - 720p BluRay.mkv",
                'TargetResolution': "720p"
            },
            {
                'Input': "TV Show S01E01 - 2160p UHD.mp4",
                'ExpectedResolution': "2160p",
                'ExpectedOutput': "TV Show S01E01 - 720p UHD.mp4",
                'TargetResolution': "720p"
            },
            {
                'Input': "Documentary - 4K HDR.avi",
                'ExpectedResolution': "4K",
                'ExpectedOutput': "Documentary - 720p HDR.avi",
                'TargetResolution': "720p"
            },
            {
                'Input': "Old Movie - HD Quality.mov",
                'ExpectedResolution': "HD",
                'ExpectedOutput': "Old Movie - 720p Quality.mov",
                'TargetResolution': "720p"
            },
            {
                'Input': "Simple File Name.mp4",
                'ExpectedResolution': None,
                'ExpectedOutput': "Simple File Name-720p.mp4",
                'TargetResolution': "720p"
            },
            {
                'Input': "Movie with 1080p and 2160p in name.mkv",
                'ExpectedResolution': "1080p",  # First match
                'ExpectedOutput': "Movie with 720p and 720p in name.mkv",
                'TargetResolution': "720p"
            }
        ]
    
    def TestResolutionExtractionFromFilenames(self):
        """Test that resolution is correctly extracted from various filename patterns."""
        # This test will FAIL until implementation is complete
        
        for TestCase in self.TestCases:
            with self.subTest(Input=TestCase['Input']):
                Resolution = self.FilenameService.ExtractResolutionFromFilename(TestCase['Input'])
                self.assertEqual(Resolution, TestCase['ExpectedResolution'],
                               f"Failed to extract resolution from: {TestCase['Input']}")
    
    def TestOutputFilenameGeneration(self):
        """Test that output filenames are generated correctly with resolution replacement."""
        # This test will FAIL until implementation is complete
        
        for TestCase in self.TestCases:
            with self.subTest(Input=TestCase['Input']):
                OutputFilename = self.FilenameService.GenerateOutputFilename(
                    TestCase['Input'], 
                    TestCase['TargetResolution']
                )
                self.assertEqual(OutputFilename, TestCase['ExpectedOutput'],
                               f"Failed to generate output filename for: {TestCase['Input']}")
    
    def TestOutputFilePathGeneration(self):
        """Test that complete output file paths are generated correctly."""
        # This test will FAIL until implementation is complete
        
        OutputDirectory = r"C:\MediaVortex"
        
        for TestCase in self.TestCases:
            with self.subTest(Input=TestCase['Input']):
                InputFilePath = os.path.join(r"C:\Test", TestCase['Input'])
                ExpectedOutputPath = os.path.join(OutputDirectory, TestCase['ExpectedOutput'])
                
                OutputFilePath = self.FilenameService.GenerateOutputFilePath(
                    InputFilePath,
                    OutputDirectory,
                    TestCase['TargetResolution']
                )
                
                self.assertEqual(OutputFilePath, ExpectedOutputPath,
                               f"Failed to generate output file path for: {TestCase['Input']}")
    
    def TestTargetResolutionDetermination(self):
        """Test that target resolution is determined correctly based on original resolution."""
        # This test will FAIL until implementation is complete
        
        ResolutionMappingTests = [
            {'Original': '1080p', 'Expected': '720p'},
            {'Original': '2160p', 'Expected': '720p'},
            {'Original': '4K', 'Expected': '720p'},
            {'Original': 'UHD', 'Expected': '720p'},
            {'Original': 'HD', 'Expected': '720p'},
            {'Original': 'SD', 'Expected': '720p'},
            {'Original': None, 'Expected': '720p'},
            {'Original': 'Unknown', 'Expected': '720p'}
        ]
        
        for Test in ResolutionMappingTests:
            with self.subTest(Original=Test['Original']):
                TargetResolution = self.FilenameService.DetermineTargetResolution(Test['Original'])
                self.assertEqual(TargetResolution, Test['Expected'],
                               f"Failed to determine target resolution for: {Test['Original']}")
    
    def TestFilenameResolutionValidation(self):
        """Test that filename resolution validation works correctly."""
        # This test will FAIL until implementation is complete
        
        for TestCase in self.TestCases:
            with self.subTest(Input=TestCase['Input']):
                Validation = self.FilenameService.ValidateFilenameResolution(TestCase['Input'])
                
                # Verify validation structure
                self.assertIsInstance(Validation, dict)
                self.assertIn('Success', Validation)
                self.assertIn('OriginalFileName', Validation)
                self.assertIn('CurrentResolution', Validation)
                self.assertIn('TargetResolution', Validation)
                self.assertIn('NeedsResolutionChange', Validation)
                self.assertIn('NewFileName', Validation)
                
                # Verify validation values
                self.assertTrue(Validation['Success'])
                self.assertEqual(Validation['OriginalFileName'], TestCase['Input'])
                self.assertEqual(Validation['CurrentResolution'], TestCase['ExpectedResolution'])
                self.assertEqual(Validation['TargetResolution'], TestCase['TargetResolution'])
                self.assertEqual(Validation['NewFileName'], TestCase['ExpectedOutput'])
                
                # Verify NeedsResolutionChange logic
                if TestCase['ExpectedResolution']:
                    self.assertTrue(Validation['NeedsResolutionChange'])
                else:
                    self.assertFalse(Validation['NeedsResolutionChange'])
    
    def TestResolutionPatternMatching(self):
        """Test that resolution patterns are matched correctly in various contexts."""
        # This test will FAIL until implementation is complete
        
        PatternTests = [
            {'Input': "1080p", 'ShouldMatch': True},
            {'Input': "2160p", 'ShouldMatch': True},
            {'Input': "4K", 'ShouldMatch': True},
            {'Input': "UHD", 'ShouldMatch': True},
            {'Input': "HD", 'ShouldMatch': True},
            {'Input': "SD", 'ShouldMatch': True},
            {'Input': "720p", 'ShouldMatch': True},
            {'Input': "480p", 'ShouldMatch': True},
            {'Input': "360p", 'ShouldMatch': True},
            {'Input': "1080i", 'ShouldMatch': False},  # Not in our patterns
            {'Input': "HDTV", 'ShouldMatch': False},   # Not in our patterns
            {'Input': "BluRay", 'ShouldMatch': False}, # Not a resolution
            {'Input': "WEB-DL", 'ShouldMatch': False}  # Not a resolution
        ]
        
        for Test in PatternTests:
            with self.subTest(Input=Test['Input']):
                Resolution = self.FilenameService.ExtractResolutionFromFilename(f"Movie - {Test['Input']}.mkv")
                if Test['ShouldMatch']:
                    self.assertEqual(Resolution, Test['Input'],
                                   f"Should have matched resolution: {Test['Input']}")
                else:
                    self.assertNotEqual(Resolution, Test['Input'],
                                      f"Should not have matched resolution: {Test['Input']}")
    
    def TestCaseInsensitiveResolutionMatching(self):
        """Test that resolution matching is case insensitive."""
        # This test will FAIL until implementation is complete
        
        CaseTests = [
            "Movie - 1080P BluRay.mkv",  # Uppercase P
            "Movie - 2160P UHD.mkv",     # Uppercase P
            "Movie - 4k HDR.mkv",        # Lowercase k
            "Movie - uhd Quality.mkv",   # Lowercase uhd
            "Movie - hd Quality.mkv",    # Lowercase hd
            "Movie - sd Quality.mkv"     # Lowercase sd
        ]
        
        for TestInput in CaseTests:
            with self.subTest(Input=TestInput):
                Resolution = self.FilenameService.ExtractResolutionFromFilename(TestInput)
                self.assertIsNotNone(Resolution, f"Should have matched resolution in: {TestInput}")
                
                # Generate output filename
                OutputFilename = self.FilenameService.GenerateOutputFilename(TestInput, "720p")
                self.assertIn("720p", OutputFilename, f"Should have replaced resolution in: {TestInput}")
    
    def TestMultipleResolutionReplacement(self):
        """Test that multiple resolution mentions in filename are all replaced."""
        # This test will FAIL until implementation is complete
        
        TestInput = "Movie - Available in 1080p and 2160p formats.mkv"
        ExpectedOutput = "Movie - Available in 720p and 720p formats.mkv"
        
        OutputFilename = self.FilenameService.GenerateOutputFilename(TestInput, "720p")
        self.assertEqual(OutputFilename, ExpectedOutput,
                        "Should have replaced all resolution mentions in filename")
    
    def TestFilenameResolutionWithSpecialCharacters(self):
        """Test filename resolution with special characters and Unicode."""
        # This test will FAIL until implementation is complete
        
        SpecialCharTests = [
            "Movie (2024) - 1080p [BluRay].mkv",
            "TV Show: Season 1 - 2160p UHD.mkv",
            "Documentary - 4K HDR [2024].mkv",
            "Movie with spaces - 1080p quality.mkv"
        ]
        
        for TestInput in SpecialCharTests:
            with self.subTest(Input=TestInput):
                Resolution = self.FilenameService.ExtractResolutionFromFilename(TestInput)
                self.assertIsNotNone(Resolution, f"Should have extracted resolution from: {TestInput}")
                
                OutputFilename = self.FilenameService.GenerateOutputFilename(TestInput, "720p")
                self.assertIn("720p", OutputFilename, f"Should have replaced resolution in: {TestInput}")
                self.assertNotIn("1080p", OutputFilename, f"Should not contain original resolution in: {TestInput}")
                self.assertNotIn("2160p", OutputFilename, f"Should not contain original resolution in: {TestInput}")
                self.assertNotIn("4K", OutputFilename, f"Should not contain original resolution in: {TestInput}")


if __name__ == '__main__':
    unittest.main()
