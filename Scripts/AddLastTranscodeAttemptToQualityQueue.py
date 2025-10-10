#!/usr/bin/env python3
"""
Script to add the last transcode attempt to the quality test queue using ShouldQualityTestService.
This script will:
1. Get the most recent successful transcode attempt
2. Use ShouldQualityTestService to determine if it should be quality tested
3. If yes, create a quality test queue entry
"""

import sys
import os
from datetime import datetime

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Repositories.DatabaseManager import DatabaseManager
from Services.ShouldQualityTestService import ShouldQualityTestService
from Services.LoggingService import LoggingService

def AddLastTranscodeAttemptToQualityQueue():
    """Add the last transcode attempt to quality test queue if it should be tested."""
    try:
        LoggingService.LogInfo("Starting process to add last transcode attempt to quality queue", "AddLastTranscodeAttemptToQualityQueue")
        
        # Initialize services
        DatabaseManagerInstance = DatabaseManager()
        ShouldQualityTest = ShouldQualityTestService()
        
        # Get the most recent successful transcode attempt
        print("Getting the most recent successful transcode attempt...")
        
        query = """
            SELECT ta.Id, ta.FilePath, ta.AttemptDate, ta.Success, ta.ProfileName, ta.OldSizeBytes, ta.NewSizeBytes,
                   tfp.LocalSourcePath, tfp.LocalOutputPath
            FROM TranscodeAttempts ta
            INNER JOIN TemporaryFilePaths tfp ON ta.Id = tfp.TranscodeAttemptId
            WHERE ta.Success = 1 AND tfp.LocalOutputPath IS NOT NULL
            ORDER BY ta.AttemptDate DESC 
            LIMIT 1
        """
        
        attempts = DatabaseManagerInstance.DatabaseService.ExecuteQuery(query)
        
        if not attempts:
            LoggingService.LogWarning("No successful transcode attempts found", "AddLastTranscodeAttemptToQualityQueue")
            print("No successful transcode attempts found in the database.")
            return False
        
        attempt = dict(attempts[0])
        TranscodeAttemptId = attempt['Id']
        OriginalFilePath = attempt['FilePath']  # FilePath is the original file path
        InputFilePath = attempt['LocalSourcePath']
        OutputFilePath = attempt['LocalOutputPath']
        
        print(f"Found most recent transcode attempt:")
        print(f"  ID: {TranscodeAttemptId}")
        print(f"  Original File: {OriginalFilePath}")
        print(f"  Date: {attempt['AttemptDate']}")
        print(f"  Profile: {attempt['ProfileName']}")
        print(f"  Size Reduction: {attempt['NewSizeBytes']} / {attempt['OldSizeBytes']} bytes")
        
        # Get file paths from TemporaryFilePaths table (database-driven approach)
        if not InputFilePath or not OutputFilePath:
            LoggingService.LogError(f"Could not get file paths from TemporaryFilePaths table", "AddLastTranscodeAttemptToQualityQueue")
            print("ERROR: Could not get file paths from TemporaryFilePaths table.")
            return False
        
        print(f"  Local Source: {InputFilePath}")
        print(f"  Local Output: {OutputFilePath}")
        
        # Check if this file should undergo quality testing
        print(f"\nChecking if file should undergo quality testing...")
        ShouldTest = ShouldQualityTest.ShouldTestFile(OriginalFilePath)
        
        if not ShouldTest:
            LoggingService.LogInfo(f"File {OriginalFilePath} should not undergo quality testing", "AddLastTranscodeAttemptToQualityQueue")
            print(f"File should NOT undergo quality testing (excluded by ShouldQualityTestService rules).")
            return False
        
        print(f"File SHOULD undergo quality testing.")
        
        # Check if quality test queue entry already exists for this transcode attempt
        existing_query = """
            SELECT Id FROM QualityTestingQueue 
            WHERE TranscodeAttemptId = ?
        """
        
        existing_entries = DatabaseManagerInstance.DatabaseService.ExecuteQuery(existing_query, (TranscodeAttemptId,))
        
        if existing_entries:
            LoggingService.LogWarning(f"Quality test queue entry already exists for TranscodeAttempt {TranscodeAttemptId}", "AddLastTranscodeAttemptToQualityQueue")
            print(f"Quality test queue entry already exists for this transcode attempt (ID: {existing_entries[0]['Id']}).")
            return False
        
        # Create quality test queue entry with parsed paths from FFmpeg command
        print(f"\nCreating quality test queue entry...")
        print(f"  Original File: {OriginalFilePath}")
        print(f"  Local Source: {InputFilePath}")
        print(f"  Transcoded File: {OutputFilePath}")
        
        QualityTestJobId = DatabaseManagerInstance.CreateQualityTestQueueEntry(
            TranscodeAttemptId, OriginalFilePath, InputFilePath, OutputFilePath
        )
        
        if QualityTestJobId:
            LoggingService.LogInfo(f"Successfully created quality test job {QualityTestJobId} for TranscodeAttempt {TranscodeAttemptId}", "AddLastTranscodeAttemptToQualityQueue")
            print(f"SUCCESS: Quality test queue entry created with ID {QualityTestJobId}")
            print(f"Transcode Attempt ID: {TranscodeAttemptId}")
            print(f"Original File: {OriginalFilePath}")
            print(f"Transcoded File: {OutputFilePath}")
            return True
        else:
            LoggingService.LogError(f"Failed to create quality test queue entry for TranscodeAttempt {TranscodeAttemptId}", "AddLastTranscodeAttemptToQualityQueue")
            print("ERROR: Failed to create quality test queue entry")
            return False
            
    except Exception as e:
        ErrorMsg = f"Error adding last transcode attempt to quality queue: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "AddLastTranscodeAttemptToQualityQueue")
        print(f"ERROR: {ErrorMsg}")
        return False

if __name__ == "__main__":
    print("Adding last transcode attempt to quality test queue...")
    print("=" * 60)
    
    Success = AddLastTranscodeAttemptToQualityQueue()
    
    print("=" * 60)
    if Success:
        print("\nThe quality test queue entry has been successfully created.")
        print("You can now start the QualityCompareService to process this record.")
    else:
        print("\nFailed to create the quality test queue entry.")
        print("Check the logs for more details.")
        sys.exit(1)
