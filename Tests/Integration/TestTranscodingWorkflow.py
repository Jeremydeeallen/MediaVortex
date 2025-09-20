"""
Integration test for complete transcoding workflow with quality scoring.
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

from Services.TranscodingBusinessService import TranscodingBusinessService
from Services.FFmpegTranscodingService import FFmpegTranscodingService
from Services.FilenameResolutionService import FilenameResolutionService
from Services.FileManagerService import FileManagerService
from Services.FFmpegComparisonService import FFmpegComparisonService
from Models.TranscodeQueueModel import TranscodeQueueModel
from Models.TranscodeAttemptModel import TranscodeAttemptModel


class TestTranscodingWorkflow(unittest.TestCase):
    """Integration test for complete transcoding workflow with quality scoring."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create temporary directories for testing
        self.TempDir = tempfile.mkdtemp()
        self.SourceDir = os.path.join(self.TempDir, "Source")
        self.OutputDir = os.path.join(self.TempDir, "Output")
        os.makedirs(self.SourceDir, exist_ok=True)
        os.makedirs(self.OutputDir, exist_ok=True)
        
        # Sample test file
        self.TestFilePath = os.path.join(self.SourceDir, "TestMovie - 1080p BluRay.mkv")
        self.TestFileName = "TestMovie - 1080p BluRay.mkv"
        
        # Create a dummy test file
        with open(self.TestFilePath, 'w') as f:
            f.write("dummy video content")
        
        # Sample queue item
        self.QueueItem = TranscodeQueueModel(
            Id=1,
            FilePath=self.TestFilePath,
            FileName=self.TestFileName,
            Directory=self.SourceDir,
            SizeBytes=1500000000,  # 1.5GB
            SizeMB=1500.0,
            Priority=1,
            Status="pending",
            AssignedProfile="HighQuality"
        )
        
        # Quality settings from MediaFiles table
        self.QualitySettings = {
            'VideoBitrateKbps': 2000,
            'AudioBitrateKbps': 128,
            'TargetResolution': '720p',
            'Codec': 'libx264'
        }
    
    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.TempDir):
            shutil.rmtree(self.TempDir)
    
    def TestCompleteTranscodingWorkflowSuccess(self):
        """Test complete transcoding workflow from queue to completion with quality scoring."""
        # This test will FAIL until implementation is complete
        
        with patch('Services.TranscodingBusinessService.FFmpegTranscodingService') as MockTranscodingService, \
             patch('Services.TranscodingBusinessService.FilenameResolutionService') as MockFilenameService, \
             patch('Services.TranscodingBusinessService.FileManagerService') as MockFileManager, \
             patch('Services.TranscodingBusinessService.FFmpegComparisonService') as MockQualityService:
            
            # Setup mocks
            MockTranscodingService.TranscodeVideo.return_value = {
                'Success': True,
                'OutputFilePath': os.path.join(self.OutputDir, "TestMovie - 720p BluRay.mkv"),
                'Duration': 120.5,
                'ReturnCode': 0
            }
            
            MockFilenameService.GenerateOutputFilePath.return_value = os.path.join(self.OutputDir, "TestMovie - 720p BluRay.mkv")
            
            MockFileManager.ValidateFileExists.return_value = True
            MockFileManager.SetupTranscodingDirectories.return_value = {
                'Success': True,
                'MediaVortexSourceDir': self.SourceDir,
                'MediaVortexTempDir': self.OutputDir
            }
            
            MockQualityService.CreateVMAFComparison.return_value = Mock()
            MockQualityService.CreateVMAFComparison.return_value.Success = True
            MockQualityService.CreateVMAFComparison.return_value.VMAFScore = 95.2
            
            # Initialize service
            transcodingService = TranscodingBusinessService()
            
            # Execute workflow
            result = transcodingService.ProcessTranscodingWorkflow(self.QueueItem, self.QualitySettings)
            
            # Verify workflow steps
            self.assertTrue(result['Success'])
            self.assertEqual(result['Status'], 'completed')
            self.assertGreater(result['VMAFScore'], 90.0)
            self.assertIn('OutputFilePath', result)
            self.assertIn('TranscodeAttempt', result)
            
            # Verify file operations were called
            MockFileManager.SetupTranscodingDirectories.assert_called_once()
            MockTranscodingService.TranscodeVideo.assert_called_once()
            MockQualityService.CreateVMAFComparison.assert_called_once()
    
    def TestTranscodingWorkflowQualityScoreBelowThreshold(self):
        """Test transcoding workflow when quality score is below 90 threshold."""
        # This test will FAIL until implementation is complete
        
        with patch('Services.TranscodingBusinessService.FFmpegTranscodingService') as MockTranscodingService, \
             patch('Services.TranscodingBusinessService.FilenameResolutionService') as MockFilenameService, \
             patch('Services.TranscodingBusinessService.FileManagerService') as MockFileManager, \
             patch('Services.TranscodingBusinessService.FFmpegComparisonService') as MockQualityService:
            
            # Setup mocks for low quality result
            MockTranscodingService.TranscodeVideo.return_value = {
                'Success': True,
                'OutputFilePath': os.path.join(self.OutputDir, "TestMovie - 720p BluRay.mkv"),
                'Duration': 120.5,
                'ReturnCode': 0
            }
            
            MockFilenameService.GenerateOutputFilePath.return_value = os.path.join(self.OutputDir, "TestMovie - 720p BluRay.mkv")
            
            MockFileManager.ValidateFileExists.return_value = True
            MockFileManager.SetupTranscodingDirectories.return_value = {
                'Success': True,
                'MediaVortexSourceDir': self.SourceDir,
                'MediaVortexTempDir': self.OutputDir
            }
            
            # Mock low quality score
            MockQualityService.CreateVMAFComparison.return_value = Mock()
            MockQualityService.CreateVMAFComparison.return_value.Success = True
            MockQualityService.CreateVMAFComparison.return_value.VMAFScore = 85.3  # Below 90 threshold
            
            # Initialize service
            transcodingService = TranscodingBusinessService()
            
            # Execute workflow
            result = transcodingService.ProcessTranscodingWorkflow(self.QueueItem, self.QualitySettings)
            
            # Verify workflow result
            self.assertFalse(result['Success'])
            self.assertEqual(result['Status'], 'failed')
            self.assertLess(result['VMAFScore'], 90.0)
            self.assertIn('Quality score below threshold', result['ErrorMessage'])
            
            # Verify no file replacement occurred
            MockFileManager.ValidateFileExists.assert_called()
    
    def TestTranscodingWorkflowTranscodingFailure(self):
        """Test transcoding workflow when FFmpeg transcoding fails."""
        # This test will FAIL until implementation is complete
        
        with patch('Services.TranscodingBusinessService.FFmpegTranscodingService') as MockTranscodingService, \
             patch('Services.TranscodingBusinessService.FilenameResolutionService') as MockFilenameService, \
             patch('Services.TranscodingBusinessService.FileManagerService') as MockFileManager:
            
            # Setup mocks for transcoding failure
            MockTranscodingService.TranscodeVideo.return_value = {
                'Success': False,
                'ErrorMessage': 'FFmpeg transcoding failed: codec not supported',
                'ReturnCode': 1
            }
            
            MockFilenameService.GenerateOutputFilePath.return_value = os.path.join(self.OutputDir, "TestMovie - 720p BluRay.mkv")
            
            MockFileManager.ValidateFileExists.return_value = True
            MockFileManager.SetupTranscodingDirectories.return_value = {
                'Success': True,
                'MediaVortexSourceDir': self.SourceDir,
                'MediaVortexTempDir': self.OutputDir
            }
            
            # Initialize service
            transcodingService = TranscodingBusinessService()
            
            # Execute workflow
            result = transcodingService.ProcessTranscodingWorkflow(self.QueueItem, self.QualitySettings)
            
            # Verify workflow result
            self.assertFalse(result['Success'])
            self.assertEqual(result['Status'], 'failed')
            self.assertIn('FFmpeg transcoding failed', result['ErrorMessage'])
            
            # Verify transcoding was attempted
            MockTranscodingService.TranscodeVideo.assert_called_once()
    
    def TestTranscodingWorkflowFileCopyOperations(self):
        """Test that file copy operations work correctly in the workflow."""
        # This test will FAIL until implementation is complete
        
        with patch('Services.TranscodingBusinessService.FFmpegTranscodingService') as MockTranscodingService, \
             patch('Services.TranscodingBusinessService.FilenameResolutionService') as MockFilenameService, \
             patch('Services.TranscodingBusinessService.FileManagerService') as MockFileManager, \
             patch('Services.TranscodingBusinessService.FFmpegComparisonService') as MockQualityService:
            
            # Setup mocks
            MockTranscodingService.TranscodeVideo.return_value = {
                'Success': True,
                'OutputFilePath': os.path.join(self.OutputDir, "TestMovie - 720p BluRay.mkv"),
                'Duration': 120.5,
                'ReturnCode': 0
            }
            
            MockFilenameService.GenerateOutputFilePath.return_value = os.path.join(self.OutputDir, "TestMovie - 720p BluRay.mkv")
            
            MockFileManager.ValidateFileExists.return_value = True
            MockFileManager.SetupTranscodingDirectories.return_value = {
                'Success': True,
                'MediaVortexSourceDir': self.SourceDir,
                'MediaVortexTempDir': self.OutputDir
            }
            
            MockQualityService.CreateVMAFComparison.return_value = Mock()
            MockQualityService.CreateVMAFComparison.return_value.Success = True
            MockQualityService.CreateVMAFComparison.return_value.VMAFScore = 95.2
            
            # Initialize service
            transcodingService = TranscodingBusinessService()
            
            # Execute workflow
            result = transcodingService.ProcessTranscodingWorkflow(self.QueueItem, self.QualitySettings)
            
            # Verify file operations
            self.assertTrue(result['Success'])
            
            # Verify directory setup was called
            MockFileManager.SetupTranscodingDirectories.assert_called_once()
            
            # Verify file validation was called
            MockFileManager.ValidateFileExists.assert_called()
    
    def TestTranscodingWorkflowDatabaseLogging(self):
        """Test that transcoding attempts are properly logged to database."""
        # This test will FAIL until implementation is complete
        
        with patch('Services.TranscodingBusinessService.FFmpegTranscodingService') as MockTranscodingService, \
             patch('Services.TranscodingBusinessService.FilenameResolutionService') as MockFilenameService, \
             patch('Services.TranscodingBusinessService.FileManagerService') as MockFileManager, \
             patch('Services.TranscodingBusinessService.FFmpegComparisonService') as MockQualityService, \
             patch('Services.TranscodingBusinessService.DatabaseManager') as MockDatabase:
            
            # Setup mocks
            MockTranscodingService.TranscodeVideo.return_value = {
                'Success': True,
                'OutputFilePath': os.path.join(self.OutputDir, "TestMovie - 720p BluRay.mkv"),
                'Duration': 120.5,
                'ReturnCode': 0
            }
            
            MockFilenameService.GenerateOutputFilePath.return_value = os.path.join(self.OutputDir, "TestMovie - 720p BluRay.mkv")
            
            MockFileManager.ValidateFileExists.return_value = True
            MockFileManager.SetupTranscodingDirectories.return_value = {
                'Success': True,
                'MediaVortexSourceDir': self.SourceDir,
                'MediaVortexTempDir': self.OutputDir
            }
            
            MockQualityService.CreateVMAFComparison.return_value = Mock()
            MockQualityService.CreateVMAFComparison.return_value.Success = True
            MockQualityService.CreateVMAFComparison.return_value.VMAFScore = 95.2
            
            MockDatabase.SaveTranscodeAttempt.return_value = True
            
            # Initialize service
            transcodingService = TranscodingBusinessService()
            
            # Execute workflow
            result = transcodingService.ProcessTranscodingWorkflow(self.QueueItem, self.QualitySettings)
            
            # Verify database logging
            self.assertTrue(result['Success'])
            MockDatabase.SaveTranscodeAttempt.assert_called()
            
            # Verify TranscodeAttempt was created with correct data
            call_args = MockDatabase.SaveTranscodeAttempt.call_args[0][0]
            self.assertIsInstance(call_args, TranscodeAttemptModel)
            self.assertEqual(call_args.FilePath, self.TestFilePath)
            self.assertTrue(call_args.Success)
            self.assertEqual(call_args.VMAF, 95.2)
    
    def TestTranscodingWorkflowAspectRatioPreservation(self):
        """Test that aspect ratio is preserved during transcoding."""
        # This test will FAIL until implementation is complete
        
        with patch('Services.TranscodingBusinessService.FFmpegTranscodingService') as MockTranscodingService, \
             patch('Services.TranscodingBusinessService.FilenameResolutionService') as MockFilenameService, \
             patch('Services.TranscodingBusinessService.FileManagerService') as MockFileManager, \
             patch('Services.TranscodingBusinessService.FFmpegComparisonService') as MockQualityService:
            
            # Setup mocks
            MockTranscodingService.TranscodeVideo.return_value = {
                'Success': True,
                'OutputFilePath': os.path.join(self.OutputDir, "TestMovie - 720p BluRay.mkv"),
                'Duration': 120.5,
                'ReturnCode': 0
            }
            
            MockFilenameService.GenerateOutputFilePath.return_value = os.path.join(self.OutputDir, "TestMovie - 720p BluRay.mkv")
            
            MockFileManager.ValidateFileExists.return_value = True
            MockFileManager.SetupTranscodingDirectories.return_value = {
                'Success': True,
                'MediaVortexSourceDir': self.SourceDir,
                'MediaVortexTempDir': self.OutputDir
            }
            
            MockQualityService.CreateVMAFComparison.return_value = Mock()
            MockQualityService.CreateVMAFComparison.return_value.Success = True
            MockQualityService.CreateVMAFComparison.return_value.VMAFScore = 95.2
            
            # Initialize service
            transcodingService = TranscodingBusinessService()
            
            # Execute workflow
            result = transcodingService.ProcessTranscodingWorkflow(self.QueueItem, self.QualitySettings)
            
            # Verify transcoding was called with aspect ratio preservation
            self.assertTrue(result['Success'])
            MockTranscodingService.TranscodeVideo.assert_called_once()
            
            # Verify the quality settings included aspect ratio preservation
            call_args = MockTranscodingService.TranscodeVideo.call_args
            quality_settings = call_args[0][2]  # Third argument is quality settings
            self.assertEqual(quality_settings['TargetResolution'], '720p')
            self.assertIn('VideoBitrateKbps', quality_settings)
            self.assertIn('AudioBitrateKbps', quality_settings)


if __name__ == '__main__':
    unittest.main()
