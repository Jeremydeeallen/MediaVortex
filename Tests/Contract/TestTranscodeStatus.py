"""
Contract test for GET /api/transcode/status/{JobId} endpoint.
This test MUST FAIL before implementation begins (TDD approach).
"""

import unittest
import json
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add the parent directory to the path so we can import our modules
sys.path.append(str(Path(__file__).parent.parent.parent))

from Controllers.TranscodeQueueController import TranscodeQueueController


class TestTranscodeStatus(unittest.TestCase):
    """Contract test for GET /api/transcode/status/{JobId} endpoint."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.Controller = TranscodeQueueController()
        self.ValidJobId = "test-job-123"
        self.InvalidJobId = "invalid-job-456"
        self.ValidFilePath = r"C:\Test\Movie - 1080p BluRay.mkv"
        self.ValidStartTime = "2024-01-15T10:30:00Z"
        self.ValidEndTime = "2024-01-15T11:45:00Z"
        self.ValidOutputFilePath = r"C:\MediaVortex\Movie - 720p BluRay.mkv"
    
    def TestTranscodeStatusRunningResponse(self):
        """Test successful status response for running job matches contract schema."""
        # This test will FAIL until implementation is complete
        
        with patch('Controllers.TranscodeQueueController.TranscodingBusinessService') as MockService:
            MockService.GetTranscodeStatus.return_value = {
                'Success': True,
                'JobId': self.ValidJobId,
                'FilePath': self.ValidFilePath,
                'Status': 'running',
                'ProgressPercent': 45.5,
                'StartTime': self.ValidStartTime,
                'EndTime': None,
                'ErrorMessage': None,
                'OutputFilePath': None,
                'SizeReductionPercent': None
            }
            
            response = self.Controller.GetTranscodeStatus(self.ValidJobId)
            
            # Verify response structure matches contract
            self.assertIsInstance(response, dict)
            
            # Required fields from contract
            RequiredFields = ['JobId', 'FilePath', 'Status', 'ProgressPercent', 'StartTime']
            for Field in RequiredFields:
                self.assertIn(Field, response, f"Required field '{Field}' missing from response")
            
            # Verify field types match contract
            self.assertIsInstance(response['JobId'], str)
            self.assertIsInstance(response['FilePath'], str)
            self.assertIn(response['Status'], ['running', 'completed', 'failed', 'cancelled'])
            self.assertIsInstance(response['ProgressPercent'], (int, float))
            self.assertGreaterEqual(response['ProgressPercent'], 0)
            self.assertLessEqual(response['ProgressPercent'], 100)
            self.assertIsInstance(response['StartTime'], str)
            
            # Verify values
            self.assertEqual(response['JobId'], self.ValidJobId)
            self.assertEqual(response['FilePath'], self.ValidFilePath)
            self.assertEqual(response['Status'], 'running')
            self.assertEqual(response['ProgressPercent'], 45.5)
            self.assertEqual(response['StartTime'], self.ValidStartTime)
    
    def TestTranscodeStatusCompletedResponse(self):
        """Test successful status response for completed job matches contract schema."""
        # This test will FAIL until implementation is complete
        
        with patch('Controllers.TranscodeQueueController.TranscodingBusinessService') as MockService:
            MockService.GetTranscodeStatus.return_value = {
                'Success': True,
                'JobId': self.ValidJobId,
                'FilePath': self.ValidFilePath,
                'Status': 'completed',
                'ProgressPercent': 100.0,
                'StartTime': self.ValidStartTime,
                'EndTime': self.ValidEndTime,
                'ErrorMessage': None,
                'OutputFilePath': self.ValidOutputFilePath,
                'SizeReductionPercent': 25.3
            }
            
            response = self.Controller.GetTranscodeStatus(self.ValidJobId)
            
            # Verify response structure
            self.assertIsInstance(response, dict)
            
            # Required fields
            RequiredFields = ['JobId', 'FilePath', 'Status', 'ProgressPercent', 'StartTime']
            for Field in RequiredFields:
                self.assertIn(Field, response, f"Required field '{Field}' missing from response")
            
            # Optional fields for completed job
            OptionalFields = ['EndTime', 'OutputFilePath', 'SizeReductionPercent']
            for Field in OptionalFields:
                if Field in response:
                    self.assertIsNotNone(response[Field])
            
            # Verify values
            self.assertEqual(response['JobId'], self.ValidJobId)
            self.assertEqual(response['Status'], 'completed')
            self.assertEqual(response['ProgressPercent'], 100.0)
            self.assertEqual(response['EndTime'], self.ValidEndTime)
            self.assertEqual(response['OutputFilePath'], self.ValidOutputFilePath)
            self.assertEqual(response['SizeReductionPercent'], 25.3)
    
    def TestTranscodeStatusFailedResponse(self):
        """Test successful status response for failed job matches contract schema."""
        # This test will FAIL until implementation is complete
        
        with patch('Controllers.TranscodeQueueController.TranscodingBusinessService') as MockService:
            MockService.GetTranscodeStatus.return_value = {
                'Success': True,
                'JobId': self.ValidJobId,
                'FilePath': self.ValidFilePath,
                'Status': 'failed',
                'ProgressPercent': 67.8,
                'StartTime': self.ValidStartTime,
                'EndTime': self.ValidEndTime,
                'ErrorMessage': 'FFmpeg transcoding failed: codec not supported',
                'OutputFilePath': None,
                'SizeReductionPercent': None
            }
            
            response = self.Controller.GetTranscodeStatus(self.ValidJobId)
            
            # Verify response structure
            self.assertIsInstance(response, dict)
            
            # Required fields
            RequiredFields = ['JobId', 'FilePath', 'Status', 'ProgressPercent', 'StartTime']
            for Field in RequiredFields:
                self.assertIn(Field, response, f"Required field '{Field}' missing from response")
            
            # Verify values
            self.assertEqual(response['JobId'], self.ValidJobId)
            self.assertEqual(response['Status'], 'failed')
            self.assertEqual(response['ProgressPercent'], 67.8)
            self.assertEqual(response['ErrorMessage'], 'FFmpeg transcoding failed: codec not supported')
            self.assertEqual(response['EndTime'], self.ValidEndTime)
    
    def TestTranscodeStatusJobNotFound(self):
        """Test error response when job is not found."""
        # This test will FAIL until implementation is complete
        
        with patch('Controllers.TranscodeQueueController.TranscodingBusinessService') as MockService:
            MockService.GetTranscodeStatus.return_value = {
                'Success': False,
                'Error': 'Job not found',
                'ErrorCode': 'JOB_NOT_FOUND',
                'Timestamp': self.ValidStartTime
            }
            
            response = self.Controller.GetTranscodeStatus(self.InvalidJobId)
            
            # Verify error response structure matches contract
            self.assertIsInstance(response, dict)
            
            # Required error fields from contract
            RequiredErrorFields = ['Error', 'ErrorCode', 'Timestamp']
            for Field in RequiredErrorFields:
                self.assertIn(Field, response, f"Required error field '{Field}' missing from response")
            
            # Verify error values
            self.assertEqual(response['Error'], 'Job not found')
            self.assertEqual(response['ErrorCode'], 'JOB_NOT_FOUND')
            self.assertIsInstance(response['Timestamp'], str)
    
    def TestTranscodeStatusInternalServerError(self):
        """Test error response for internal server error."""
        # This test will FAIL until implementation is complete
        
        with patch('Controllers.TranscodeQueueController.TranscodingBusinessService') as MockService:
            MockService.GetTranscodeStatus.side_effect = Exception("Database connection failed")
            
            response = self.Controller.GetTranscodeStatus(self.ValidJobId)
            
            # Verify error response structure
            self.assertIsInstance(response, dict)
            self.assertIn('Error', response)
            self.assertIn('ErrorCode', response)
            self.assertIn('Timestamp', response)
            
            self.assertIn('Database connection failed', response['Error'])
            self.assertEqual(response['ErrorCode'], 'INTERNAL_SERVER_ERROR')
    
    def TestTranscodeStatusResponseStatusCode(self):
        """Test that correct HTTP status codes are returned."""
        # This test will FAIL until implementation is complete
        
        # Test success case (200)
        with patch('Controllers.TranscodeQueueController.TranscodingBusinessService') as MockService:
            MockService.GetTranscodeStatus.return_value = {
                'Success': True,
                'JobId': self.ValidJobId,
                'FilePath': self.ValidFilePath,
                'Status': 'running',
                'ProgressPercent': 50.0,
                'StartTime': self.ValidStartTime
            }
            
            response, statusCode = self.Controller.GetTranscodeStatus(self.ValidJobId)
            self.assertEqual(statusCode, 200)
        
        # Test not found case (404)
        with patch('Controllers.TranscodeQueueController.TranscodingBusinessService') as MockService:
            MockService.GetTranscodeStatus.return_value = {
                'Success': False,
                'Error': 'Job not found',
                'ErrorCode': 'JOB_NOT_FOUND',
                'Timestamp': self.ValidStartTime
            }
            
            response, statusCode = self.Controller.GetTranscodeStatus(self.InvalidJobId)
            self.assertEqual(statusCode, 404)
        
        # Test server error case (500)
        with patch('Controllers.TranscodeQueueController.TranscodingBusinessService') as MockService:
            MockService.GetTranscodeStatus.side_effect = Exception("Internal error")
            
            response, statusCode = self.Controller.GetTranscodeStatus(self.ValidJobId)
            self.assertEqual(statusCode, 500)
    
    def TestTranscodeStatusValidStatusValues(self):
        """Test that status field only contains valid enum values."""
        # This test will FAIL until implementation is complete
        
        ValidStatusValues = ['running', 'completed', 'failed', 'cancelled']
        
        for Status in ValidStatusValues:
            with patch('Controllers.TranscodeQueueController.TranscodingBusinessService') as MockService:
                MockService.GetTranscodeStatus.return_value = {
                    'Success': True,
                    'JobId': self.ValidJobId,
                    'FilePath': self.ValidFilePath,
                    'Status': Status,
                    'ProgressPercent': 50.0,
                    'StartTime': self.ValidStartTime
                }
                
                response = self.Controller.GetTranscodeStatus(self.ValidJobId)
                self.assertEqual(response['Status'], Status)


if __name__ == '__main__':
    unittest.main()
