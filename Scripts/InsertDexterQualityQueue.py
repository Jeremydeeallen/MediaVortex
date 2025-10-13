"""
DEPRECATED: Script to manually insert the Dexter S06E07 quality testing record into the queue.
This script is deprecated because it uses the old SaveQualityTestingQueueItem method that no longer exists.
Use QualityTestQueueService.AddToQualityTestQueue() instead.

This prevents having to retranscode the file.
"""

import sys
import os
from datetime import datetime

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Repositories.DatabaseManager import DatabaseManager
from Models.QualityTestingQueueModel import QualityTestingQueueModel
from Services.LoggingService import LoggingService

def InsertDexterQualityQueueRecord():
    """DEPRECATED: Insert the Dexter S06E07 quality testing record into the queue."""
    print("WARNING: This script is deprecated and will not work with the current database schema.")
    print("Use QualityTestQueueService.AddToQualityTestQueue() instead.")
    return False
    
    try:
        LoggingService.LogInfo("Starting manual insertion of Dexter S06E07 quality queue record", "InsertDexterQualityQueueRecord")
        
        # Initialize database manager
        DatabaseManagerInstance = DatabaseManager()
        
        # Create quality testing queue item with data from the log
        QueueItem = QualityTestingQueueModel()
        QueueItem.TranscodeAttemptId = 151  # From the log: "Updated 1 rows for attempt 151"
        QueueItem.OriginalFilePath = r"T:\Dexter\Season 6\Dexter - S06E07 - Nebraska Bluray-1080p.mkv"
        QueueItem.TranscodedFilePath = r"C:\MediaVortex\Dexter - S06E07 - Nebraska Bluray-720p.mp4"
        QueueItem.FileName = "Dexter - S06E07 - Nebraska Bluray-720p.mp4"  # Extracted from output path
        QueueItem.Status = "Pending"
        QueueItem.Priority = 50
        QueueItem.DateAdded = datetime.now()
        QueueItem.QualityThreshold = 90.0  # Default threshold
        QueueItem.StrategyType = "Single"  # Default strategy
        QueueItem.RetryCount = 0
        QueueItem.MaxRetries = 3
        
        # Save to database
        QueueId = DatabaseManagerInstance.SaveQualityTestingQueueItem(QueueItem)
        
        if QueueId > 0:
            LoggingService.LogInfo(f"Successfully inserted Dexter S06E07 quality queue record with ID {QueueId}", "InsertDexterQualityQueueRecord")
            print(f"SUCCESS: Quality testing record inserted with ID {QueueId}")
            print(f"Original File: {QueueItem.OriginalFilePath}")
            print(f"Transcoded File: {QueueItem.TranscodedFilePath}")
            print(f"File Name: {QueueItem.FileName}")
            print(f"Transcode Attempt ID: {QueueItem.TranscodeAttemptId}")
            return True
        else:
            LoggingService.LogError("Failed to insert Dexter S06E07 quality queue record", "InsertDexterQualityQueueRecord")
            print("ERROR: Failed to insert quality testing record")
            return False
            
    except Exception as e:
        ErrorMsg = f"Error inserting Dexter S06E07 quality queue record: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "InsertDexterQualityQueueRecord")
        print(f"ERROR: {ErrorMsg}")
        return False

if __name__ == "__main__":
    print("Inserting Dexter S06E07 quality testing record into queue...")
    Success = InsertDexterQualityQueueRecord()
    if Success:
        print("\nThe quality testing record has been successfully inserted.")
        print("You can now start the QualityCompareService to process this record.")
    else:
        print("\nFailed to insert the quality testing record.")
        sys.exit(1)
