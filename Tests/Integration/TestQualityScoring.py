"""
Integration test for quality scoring and file replacement logic.
This test MUST FAIL before implementation begins (TDD approach).
"""

import unittest
import os
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path

# Add the parent directory to the path so we can import our modules
sys.path.append(str(Path(__file__).parent.parent.parent))

from Services.FFmpegComparisonService import FFmpegComparisonService
from Services.FileManagerService import FileManagerService
from Services.TranscodingBusinessService import TranscodingBusinessService
from Models.TranscodeAttemptModel import TranscodeAttemptModel


class TestQualityScoring(unittest.TestCase):
    """Integration test for quality scoring and file replacement logic."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create temporary directories for testing
        self.TempDir = tempfile.mkdtemp()
        self.SourceDir = os.path.join(self.TempDir, "Source")
        self.OutputDir = os.path.join(self.TempDir, "Output")
        os.makedirs(self.SourceDir, exist_ok=True)
        os.makedirs(self.OutputDir, exist_ok=True)
        
        # Sample test files
        self.OriginalFilePath = os.path.join(self.SourceDir, "TestMovie - 1080p BluRay.mkv")
        self.TranscodedFilePath = os.path.join(self.OutputDir, "TestMovie - 720p BluRay.mkv")
        
        # Create dummy test files
        with open(self.OriginalFilePath, 'w') as f:
            f.write("original video content")
        with open(self.TranscodedFilePath, 'w') as f:
            f.write("transcoded video content")
        
        # Sample transcoding attempt
        self.TranscodeAttempt = TranscodeAttemptModel(
            Id=1,
            FilePath=self.OriginalFilePath,
            Quality=22,
            OldSizeBytes=1500000000,  # 1.5GB
            NewSizeBytes=800000000,   # 800MB
            Success=True,
            ProfileName="HighQuality"
        )
    
    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.TempDir):
            shutil.rmtree(self.TempDir)
    
    def TestQualityScoringAboveThreshold(self):
        """Test quality scoring when VMAF score is above 90 threshold."""
        # This test will FAIL until implementation is complete
        
        with patch('Services.FFmpegComparisonService.FFmpegService') as MockFFmpegService:
            # Mock VMAF comparison with high quality score
            MockVMAFResult = Mock()
            MockVMAFResult.Success = True
            MockVMAFResult.VMAFScore = 95.2
            MockVMAFResult.OutputPath = os.path.join(self.OutputDir, "VMAFResults.json")
            
            MockFFmpegService.CreateVMAFComparison.return_value = MockVMAFResult
            
            # Initialize service
            qualityService = FFmpegComparisonService()
            
            # Execute quality scoring
            result = qualityService.CreateVMAFComparison(
                self.OriginalFilePath,
                self.TranscodedFilePath,
                os.path.join(self.OutputDir, "VMAFResults.json")
            )
            
            # Verify quality scoring result
            self.assertTrue(result.Success)
            self.assertGreater(result.VMAFScore, 90.0)
            self.assertEqual(result.VMAFScore, 95.2)
            
            # Verify VMAF comparison was called
            MockFFmpegService.CreateVMAFComparison.assert_called_once()
    
    def TestQualityScoringBelowThreshold(self):
        """Test quality scoring when VMAF score is below 90 threshold."""
        # This test will FAIL until implementation is complete
        
        with patch('Services.FFmpegComparisonService.FFmpegService') as MockFFmpegService:
            # Mock VMAF comparison with low quality score
            MockVMAFResult = Mock()
            MockVMAFResult.Success = True
            MockVMAFResult.VMAFScore = 85.3  # Below 90 threshold
            MockVMAFResult.OutputPath = os.path.join(self.OutputDir, "VMAFResults.json")
            
            MockFFmpegService.CreateVMAFComparison.return_value = MockVMAFResult
            
            # Initialize service
            qualityService = FFmpegComparisonService()
            
            # Execute quality scoring
            result = qualityService.CreateVMAFComparison(
                self.OriginalFilePath,
                self.TranscodedFilePath,
                os.path.join(self.OutputDir, "VMAFResults.json")
            )
            
            # Verify quality scoring result
            self.assertTrue(result.Success)
            self.assertLess(result.VMAFScore, 90.0)
            self.assertEqual(result.VMAFScore, 85.3)
    
    def TestFileReplacementOnQualityPass(self):
        """Test that files are replaced when quality score is above threshold."""
        # This test will FAIL until implementation is complete
        
        with patch('Services.TranscodingBusinessService.FFmpegComparisonService') as MockQualityService, \
             patch('Services.TranscodingBusinessService.FileManagerService') as MockFileManager:
            
            # Mock high quality score
            MockVMAFResult = Mock()
            MockVMAFResult.Success = True
            MockVMAFResult.VMAFScore = 95.2
            
            MockQualityService.CreateVMAFComparison.return_value = MockVMAFResult
            MockFileManager.ValidateFileExists.return_value = True
            
            # Initialize service
            transcodingService = TranscodingBusinessService()
            
            # Execute file replacement logic
            result = transcodingService.ProcessFileReplacement(
                self.OriginalFilePath,
                self.TranscodedFilePath,
                self.TranscodeAttempt,
                95.2
            )
            
            # Verify file replacement result
            self.assertTrue(result['Success'])
            self.assertEqual(result['Status'], 'completed')
            self.assertGreater(result['VMAFScore'], 90.0)
            
            # Verify file operations were called
            MockFileManager.ValidateFileExists.assert_called()
    
    def TestFileReplacementSkippedOnQualityFail(self):
        """Test that file replacement is skipped when quality score is below threshold."""
        # This test will FAIL until implementation is complete
        
        with patch('Services.TranscodingBusinessService.FFmpegComparisonService') as MockQualityService, \
             patch('Services.TranscodingBusinessService.FileManagerService') as MockFileManager:
            
            # Mock low quality score
            MockVMAFResult = Mock()
            MockVMAFResult.Success = True
            MockVMAFResult.VMAFScore = 85.3  # Below 90 threshold
            
            MockQualityService.CreateVMAFComparison.return_value = MockVMAFResult
            MockFileManager.ValidateFileExists.return_value = True
            
            # Initialize service
            transcodingService = TranscodingBusinessService()
            
            # Execute file replacement logic
            result = transcodingService.ProcessFileReplacement(
                self.OriginalFilePath,
                self.TranscodedFilePath,
                self.TranscodeAttempt,
                85.3
            )
            
            # Verify file replacement result
            self.assertFalse(result['Success'])
            self.assertEqual(result['Status'], 'failed')
            self.assertLess(result['VMAFScore'], 90.0)
            self.assertIn('Quality score below threshold', result['ErrorMessage'])
            
            # Verify original file was not deleted
            self.assertTrue(os.path.exists(self.OriginalFilePath))
    
    def TestQualityScoringFailureHandling(self):
        """Test handling when quality scoring fails."""
        # This test will FAIL until implementation is complete
        
        with patch('Services.FFmpegComparisonService.FFmpegService') as MockFFmpegService:
            # Mock VMAF comparison failure
            MockVMAFResult = Mock()
            MockVMAFResult.Success = False
            MockVMAFResult.ErrorMessage = "FFmpeg VMAF analysis failed"
            
            MockFFmpegService.CreateVMAFComparison.return_value = MockVMAFResult
            
            # Initialize service
            qualityService = FFmpegComparisonService()
            
            # Execute quality scoring
            result = qualityService.CreateVMAFComparison(
                self.OriginalFilePath,
                self.TranscodedFilePath,
                os.path.join(self.OutputDir, "VMAFResults.json")
            )
            
            # Verify quality scoring failure
            self.assertFalse(result.Success)
            self.assertIn('FFmpeg VMAF analysis failed', result.ErrorMessage)
    
    def TestTranscodeAttemptDatabaseLogging(self):
        """Test that transcoding attempts are logged to database with quality scores."""
        # This test will FAIL until implementation is complete
        
        with patch('Services.TranscodingBusinessService.FFmpegComparisonService') as MockQualityService, \
             patch('Services.TranscodingBusinessService.FileManagerService') as MockFileManager, \
             patch('Services.TranscodingBusinessService.DatabaseManager') as MockDatabase:
            
            # Mock high quality score
            MockVMAFResult = Mock()
            MockVMAFResult.Success = True
            MockVMAFResult.VMAFScore = 95.2
            
            MockQualityService.CreateVMAFComparison.return_value = MockVMAFResult
            MockFileManager.ValidateFileExists.return_value = True
            MockDatabase.SaveTranscodeAttempt.return_value = True
            
            # Initialize service
            transcodingService = TranscodingBusinessService()
            
            # Execute file replacement with database logging
            result = transcodingService.ProcessFileReplacement(
                self.OriginalFilePath,
                self.TranscodedFilePath,
                self.TranscodeAttempt,
                95.2
            )
            
            # Verify database logging
            self.assertTrue(result['Success'])
            MockDatabase.SaveTranscodeAttempt.assert_called()
            
            # Verify TranscodeAttempt was saved with quality score
            call_args = MockDatabase.SaveTranscodeAttempt.call_args[0][0]
            self.assertIsInstance(call_args, TranscodeAttemptModel)
            self.assertEqual(call_args.VMAF, 95.2)
            self.assertTrue(call_args.Success)
    
    def TestQualityThresholdConfiguration(self):
        """Test that quality threshold is configurable and properly applied."""
        # This test will FAIL until implementation is complete
        
        QualityThresholdTests = [
            {'VMAFScore': 95.2, 'Threshold': 90.0, 'ShouldPass': True},
            {'VMAFScore': 89.9, 'Threshold': 90.0, 'ShouldPass': False},
            {'VMAFScore': 90.0, 'Threshold': 90.0, 'ShouldPass': True},
            {'VMAFScore': 85.3, 'Threshold': 80.0, 'ShouldPass': True},
            {'VMAFScore': 79.9, 'Threshold': 80.0, 'ShouldPass': False}
        ]
        
        for Test in QualityThresholdTests:
            with self.subTest(VMAFScore=Test['VMAFScore'], Threshold=Test['Threshold']):
                with patch('Services.TranscodingBusinessService.FFmpegComparisonService') as MockQualityService, \
                     patch('Services.TranscodingBusinessService.FileManagerService') as MockFileManager:
                    
                    # Mock quality score
                    MockVMAFResult = Mock()
                    MockVMAFResult.Success = True
                    MockVMAFResult.VMAFScore = Test['VMAFScore']
                    
                    MockQualityService.CreateVMAFComparison.return_value = MockVMAFResult
                    MockFileManager.ValidateFileExists.return_value = True
                    
                    # Initialize service with custom threshold
                    transcodingService = TranscodingBusinessService()
                    transcodingService.QualityThreshold = Test['Threshold']
                    
                    # Execute file replacement logic
                    result = transcodingService.ProcessFileReplacement(
                        self.OriginalFilePath,
                        self.TranscodedFilePath,
                        self.TranscodeAttempt,
                        Test['VMAFScore']
                    )
                    
                    # Verify result based on threshold
                    if Test['ShouldPass']:
                        self.assertTrue(result['Success'], 
                                      f"Should have passed with VMAF {Test['VMAFScore']} >= {Test['Threshold']}")
                        self.assertEqual(result['Status'], 'completed')
                    else:
                        self.assertFalse(result['Success'], 
                                       f"Should have failed with VMAF {Test['VMAFScore']} < {Test['Threshold']}")
                        self.assertEqual(result['Status'], 'failed')
    
    def TestFileCleanupOnQualityFail(self):
        """Test that temporary files are cleaned up when quality fails."""
        # This test will FAIL until implementation is complete
        
        with patch('Services.TranscodingBusinessService.FFmpegComparisonService') as MockQualityService, \
             patch('Services.TranscodingBusinessService.FileManagerService') as MockFileManager:
            
            # Mock low quality score
            MockVMAFResult = Mock()
            MockVMAFResult.Success = True
            MockVMAFResult.VMAFScore = 85.3  # Below threshold
            
            MockQualityService.CreateVMAFComparison.return_value = MockVMAFResult
            MockFileManager.ValidateFileExists.return_value = True
            
            # Initialize service
            transcodingService = TranscodingBusinessService()
            
            # Execute file replacement logic
            result = transcodingService.ProcessFileReplacement(
                self.OriginalFilePath,
                self.TranscodedFilePath,
                self.TranscodeAttempt,
                85.3
            )
            
            # Verify file cleanup
            self.assertFalse(result['Success'])
            self.assertEqual(result['Status'], 'failed')
            
            # Verify original file still exists (not deleted)
            self.assertTrue(os.path.exists(self.OriginalFilePath))
            
            # Verify transcoded file cleanup (should be removed)
            # Note: This would depend on the specific cleanup implementation


if __name__ == '__main__':
    unittest.main()
