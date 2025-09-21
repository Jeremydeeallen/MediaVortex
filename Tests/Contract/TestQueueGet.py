"""
Contract test for GET /api/transcode/queue endpoint.
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


class TestQueueGet(unittest.TestCase):
    """Contract test for GET /api/transcode/queue endpoint."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.Controller = TranscodeQueueController()
        self.ValidTimestamp = "2024-01-15T10:30:00Z"
        
        # Sample queue items for testing
        self.SampleQueueItems = [
            {
                'Id': 1,
                'FilePath': r"C:\Test\Movie1 - 1080p BluRay.mkv",
                'FileName': "Movie1 - 1080p BluRay.mkv",
                'SizeMB': 2500.5,
                'Status': 'pending',
                'AssignedProfile': 'HighQuality',
                'DateAdded': self.ValidTimestamp
            },
            {
                'Id': 2,
                'FilePath': r"C:\Test\Movie2 - 2160p UHD.mkv",
                'FileName': "Movie2 - 2160p UHD.mkv",
                'SizeMB': 1800.3,
                'Status': 'pending',
                'AssignedProfile': 'MediumQuality',
                'DateAdded': self.ValidTimestamp
            },
            {
                'Id': 3,
                'FilePath': r"C:\Test\Movie3 - 720p HD.mkv",
                'FileName': "Movie3 - 720p HD.mkv",
                'SizeMB': 1200.7,
                'Status': 'processing',
                'AssignedProfile': 'LowQuality',
                'DateAdded': self.ValidTimestamp
            }
        ]
    
    def TestQueueGetSuccessResponse(self):
        """Test successful queue retrieval response matches contract schema."""
        # This test will FAIL until implementation is complete
        
        with patch('Controllers.TranscodeQueueController.TranscodingBusinessService') as MockService:
            MockService.GetTranscodeQueue.return_value = {
                'Success': True,
                'Message': 'Queue retrieved successfully',
                'QueueItems': self.SampleQueueItems,
                'TotalItems': 3,
                'TotalSizeMB': 5501.5
            }
            
            response = self.Controller.GetTranscodeQueue()
            
            # Verify response structure matches contract
            self.assertIsInstance(response, dict)
            
            # Required fields from contract
            RequiredFields = ['Message', 'QueueItems', 'TotalItems', 'TotalSizeMB']
            for Field in RequiredFields:
                self.assertIn(Field, response, f"Required field '{Field}' missing from response")
            
            # Verify field types match contract
            self.assertIsInstance(response['Message'], str)
            self.assertIsInstance(response['QueueItems'], list)
            self.assertIsInstance(response['TotalItems'], int)
            self.assertIsInstance(response['TotalSizeMB'], (int, float))
            
            # Verify values
            self.assertEqual(response['Message'], 'Queue retrieved successfully')
            self.assertEqual(response['TotalItems'], 3)
            self.assertEqual(response['TotalSizeMB'], 5501.5)
            self.assertEqual(len(response['QueueItems']), 3)
    
    def TestQueueGetQueueItemStructure(self):
        """Test that queue items have correct structure matching contract schema."""
        # This test will FAIL until implementation is complete
        
        with patch('Controllers.TranscodeQueueController.TranscodingBusinessService') as MockService:
            MockService.GetTranscodeQueue.return_value = {
                'Success': True,
                'Message': 'Queue retrieved successfully',
                'QueueItems': self.SampleQueueItems,
                'TotalItems': 3,
                'TotalSizeMB': 5501.5
            }
            
            response = self.Controller.GetTranscodeQueue()
            queueItems = response['QueueItems']
            
            # Verify each queue item structure
            for Item in queueItems:
                self.assertIsInstance(Item, dict)
                
                # Required fields for each queue item from contract
                RequiredItemFields = ['Id', 'FilePath', 'FileName', 'SizeMB', 'Status', 'AssignedProfile', 'DateAdded']
                for Field in RequiredItemFields:
                    self.assertIn(Field, Item, f"Required field '{Field}' missing from queue item")
                
                # Verify field types
                self.assertIsInstance(Item['Id'], int)
                self.assertIsInstance(Item['FilePath'], str)
                self.assertIsInstance(Item['FileName'], str)
                self.assertIsInstance(Item['SizeMB'], (int, float))
                self.assertIn(Item['Status'], ['pending', 'processing', 'completed', 'failed'])
                self.assertIsInstance(Item['AssignedProfile'], str)
                self.assertIsInstance(Item['DateAdded'], str)
    
    def TestQueueGetEmptyQueue(self):
        """Test response when queue is empty."""
        # This test will FAIL until implementation is complete
        
        with patch('Controllers.TranscodeQueueController.TranscodingBusinessService') as MockService:
            MockService.GetTranscodeQueue.return_value = {
                'Success': True,
                'Message': 'Queue is empty',
                'QueueItems': [],
                'TotalItems': 0,
                'TotalSizeMB': 0.0
            }
            
            response = self.Controller.GetTranscodeQueue()
            
            # Verify response structure
            self.assertIsInstance(response, dict)
            self.assertEqual(response['Message'], 'Queue is empty')
            self.assertEqual(response['QueueItems'], [])
            self.assertEqual(response['TotalItems'], 0)
            self.assertEqual(response['TotalSizeMB'], 0.0)
    
    def TestQueueGetSortedBySize(self):
        """Test that queue items are sorted by size (largest first)."""
        # This test will FAIL until implementation is complete
        
        with patch('Controllers.TranscodeQueueController.TranscodingBusinessService') as MockService:
            MockService.GetTranscodeQueue.return_value = {
                'Success': True,
                'Message': 'Queue retrieved successfully',
                'QueueItems': self.SampleQueueItems,  # Already sorted by size descending
                'TotalItems': 3,
                'TotalSizeMB': 5501.5
            }
            
            response = self.Controller.GetTranscodeQueue()
            queueItems = response['QueueItems']
            
            # Verify items are sorted by SizeMB descending
            for i in range(len(queueItems) - 1):
                self.assertGreaterEqual(
                    queueItems[i]['SizeMB'], 
                    queueItems[i + 1]['SizeMB'],
                    f"Queue items not sorted by size: {queueItems[i]['SizeMB']} should be >= {queueItems[i + 1]['SizeMB']}"
                )
    
    def TestQueueGetInternalServerError(self):
        """Test error response for internal server error."""
        # This test will FAIL until implementation is complete
        
        with patch('Controllers.TranscodeQueueController.TranscodingBusinessService') as MockService:
            MockService.GetTranscodeQueue.side_effect = Exception("Database connection failed")
            
            response = self.Controller.GetTranscodeQueue()
            
            # Verify error response structure
            self.assertIsInstance(response, dict)
            self.assertIn('Error', response)
            self.assertIn('ErrorCode', response)
            self.assertIn('Timestamp', response)
            
            self.assertIn('Database connection failed', response['Error'])
            self.assertEqual(response['ErrorCode'], 'INTERNAL_SERVER_ERROR')
    
    def TestQueueGetResponseStatusCode(self):
        """Test that correct HTTP status codes are returned."""
        # This test will FAIL until implementation is complete
        
        # Test success case (200)
        with patch('Controllers.TranscodeQueueController.TranscodingBusinessService') as MockService:
            MockService.GetTranscodeQueue.return_value = {
                'Success': True,
                'Message': 'Queue retrieved successfully',
                'QueueItems': self.SampleQueueItems,
                'TotalItems': 3,
                'TotalSizeMB': 5501.5
            }
            
            response, statusCode = self.Controller.GetTranscodeQueue()
            self.assertEqual(statusCode, 200)
        
        # Test server error case (500)
        with patch('Controllers.TranscodeQueueController.TranscodingBusinessService') as MockService:
            MockService.GetTranscodeQueue.side_effect = Exception("Internal error")
            
            response, statusCode = self.Controller.GetTranscodeQueue()
            self.assertEqual(statusCode, 500)
    
    def TestQueueGetValidStatusValues(self):
        """Test that status field only contains valid enum values."""
        # This test will FAIL until implementation is complete
        
        ValidStatusValues = ['pending', 'processing', 'completed', 'failed']
        
        with patch('Controllers.TranscodeQueueController.TranscodingBusinessService') as MockService:
            MockService.GetTranscodeQueue.return_value = {
                'Success': True,
                'Message': 'Queue retrieved successfully',
                'QueueItems': self.SampleQueueItems,
                'TotalItems': 3,
                'TotalSizeMB': 5501.5
            }
            
            response = self.Controller.GetTranscodeQueue()
            queueItems = response['QueueItems']
            
            for Item in queueItems:
                self.assertIn(Item['Status'], ValidStatusValues, 
                             f"Invalid status value: {Item['Status']}")
    
    def TestQueueGetTotalSizeCalculation(self):
        """Test that TotalSizeMB is correctly calculated."""
        # This test will FAIL until implementation is complete
        
        with patch('Controllers.TranscodeQueueController.TranscodingBusinessService') as MockService:
            MockService.GetTranscodeQueue.return_value = {
                'Success': True,
                'Message': 'Queue retrieved successfully',
                'QueueItems': self.SampleQueueItems,
                'TotalItems': 3,
                'TotalSizeMB': 5501.5
            }
            
            response = self.Controller.GetTranscodeQueue()
            
            # Calculate expected total size
            ExpectedTotalSize = sum(Item['SizeMB'] for Item in self.SampleQueueItems)
            
            self.assertEqual(response['TotalSizeMB'], ExpectedTotalSize)
            self.assertEqual(response['TotalItems'], len(self.SampleQueueItems))


if __name__ == '__main__':
    unittest.main()
