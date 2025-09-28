#!/usr/bin/env python3
"""
Test script to verify VMAF results are properly saved to TranscodeAttempts.VMAF field.
This script will:
1. Create test video files
2. Simulate a transcode attempt
3. Run quality testing to populate VMAF
4. Verify VMAF field is populated in TranscodeAttempts table
"""

import os
import sys
import time
import tempfile
import shutil
from datetime import datetime
from pathlib import Path

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from Repositories.DatabaseManager import DatabaseManager
from Services.QualityTestingOrchestratorService import QualityTestingOrchestratorService
from Services.FFmpegService import FFmpegService
from Services.LoggingService import LoggingService
from Models.TranscodeAttemptModel import TranscodeAttemptModel


class TranscodeAttemptsVMAFTest:
    """Test VMAF population in TranscodeAttempts table."""
    
    def __init__(self):
        self.DatabaseManager = DatabaseManager()
        self.QualityOrchestrator = QualityTestingOrchestratorService(self.DatabaseManager)
        self.FFmpegService = FFmpegService()
        self.TestFiles = []
        self.TranscodeAttemptIds = []
        
    def CreateTestVideoFiles(self) -> tuple:
        """Create test video files for transcoding simulation."""
        try:
            LoggingService.LogInfo("Creating test video files...", "TranscodeAttemptsVMAFTest", "CreateTestVideoFiles")
            
            # Create temporary directory for test files
            self.TestDir = tempfile.mkdtemp(prefix="transcode_test_")
            LoggingService.LogInfo(f"Created test directory: {self.TestDir}", "TranscodeAttemptsVMAFTest", "CreateTestVideoFiles")
            
            # Create original test file (higher quality)
            OriginalFile = os.path.join(self.TestDir, "original_test.mp4")
            OriginalCommand = [
                "-f", "lavfi", "-i", "testsrc=duration=15:size=1920x1080:rate=30",
                "-f", "lavfi", "-i", "sine=frequency=1000:duration=15",
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k",
                "-y", OriginalFile
            ]
            
            # Create transcoded test file (lower quality)
            TranscodedFile = os.path.join(self.TestDir, "transcoded_test.mp4")
            TranscodedCommand = [
                "-i", OriginalFile,
                "-c:v", "libx264", "-preset", "fast", "-crf", "28",
                "-c:a", "aac", "-b:a", "128k",
                "-y", TranscodedFile
            ]
            
            # Execute commands
            LoggingService.LogInfo("Creating original test file...", "TranscodeAttemptsVMAFTest", "CreateTestVideoFiles")
            result1 = self.FFmpegService.ExecuteFFmpegCommand(OriginalCommand)
            if not result1.get('Success', False):
                raise Exception(f"Failed to create original test file: {result1.get('ErrorMessage', 'Unknown error')}")
            
            LoggingService.LogInfo("Creating transcoded test file...", "TranscodeAttemptsVMAFTest", "CreateTestVideoFiles")
            result2 = self.FFmpegService.ExecuteFFmpegCommand(TranscodedCommand)
            if not result2.get('Success', False):
                raise Exception(f"Failed to create transcoded test file: {result2.get('ErrorMessage', 'Unknown error')}")
            
            # Verify files exist
            if not os.path.exists(OriginalFile) or not os.path.exists(TranscodedFile):
                raise Exception("Test files were not created successfully")
            
            self.TestFiles = [OriginalFile, TranscodedFile]
            LoggingService.LogInfo(f"Test files created successfully: {self.TestFiles}", "TranscodeAttemptsVMAFTest", "CreateTestVideoFiles")
            return OriginalFile, TranscodedFile
            
        except Exception as e:
            LoggingService.LogException("Failed to create test video files", e, "TranscodeAttemptsVMAFTest", "CreateTestVideoFiles")
            raise
    
    def SimulateTranscodeAttempt(self, OriginalFile: str, TranscodedFile: str) -> int:
        """Simulate a transcode attempt and create TranscodeAttempts record."""
        try:
            LoggingService.LogInfo("Simulating transcode attempt...", "TranscodeAttemptsVMAFTest", "SimulateTranscodeAttempt")
            
            # Get file sizes
            OriginalSize = os.path.getsize(OriginalFile)
            TranscodedSize = os.path.getsize(TranscodedFile)
            SizeReduction = OriginalSize - TranscodedSize
            SizeReductionPercent = (SizeReduction / OriginalSize) * 100 if OriginalSize > 0 else 0
            
            # Create transcode attempt record
            attempt = TranscodeAttemptModel(
                FilePath=OriginalFile,
                AttemptDate=datetime.now(),
                Quality=23,  # CRF 23
                OldSizeBytes=OriginalSize,
                NewSizeBytes=TranscodedSize,
                Success=True,
                SizeReductionBytes=SizeReduction,
                SizeReductionPercent=SizeReductionPercent,
                ErrorMessage=None,
                TranscodeDurationSeconds=45.0,  # Simulated duration
                FfpmpegCommand=f"ffmpeg -i {OriginalFile} -c:v libx264 -crf 23 -c:a aac -b:a 128k {TranscodedFile}",
                AudioBitrateKbps=128,
                VideoBitrateKbps=2500,
                ProfileName="TestProfile",
                VMAF=None  # This should be updated by quality testing
            )
            
            # Save to database
            attempt_id = self.DatabaseManager.SaveTranscodeAttempt(attempt)
            if attempt_id > 0:
                attempt.Id = attempt_id
                self.TranscodeAttemptIds.append(attempt_id)
                LoggingService.LogInfo(f"Created transcode attempt {attempt_id} for {OriginalFile}", "TranscodeAttemptsVMAFTest", "SimulateTranscodeAttempt")
                return attempt_id
            else:
                raise Exception("Failed to save transcode attempt to database")
            
        except Exception as e:
            LoggingService.LogException("Failed to simulate transcode attempt", e, "TranscodeAttemptsVMAFTest", "SimulateTranscodeAttempt")
            raise
    
    def RunQualityTest(self, TranscodeAttemptId: int, OriginalFile: str, TranscodedFile: str) -> dict:
        """Run quality test and populate VMAF score."""
        try:
            LoggingService.LogInfo(f"Running quality test for attempt {TranscodeAttemptId}...", "TranscodeAttemptsVMAFTest", "RunQualityTest")
            
            # Create quality testing queue item
            from Models.QualityTestingQueueModel import QualityTestingQueueModel
            queue_item = QualityTestingQueueModel()
            queue_item.TranscodeAttemptId = TranscodeAttemptId
            queue_item.OriginalFilePath = OriginalFile
            queue_item.TranscodedFilePath = TranscodedFile
            queue_item.FileName = os.path.basename(TranscodedFile)
            queue_item.Status = "Pending"
            queue_item.Priority = 50
            queue_item.DateAdded = datetime.now()
            queue_item.QualityThreshold = 90.0
            queue_item.StrategyType = "Single"
            queue_item.RetryCount = 0
            queue_item.MaxRetries = 3
            
            # Save to database
            queue_id = self.DatabaseManager.SaveQualityTestingQueueItem(queue_item)
            if queue_id <= 0:
                raise Exception("Failed to create quality testing queue item")
            
            queue_item.Id = queue_id
            LoggingService.LogInfo(f"Created quality test job {queue_id} for attempt {TranscodeAttemptId}", "TranscodeAttemptsVMAFTest", "RunQualityTest")
            
            # Process quality test
            result = self.QualityOrchestrator.ProcessQualityTestingRequest(queue_item)
            if not result.get('Success', False):
                raise Exception(f"Quality test failed: {result.get('ErrorMessage', 'Unknown error')}")
            
            LoggingService.LogInfo(f"Quality test completed for attempt {TranscodeAttemptId}: {result.get('Message', '')}", "TranscodeAttemptsVMAFTest", "RunQualityTest")
            return result
            
        except Exception as e:
            LoggingService.LogException("Failed to run quality test", e, "TranscodeAttemptsVMAFTest", "RunQualityTest")
            raise
    
    def VerifyTranscodeAttemptsVMAF(self, TranscodeAttemptId: int) -> dict:
        """Verify that VMAF score is populated in TranscodeAttempts table."""
        try:
            LoggingService.LogInfo(f"Verifying VMAF score for attempt {TranscodeAttemptId}...", "TranscodeAttemptsVMAFTest", "VerifyTranscodeAttemptsVMAF")
            
            # Get the updated transcode attempt
            attempt = self.DatabaseManager.GetTranscodeAttemptById(TranscodeAttemptId)
            if not attempt:
                return {
                    'Success': False,
                    'ErrorMessage': f"Could not retrieve transcode attempt {TranscodeAttemptId}",
                    'VMAFScore': None,
                    'AllFields': {}
                }
            
            # Check all fields
            all_fields = {
                'Id': attempt.Id,
                'FilePath': attempt.FilePath,
                'AttemptDate': attempt.AttemptDate,
                'Quality': attempt.Quality,
                'OldSizeBytes': attempt.OldSizeBytes,
                'NewSizeBytes': attempt.NewSizeBytes,
                'Success': attempt.Success,
                'SizeReductionBytes': attempt.SizeReductionBytes,
                'SizeReductionPercent': attempt.SizeReductionPercent,
                'ErrorMessage': attempt.ErrorMessage,
                'TranscodeDurationSeconds': attempt.TranscodeDurationSeconds,
                'FfpmpegCommand': attempt.FfpmpegCommand,
                'AudioBitrateKbps': attempt.AudioBitrateKbps,
                'VideoBitrateKbps': attempt.VideoBitrateKbps,
                'ProfileName': attempt.ProfileName,
                'VMAF': attempt.VMAF  # This is the critical field
            }
            
            # Check if VMAF is populated
            vmaf_populated = attempt.VMAF is not None
            success = vmaf_populated
            
            result = {
                'Success': success,
                'VMAFScore': attempt.VMAF,
                'VMAFPopulated': vmaf_populated,
                'AllFields': all_fields,
                'ErrorMessage': None if success else "VMAF score is not populated"
            }
            
            if success:
                LoggingService.LogInfo(f"VMAF score successfully populated for attempt {TranscodeAttemptId}: {attempt.VMAF}", "TranscodeAttemptsVMAFTest", "VerifyTranscodeAttemptsVMAF")
            else:
                LoggingService.LogError(f"VMAF score is NULL for attempt {TranscodeAttemptId}", "TranscodeAttemptsVMAFTest", "VerifyTranscodeAttemptsVMAF")
            
            return result
            
        except Exception as e:
            LoggingService.LogException("Failed to verify transcode attempt VMAF", e, "TranscodeAttemptsVMAFTest", "VerifyTranscodeAttemptsVMAF")
            return {
                'Success': False,
                'ErrorMessage': str(e),
                'VMAFScore': None,
                'AllFields': {}
            }
    
    def Cleanup(self):
        """Clean up test files and database records."""
        try:
            LoggingService.LogInfo("Cleaning up test files and database records...", "TranscodeAttemptsVMAFTest", "Cleanup")
            
            # Remove test directory
            if hasattr(self, 'TestDir') and os.path.exists(self.TestDir):
                shutil.rmtree(self.TestDir)
                LoggingService.LogInfo(f"Removed test directory: {self.TestDir}", "TranscodeAttemptsVMAFTest", "Cleanup")
            
            # Clean up database records
            for attempt_id in self.TranscodeAttemptIds:
                try:
                    # Get quality test results to clean up
                    quality_results = self.DatabaseManager.GetQualityTestResults(TranscodeAttemptId=attempt_id)
                    for result in quality_results:
                        # Delete quality test results
                        self.DatabaseManager.DatabaseService.ExecuteNonQuery(
                            "DELETE FROM QualityTestResults WHERE Id = ?", 
                            (result['Id'],)
                        )
                    
                    # Delete quality test progress
                    self.DatabaseManager.DatabaseService.ExecuteNonQuery(
                        "DELETE FROM QualityTestProgress WHERE TranscodeAttemptId = ?", 
                        (attempt_id,)
                    )
                    
                    # Delete quality testing queue items
                    self.DatabaseManager.DatabaseService.ExecuteNonQuery(
                        "DELETE FROM QualityTestingQueue WHERE TranscodeAttemptId = ?", 
                        (attempt_id,)
                    )
                    
                    # Delete transcode attempts
                    self.DatabaseManager.DatabaseService.ExecuteNonQuery(
                        "DELETE FROM TranscodeAttempts WHERE Id = ?", 
                        (attempt_id,)
                    )
                    
                    LoggingService.LogInfo(f"Cleaned up database records for attempt {attempt_id}", "TranscodeAttemptsVMAFTest", "Cleanup")
                except Exception as e:
                    LoggingService.LogException(f"Failed to clean up database records for attempt {attempt_id}", e, "TranscodeAttemptsVMAFTest", "Cleanup")
            
        except Exception as e:
            LoggingService.LogException("Failed to cleanup", e, "TranscodeAttemptsVMAFTest", "Cleanup")
    
    def RunFullTest(self) -> dict:
        """Run the complete VMAF test for TranscodeAttempts."""
        try:
            LoggingService.LogInfo("Starting TranscodeAttempts VMAF test...", "TranscodeAttemptsVMAFTest", "RunFullTest")
            
            # Step 1: Create test files
            original_file, transcoded_file = self.CreateTestVideoFiles()
            
            # Step 2: Simulate transcode attempt
            attempt_id = self.SimulateTranscodeAttempt(original_file, transcoded_file)
            
            # Step 3: Run quality test
            quality_result = self.RunQualityTest(attempt_id, original_file, transcoded_file)
            
            # Step 4: Wait a moment for processing
            time.sleep(2)
            
            # Step 5: Verify VMAF is populated in TranscodeAttempts
            verification_result = self.VerifyTranscodeAttemptsVMAF(attempt_id)
            
            # Step 6: Generate report
            report = {
                'Success': verification_result['Success'],
                'TranscodeAttemptId': attempt_id,
                'VMAFScore': verification_result['VMAFScore'],
                'VMAFPopulated': verification_result['VMAFPopulated'],
                'QualityTestResult': quality_result,
                'AllFields': verification_result['AllFields'],
                'ErrorMessage': verification_result['ErrorMessage'],
                'Timestamp': datetime.now().isoformat()
            }
            
            return report
            
        except Exception as e:
            LoggingService.LogException("TranscodeAttempts VMAF test failed", e, "TranscodeAttemptsVMAFTest", "RunFullTest")
            return {
                'Success': False,
                'ErrorMessage': str(e),
                'VMAFScore': None,
                'AllFields': {}
            }
        finally:
            # Always cleanup
            self.Cleanup()


def main():
    """Main function to run the TranscodeAttempts VMAF test."""
    try:
        LoggingService.LogInfo("Starting TranscodeAttempts VMAF Test", "Main", "main")
        
        tester = TranscodeAttemptsVMAFTest()
        report = tester.RunFullTest()
        
        print("\n" + "="*80)
        print("TRANSCODE ATTEMPTS VMAF TEST REPORT")
        print("="*80)
        print(f"Success: {report.get('Success', False)}")
        print(f"TranscodeAttemptId: {report.get('TranscodeAttemptId', 'N/A')}")
        print(f"VMAF Score: {report.get('VMAFScore', 'NULL')}")
        print(f"VMAF Populated: {report.get('VMAFPopulated', False)}")
        print(f"Timestamp: {report.get('Timestamp', 'Unknown')}")
        
        if report.get('ErrorMessage'):
            print(f"Error: {report['ErrorMessage']}")
        
        if report.get('AllFields'):
            print("\nTranscodeAttempts Fields:")
            for field, value in report['AllFields'].items():
                print(f"  {field}: {value}")
        
        print("\n" + "="*80)
        
        return report.get('Success', False)
        
    except Exception as e:
        LoggingService.LogException("TranscodeAttempts VMAF test failed", e, "Main", "main")
        print(f"Error: {str(e)}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
