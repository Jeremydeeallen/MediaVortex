"""
Contract test for POST /api/transcode/start endpoint.
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


class TestTranscodeStart(unittest.TestCase):
    """Contract test for POST /api/transcode/start endpoint."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.Controller = TranscodeQueueController()
        self.ValidJobId = "test-job-123"
        self.ValidFilePath = r"C:\Test\Movie - 1080p BluRay.mkv"
        self.ValidFileName = "Movie - 1080p BluRay.mkv"
        self.ValidSizeMB = 1500.5
        self.ValidAssignedProfile = "HighQuality"
        self.ValidStartTime = "2024-01-15T10:30:00Z"
    
    def test_transcode_start_success_response(self):
        """Test successful transcoding start response matches contract schema."""
        # This test will FAIL until implementation is complete
        # Expected response structure from TranscodeStartContract.json
        
        # Mock the transcoding service to return success
        with patch('Controllers.TranscodeQueueController.TranscodingBusinessService') as MockService:
            MockService.StartTranscoding.return_value = {
                'Success': True,
                'JobId': self.ValidJobId,
                'FilePath': self.ValidFilePath,
                'FileName': self.ValidFileName,
                'SizeMB': self.ValidSizeMB,
                'AssignedProfile': self.ValidAssignedProfile,
                'Status': 'processing',
                'StartTime': self.ValidStartTime
            }
            
            # Make the API call
            response = self.Controller.StartTranscoding()
            
            # Verify response structure matches contract
            self.assertIsInstance(response, dict)
            
            # Required fields from contract
            RequiredFields = ['JobId', 'FilePath', 'FileName', 'SizeMB', 'AssignedProfile', 'Status', 'StartTime']
            for Field in RequiredFields:
                self.assertIn(Field, response, f"Required field '{Field}' missing from response")
            
            # Verify field types match contract
            self.assertIsInstance(response['JobId'], str)
            self.assertIsInstance(response['FilePath'], str)
            self.assertIsInstance(response['FileName'], str)
            self.assertIsInstance(response['SizeMB'], (int, float))
            self.assertIsInstance(response['AssignedProfile'], str)
            self.assertEqual(response['Status'], 'processing')
            self.assertIsInstance(response['StartTime'], str)
            
            # Verify values
            self.assertEqual(response['JobId'], self.ValidJobId)
            self.assertEqual(response['FilePath'], self.ValidFilePath)
            self.assertEqual(response['FileName'], self.ValidFileName)
            self.assertEqual(response['SizeMB'], self.ValidSizeMB)
            self.assertEqual(response['AssignedProfile'], self.ValidAssignedProfile)
    
    def test_transcode_start_no_queue_items(self):
        """Test error response when no items in queue."""
        # This test will FAIL until implementation is complete
        
        with patch('Controllers.TranscodeQueueController.TranscodingBusinessService') as MockService:
            MockService.StartTranscoding.return_value = {
                'Success': False,
                'Error': 'No items in queue',
                'ErrorCode': 'NO_QUEUE_ITEMS',
                'Timestamp': self.ValidStartTime
            }
            
            response = self.Controller.StartTranscoding()
            
            # Verify error response structure matches contract
            self.assertIsInstance(response, dict)
            
            # Required error fields from contract
            RequiredErrorFields = ['Error', 'ErrorCode', 'Timestamp']
            for Field in RequiredErrorFields:
                self.assertIn(Field, response, f"Required error field '{Field}' missing from response")
            
            # Verify error values
            self.assertEqual(response['Error'], 'No items in queue')
            self.assertEqual(response['ErrorCode'], 'NO_QUEUE_ITEMS')
            self.assertIsInstance(response['Timestamp'], str)
    
    def test_transcode_start_invalid_request(self):
        """Test error response for invalid request."""
        # This test will FAIL until implementation is complete
        
        with patch('Controllers.TranscodeQueueController.TranscodingBusinessService') as MockService:
            MockService.StartTranscoding.return_value = {
                'Success': False,
                'Error': 'Invalid request parameters',
                'ErrorCode': 'INVALID_REQUEST',
                'Timestamp': self.ValidStartTime
            }
            
            response = self.Controller.StartTranscoding()
            
            # Verify error response structure
            self.assertIsInstance(response, dict)
            self.assertIn('Error', response)
            self.assertIn('ErrorCode', response)
            self.assertIn('Timestamp', response)
            
            self.assertEqual(response['Error'], 'Invalid request parameters')
            self.assertEqual(response['ErrorCode'], 'INVALID_REQUEST')
    
    def test_transcode_start_internal_server_error(self):
        """Test error response for internal server error."""
        # This test will FAIL until implementation is complete
        
        with patch('Controllers.TranscodeQueueController.TranscodingBusinessService') as MockService:
            MockService.StartTranscoding.side_effect = Exception("Database connection failed")
            
            response = self.Controller.StartTranscoding()
            
            # Verify error response structure
            self.assertIsInstance(response, dict)
            self.assertIn('Error', response)
            self.assertIn('ErrorCode', response)
            self.assertIn('Timestamp', response)
            
            self.assertIn('Database connection failed', response['Error'])
            self.assertEqual(response['ErrorCode'], 'INTERNAL_SERVER_ERROR')
    
    def test_transcode_start_response_status_code(self):
        """Test that correct HTTP status codes are returned."""
        # This test will FAIL until implementation is complete
        
        # Test success case (200)
        with patch('Controllers.TranscodeQueueController.TranscodingBusinessService') as MockService:
            MockService.StartTranscoding.return_value = {
                'Success': True,
                'JobId': self.ValidJobId,
                'FilePath': self.ValidFilePath,
                'FileName': self.ValidFileName,
                'SizeMB': self.ValidSizeMB,
                'AssignedProfile': self.ValidAssignedProfile,
                'Status': 'processing',
                'StartTime': self.ValidStartTime
            }
            
            response, statusCode = self.Controller.StartTranscoding()
            self.assertEqual(statusCode, 200)
        
        # Test error case (400)
        with patch('Controllers.TranscodeQueueController.TranscodingBusinessService') as MockService:
            MockService.StartTranscoding.return_value = {
                'Success': False,
                'Error': 'No items in queue',
                'ErrorCode': 'NO_QUEUE_ITEMS',
                'Timestamp': self.ValidStartTime
            }
            
            response, statusCode = self.Controller.StartTranscoding()
            self.assertEqual(statusCode, 400)
        
        # Test server error case (500)
        with patch('Controllers.TranscodeQueueController.TranscodingBusinessService') as MockService:
            MockService.StartTranscoding.side_effect = Exception("Internal error")
            
            response, statusCode = self.Controller.StartTranscoding()
            self.assertEqual(statusCode, 500)


if __name__ == '__main__':
    unittest.main()
