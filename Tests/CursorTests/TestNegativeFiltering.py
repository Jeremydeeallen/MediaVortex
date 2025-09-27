"""
Test negative filtering functionality for Media Files queue.
Tests the ! prefix exclusion filter feature.
"""

import unittest
from unittest.mock import Mock, patch
from ViewModels.FileScanningViewModel import FileScanningViewModel


class TestNegativeFiltering(unittest.TestCase):
    """Test negative filtering functionality in FileScanningViewModel."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.ViewModel = FileScanningViewModel()
        
        # Mock media files with various content types
        self.MockMediaFiles = [
            Mock(Id=1, FileName="Movie_1080p.mp4", FilePath="/path/Movie_1080p.mp4", SizeMB=1000),
            Mock(Id=2, FileName="VR_Experience_360.mp4", FilePath="/path/VR_Experience_360.mp4", SizeMB=2000),
            Mock(Id=3, FileName="HDR_Content_4K.mp4", FilePath="/path/HDR_Content_4K.mp4", SizeMB=3000),
            Mock(Id=4, FileName="Regular_Movie.mp4", FilePath="/path/Regular_Movie.mp4", SizeMB=1500),
            Mock(Id=5, FileName="VR_Game_Playthrough.mp4", FilePath="/path/VR_Game_Playthrough.mp4", SizeMB=2500),
            Mock(Id=6, FileName="360_Degree_Video.mp4", FilePath="/path/360_Degree_Video.mp4", SizeMB=1800),
            Mock(Id=7, FileName="HDR_Movie_4K.mp4", FilePath="/path/HDR_Movie_4K.mp4", SizeMB=4000),
            Mock(Id=8, FileName="Standard_Content.mp4", FilePath="/path/Standard_Content.mp4", SizeMB=1200)
        ]
    
    def TestPositiveFiltering(self):
        """Test positive filtering (existing functionality)."""
        # Test filtering for "VR" - should include only VR files
        with patch.object(self.ViewModel.BusinessService, 'GetMediaFiles', return_value=self.MockMediaFiles):
            result = self.ViewModel.GetMediaFilesPaginated(1, 10, Search="VR")
            
            # Should include VR files
            self.assertGreater(len(result['MediaFiles']), 0)
            for file in result['MediaFiles']:
                self.assertIn("VR", file['FileName'])
    
    def TestNegativeFilteringVR(self):
        """Test negative filtering to exclude VR files."""
        with patch.object(self.ViewModel.BusinessService, 'GetMediaFiles', return_value=self.MockMediaFiles):
            result = self.ViewModel.GetMediaFilesPaginated(1, 10, Search="!VR")
            
            # Should exclude all VR files
            for file in result['MediaFiles']:
                self.assertNotIn("VR", file['FileName'])
    
    def TestNegativeFiltering360(self):
        """Test negative filtering to exclude 360 files."""
        with patch.object(self.ViewModel.BusinessService, 'GetMediaFiles', return_value=self.MockMediaFiles):
            result = self.ViewModel.GetMediaFilesPaginated(1, 10, Search="!360")
            
            # Should exclude all 360 files
            for file in result['MediaFiles']:
                self.assertNotIn("360", file['FileName'])
    
    def TestNegativeFilteringHDR(self):
        """Test negative filtering to exclude HDR files."""
        with patch.object(self.ViewModel.BusinessService, 'GetMediaFiles', return_value=self.MockMediaFiles):
            result = self.ViewModel.GetMediaFilesPaginated(1, 10, Search="!HDR")
            
            # Should exclude all HDR files
            for file in result['MediaFiles']:
                self.assertNotIn("HDR", file['FileName'])
    
    def TestNegativeFilteringCaseInsensitive(self):
        """Test that negative filtering is case insensitive."""
        with patch.object(self.ViewModel.BusinessService, 'GetMediaFiles', return_value=self.MockMediaFiles):
            result = self.ViewModel.GetMediaFilesPaginated(1, 10, Search="!vr")
            
            # Should exclude all VR files (case insensitive)
            for file in result['MediaFiles']:
                self.assertNotIn("VR", file['FileName'])
                self.assertNotIn("vr", file['FileName'])
    
    def TestEmptySearch(self):
        """Test that empty search returns all files."""
        with patch.object(self.ViewModel.BusinessService, 'GetMediaFiles', return_value=self.MockMediaFiles):
            result = self.ViewModel.GetMediaFilesPaginated(1, 10, Search="")
            
            # Should return all files
            self.assertEqual(len(result['MediaFiles']), len(self.MockMediaFiles))
    
    def TestSpecialCharactersInNegativeFilter(self):
        """Test negative filtering with special characters."""
        with patch.object(self.ViewModel.BusinessService, 'GetMediaFiles', return_value=self.MockMediaFiles):
            result = self.ViewModel.GetMediaFilesPaginated(1, 10, Search="!4K")
            
            # Should exclude all 4K files
            for file in result['MediaFiles']:
                self.assertNotIn("4K", file['FileName'])
    
    def TestMultipleNegativeFilters(self):
        """Test that multiple negative filters work (though not implemented yet)."""
        # This test documents current behavior - only single negative filter supported
        with patch.object(self.ViewModel.BusinessService, 'GetMediaFiles', return_value=self.MockMediaFiles):
            result = self.ViewModel.GetMediaFilesPaginated(1, 10, Search="!VR")
            
            # Should exclude VR files but not necessarily 360 files
            vrFiles = [f for f in result['MediaFiles'] if "VR" in f['FileName']]
            self.assertEqual(len(vrFiles), 0, "VR files should be excluded")
    
    def TestNegativeFilterWithNoMatches(self):
        """Test negative filtering when no files match the exclusion term."""
        with patch.object(self.ViewModel.BusinessService, 'GetMediaFiles', return_value=self.MockMediaFiles):
            result = self.ViewModel.GetMediaFilesPaginated(1, 10, Search="!NONEXISTENT")
            
            # Should return all files since no files contain "NONEXISTENT"
            self.assertEqual(len(result['MediaFiles']), len(self.MockMediaFiles))


def RunNegativeFilteringTests():
    """Run all negative filtering tests."""
    print("Running Negative Filtering Tests...")
    
    TestSuite = unittest.TestLoader().loadTestsFromTestCase(TestNegativeFiltering)
    TestRunner = unittest.TextTestRunner(verbosity=2)
    TestResult = TestRunner.run(TestSuite)
    
    if TestResult.wasSuccessful():
        print("✅ All negative filtering tests passed!")
    else:
        print("❌ Some negative filtering tests failed!")
        print(f"Failures: {len(TestResult.failures)}")
        print(f"Errors: {len(TestResult.errors)}")
    
    return TestResult.wasSuccessful()


if __name__ == "__main__":
    RunNegativeFilteringTests()
