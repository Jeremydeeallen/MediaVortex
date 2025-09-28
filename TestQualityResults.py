#!/usr/bin/env python3
"""
Test script to verify quality test results are being saved correctly.
This script will:
1. Create test video files
2. Run transcoding with quality testing
3. Verify VMAF results are saved to TranscodeAttempts.VMAF
4. Verify all TranscodeAttempts fields are populated
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
from Models.QualityTestingQueueModel import QualityTestingQueueModel


class QualityTestValidator:
    """Validates quality test results are being saved correctly."""
    
    def __init__(self):
        self.DatabaseManager = DatabaseManager()
        self.QualityOrchestrator = QualityTestingOrchestratorService(self.DatabaseManager)
        self.FFmpegService = FFmpegService()
        self.TestFiles = []
        self.TranscodeAttemptIds = []
        
    def CreateTestVideoFiles(self) -> tuple:
        """Create two test video files for quality testing."""
        try:
            LoggingService.LogInfo("Creating test video files...", "QualityTestValidator", "CreateTestVideoFiles")
            
            # Create temporary directory for test files
            self.TestDir = tempfile.mkdtemp(prefix="quality_test_")
            LoggingService.LogInfo(f"Created test directory: {self.TestDir}", "QualityTestValidator", "CreateTestVideoFiles")
            
            # Create original test file (higher quality)
            OriginalFile = os.path.join(self.TestDir, "original_test.mp4")
            OriginalCommand = [
                "-f", "lavfi", "-i", "testsrc=duration=10:size=1280x720:rate=30",
                "-f", "lavfi", "-i", "sine=frequency=1000:duration=10",
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "aac", "-b:a", "128k",
                "-y", OriginalFile
            ]
            
            # Create transcoded test file (lower quality)
            TranscodedFile = os.path.join(self.TestDir, "transcoded_test.mp4")
            TranscodedCommand = [
                "-i", OriginalFile,
                "-c:v", "libx264", "-preset", "fast", "-crf", "28",
                "-c:a", "aac", "-b:a", "96k",
                "-y", TranscodedFile
            ]
            
            # Execute commands
            LoggingService.LogInfo("Creating original test file...", "QualityTestValidator", "CreateTestVideoFiles")
            result1 = self.FFmpegService.ExecuteFFmpegCommand(OriginalCommand)
            if not result1.get('Success', False):
                raise Exception(f"Failed to create original test file: {result1.get('ErrorMessage', 'Unknown error')}")
            
            LoggingService.LogInfo("Creating transcoded test file...", "QualityTestValidator", "CreateTestVideoFiles")
            result2 = self.FFmpegService.ExecuteFFmpegCommand(TranscodedCommand)
            if not result2.get('Success', False):
                raise Exception(f"Failed to create transcoded test file: {result2.get('ErrorMessage', 'Unknown error')}")
            
            # Verify files exist
            if not os.path.exists(OriginalFile) or not os.path.exists(TranscodedFile):
                raise Exception("Test files were not created successfully")
            
            self.TestFiles = [OriginalFile, TranscodedFile]
            LoggingService.LogInfo(f"Test files created successfully: {self.TestFiles}", "QualityTestValidator", "CreateTestVideoFiles")
            return OriginalFile, TranscodedFile
            
        except Exception as e:
            LoggingService.LogException("Failed to create test video files", e, "QualityTestValidator", "CreateTestVideoFiles")
            raise
    
    def CreateTranscodeAttempts(self) -> list:
        """Create transcode attempt records for testing."""
        try:
            LoggingService.LogInfo("Creating transcode attempt records...", "QualityTestValidator", "CreateTranscodeAttempts")
            
            attempts = []
            for i, file_path in enumerate(self.TestFiles):
                # Create transcode attempt record
                attempt = TranscodeAttemptModel(
                    FilePath=file_path,
                    AttemptDate=datetime.now(),
                    Quality=20 + (i * 5),  # Different quality settings
                    OldSizeBytes=os.path.getsize(file_path),
                    NewSizeBytes=os.path.getsize(file_path) // 2,  # Simulate size reduction
                    Success=True,
                    SizeReductionBytes=os.path.getsize(file_path) // 2,
                    SizeReductionPercent=50.0,
                    ErrorMessage=None,
                    TranscodeDurationSeconds=30.0 + (i * 10),
                    FfpmpegCommand=f"ffmpeg -i {file_path} -c:v libx264 -crf {20 + (i * 5)} output.mp4",
                    AudioBitrateKbps=128 - (i * 16),
                    VideoBitrateKbps=2000 - (i * 500),
                    ProfileName=f"TestProfile{i+1}",
                    VMAF=None  # This should be updated by quality testing
                )
                
                # Save to database
                attempt_id = self.DatabaseManager.SaveTranscodeAttempt(attempt)
                if attempt_id > 0:
                    attempt.Id = attempt_id
                    attempts.append(attempt)
                    self.TranscodeAttemptIds.append(attempt_id)
                    LoggingService.LogInfo(f"Created transcode attempt {attempt_id} for {file_path}", "QualityTestValidator", "CreateTranscodeAttempts")
                else:
                    LoggingService.LogError(f"Failed to save transcode attempt for {file_path}", "QualityTestValidator", "CreateTranscodeAttempts")
            
            return attempts
            
        except Exception as e:
            LoggingService.LogException("Failed to create transcode attempts", e, "QualityTestValidator", "CreateTranscodeAttempts")
            raise
    
    def RunQualityTests(self, attempts: list) -> list:
        """Run quality tests for the transcode attempts."""
        try:
            LoggingService.LogInfo("Running quality tests...", "QualityTestValidator", "RunQualityTests")
            
            quality_jobs = []
            for i, attempt in enumerate(attempts):
                # Create quality testing queue item
                queue_item = QualityTestingQueueModel()
                queue_item.TranscodeAttemptId = attempt.Id
                queue_item.OriginalFilePath = self.TestFiles[0]  # Use original file as reference
                queue_item.TranscodedFilePath = attempt.FilePath
                queue_item.FileName = os.path.basename(attempt.FilePath)
                queue_item.Status = "Pending"
                queue_item.Priority = 50
                queue_item.DateAdded = datetime.now()
                queue_item.QualityThreshold = 90.0
                queue_item.StrategyType = "Single"
                queue_item.RetryCount = 0
                queue_item.MaxRetries = 3
                
                # Save to database
                queue_id = self.DatabaseManager.SaveQualityTestingQueueItem(queue_item)
                if queue_id > 0:
                    queue_item.Id = queue_id
                    quality_jobs.append(queue_item)
                    LoggingService.LogInfo(f"Created quality test job {queue_id} for attempt {attempt.Id}", "QualityTestValidator", "RunQualityTests")
                else:
                    LoggingService.LogError(f"Failed to create quality test job for attempt {attempt.Id}", "QualityTestValidator", "RunQualityTests")
            
            # Process quality tests
            for job in quality_jobs:
                LoggingService.LogInfo(f"Processing quality test job {job.Id}...", "QualityTestValidator", "RunQualityTests")
                result = self.QualityOrchestrator.ProcessQualityTestingRequest(job)
                if result.get('Success', False):
                    LoggingService.LogInfo(f"Quality test job {job.Id} completed: {result.get('Message', '')}", "QualityTestValidator", "RunQualityTests")
                else:
                    LoggingService.LogError(f"Quality test job {job.Id} failed: {result.get('ErrorMessage', '')}", "QualityTestValidator", "RunQualityTests")
            
            return quality_jobs
            
        except Exception as e:
            LoggingService.LogException("Failed to run quality tests", e, "QualityTestValidator", "RunQualityTests")
            raise
    
    def VerifyResults(self, attempts: list) -> dict:
        """Verify that VMAF results are saved correctly."""
        try:
            LoggingService.LogInfo("Verifying quality test results...", "QualityTestValidator", "VerifyResults")
            
            results = {
                'VMAFResults': {},
                'TranscodeAttemptsUpdated': {},
                'QualityTestResults': {},
                'Issues': []
            }
            
            for attempt in attempts:
                attempt_id = attempt.Id
                LoggingService.LogInfo(f"Verifying results for attempt {attempt_id}...", "QualityTestValidator", "VerifyResults")
                
                # Check if VMAF score was updated in TranscodeAttempts
                updated_attempt = self.DatabaseManager.GetTranscodeAttemptById(attempt_id)
                if updated_attempt:
                    results['TranscodeAttemptsUpdated'][attempt_id] = {
                        'VMAF': updated_attempt.VMAF,
                        'FilePath': updated_attempt.FilePath,
                        'Success': updated_attempt.Success,
                        'Quality': updated_attempt.Quality,
                        'ProfileName': updated_attempt.ProfileName
                    }
                    
                    if updated_attempt.VMAF is not None:
                        results['VMAFResults'][attempt_id] = updated_attempt.VMAF
                        LoggingService.LogInfo(f"VMAF score found for attempt {attempt_id}: {updated_attempt.VMAF}", "QualityTestValidator", "VerifyResults")
                    else:
                        results['Issues'].append(f"VMAF score is NULL for attempt {attempt_id}")
                        LoggingService.LogError(f"VMAF score is NULL for attempt {attempt_id}", "QualityTestValidator", "VerifyResults")
                else:
                    results['Issues'].append(f"Could not retrieve updated attempt {attempt_id}")
                    LoggingService.LogError(f"Could not retrieve updated attempt {attempt_id}", "QualityTestValidator", "VerifyResults")
                
                # Check QualityTestResults table
                quality_results = self.DatabaseManager.GetQualityTestResults(TranscodeAttemptId=attempt_id)
                if quality_results:
                    results['QualityTestResults'][attempt_id] = quality_results
                    LoggingService.LogInfo(f"Found {len(quality_results)} quality test results for attempt {attempt_id}", "QualityTestValidator", "VerifyResults")
                else:
                    results['Issues'].append(f"No quality test results found for attempt {attempt_id}")
                    LoggingService.LogError(f"No quality test results found for attempt {attempt_id}", "QualityTestValidator", "VerifyResults")
            
            return results
            
        except Exception as e:
            LoggingService.LogException("Failed to verify results", e, "QualityTestValidator", "VerifyResults")
            raise
    
    def Cleanup(self):
        """Clean up test files and temporary data."""
        try:
            LoggingService.LogInfo("Cleaning up test files...", "QualityTestValidator", "Cleanup")
            
            # Remove test directory
            if hasattr(self, 'TestDir') and os.path.exists(self.TestDir):
                shutil.rmtree(self.TestDir)
                LoggingService.LogInfo(f"Removed test directory: {self.TestDir}", "QualityTestValidator", "Cleanup")
            
            # Clean up database records (optional - for testing purposes)
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
                    
                    LoggingService.LogInfo(f"Cleaned up database records for attempt {attempt_id}", "QualityTestValidator", "Cleanup")
                except Exception as e:
                    LoggingService.LogException(f"Failed to clean up database records for attempt {attempt_id}", e, "QualityTestValidator", "Cleanup")
            
        except Exception as e:
            LoggingService.LogException("Failed to cleanup", e, "QualityTestValidator", "Cleanup")
    
    def RunFullTest(self) -> dict:
        """Run the complete quality test validation."""
        try:
            LoggingService.LogInfo("Starting quality test validation...", "QualityTestValidator", "RunFullTest")
            
            # Step 1: Create test files
            original_file, transcoded_file = self.CreateTestVideoFiles()
            
            # Step 2: Create transcode attempts
            attempts = self.CreateTranscodeAttempts()
            
            # Step 3: Run quality tests
            quality_jobs = self.RunQualityTests(attempts)
            
            # Step 4: Wait a moment for processing
            time.sleep(5)
            
            # Step 5: Verify results
            results = self.VerifyResults(attempts)
            
            # Step 6: Generate report
            report = self.GenerateReport(results)
            
            return report
            
        except Exception as e:
            LoggingService.LogException("Quality test validation failed", e, "QualityTestValidator", "RunFullTest")
            return {
                'Success': False,
                'ErrorMessage': str(e),
                'Results': {}
            }
        finally:
            # Always cleanup
            self.Cleanup()
    
    def GenerateReport(self, results: dict) -> dict:
        """Generate a comprehensive test report."""
        try:
            report = {
                'Success': len(results['Issues']) == 0,
                'Timestamp': datetime.now().isoformat(),
                'VMAFResults': results['VMAFResults'],
                'TranscodeAttemptsUpdated': results['TranscodeAttemptsUpdated'],
                'QualityTestResultsCount': len(results['QualityTestResults']),
                'Issues': results['Issues'],
                'Summary': {
                    'TotalAttempts': len(results['TranscodeAttemptsUpdated']),
                    'VMAFResultsFound': len(results['VMAFResults']),
                    'IssuesFound': len(results['Issues']),
                    'SuccessRate': (len(results['VMAFResults']) / len(results['TranscodeAttemptsUpdated']) * 100) if results['TranscodeAttemptsUpdated'] else 0
                }
            }
            
            LoggingService.LogInfo(f"Test Report: {report['Summary']}", "QualityTestValidator", "GenerateReport")
            return report
            
        except Exception as e:
            LoggingService.LogException("Failed to generate report", e, "QualityTestValidator", "GenerateReport")
            return {'Success': False, 'ErrorMessage': str(e)}


def main():
    """Main function to run the quality test validation."""
    try:
        LoggingService.LogInfo("Starting Quality Test Validation", "Main", "main")
        
        validator = QualityTestValidator()
        report = validator.RunFullTest()
        
        print("\n" + "="*80)
        print("QUALITY TEST VALIDATION REPORT")
        print("="*80)
        print(f"Success: {report.get('Success', False)}")
        print(f"Timestamp: {report.get('Timestamp', 'Unknown')}")
        print(f"Total Attempts: {report.get('Summary', {}).get('TotalAttempts', 0)}")
        print(f"VMAF Results Found: {report.get('Summary', {}).get('VMAFResultsFound', 0)}")
        print(f"Success Rate: {report.get('Summary', {}).get('SuccessRate', 0):.1f}%")
        print(f"Issues Found: {report.get('Summary', {}).get('IssuesFound', 0)}")
        
        if report.get('VMAFResults'):
            print("\nVMAF Results:")
            for attempt_id, vmaf_score in report['VMAFResults'].items():
                print(f"  Attempt {attempt_id}: VMAF = {vmaf_score}")
        
        if report.get('Issues'):
            print("\nIssues:")
            for issue in report['Issues']:
                print(f"  - {issue}")
        
        print("\n" + "="*80)
        
        return report.get('Success', False)
        
    except Exception as e:
        LoggingService.LogException("Quality test validation failed", e, "Main", "main")
        print(f"Error: {str(e)}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
