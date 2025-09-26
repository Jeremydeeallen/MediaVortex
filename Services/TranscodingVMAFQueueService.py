from typing import Dict, Any
from datetime import datetime
from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


class TranscodingVMAFQueueService:
    """Minimal VMAF queue service for transcoding operations only."""
    
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
    
    def AddToQueue(self, JobId: int, OriginalFilePath: str, OutputFilePath: str) -> Dict[str, Any]:
        """Add a completed transcoding job to the VMAF queue for later quality assessment."""
        try:
            LoggingService.LogFunctionEntry("AddToQueue", "TranscodingVMAFQueueService", JobId, OriginalFilePath, OutputFilePath)
            
            # Get file name from output path
            FileName = OutputFilePath.split('\\')[-1] if '\\' in OutputFilePath else OutputFilePath.split('/')[-1]
            
            # Add to VMAF queue table
            query = """
                INSERT INTO VMAFQueue (TranscodeAttemptId, OriginalFilePath, TranscodedFilePath, FileName, 
                                     Status, Priority, DateAdded, QualityThreshold, RetryCount, MaxRetries)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            parameters = (
                JobId,  # TranscodeAttemptId
                OriginalFilePath,  # OriginalFilePath (now available from transcoding context)
                OutputFilePath,  # TranscodedFilePath
                FileName,  # FileName
                'Pending',  # Status
                50,  # Priority (default)
                datetime.now(),  # DateAdded
                90.0,  # QualityThreshold (default)
                0,  # RetryCount
                3   # MaxRetries
            )
            
            self.DatabaseManager.DatabaseService.ExecuteNonQuery(query, parameters)
            
            LoggingService.LogInfo(f"Added job {JobId} to VMAF queue for quality assessment", "TranscodingVMAFQueueService", "AddToQueue")
            
            return {
                "Success": True,
                "Message": f"Added job {JobId} to VMAF queue for quality assessment"
            }
            
        except Exception as e:
            LoggingService.LogException("Exception adding to VMAF queue", e, "TranscodingVMAFQueueService", "AddToQueue")
            return {
                "Success": False,
                "ErrorMessage": f"Exception adding to VMAF queue: {str(e)}"
            }
