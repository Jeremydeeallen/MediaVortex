#!/usr/bin/env python3
"""
Quality Test Queue Service
Business logic layer for quality testing queue operations
Implements MVVM pattern using MVVM architecture
"""

import os
from typing import Optional, Dict, Any
from Services.LoggingService import LoggingService
from Repositories.DatabaseManager import DatabaseManager


class QualityTestQueueService:
    """Business service for quality testing queue operations."""
    
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None):
        """Initialize the service with dependencies."""
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        # LoggingService.LogInfo("QualityTestQueueService initialized", "QualityTestQueueService", "__init__")
    
    def AddToQualityTestQueue(self, TranscodeAttemptId: int) -> Optional[int]:
        """
        Add a transcode attempt to the quality testing queue.
        Retrieves all necessary file paths from TemporaryFilePaths table.
        
        Args:
            TranscodeAttemptId: ID of the successful transcode attempt
            
        Returns:
            JobId if successful, None if failed
        """
        try:
            LoggingService.LogFunctionEntry("AddToQualityTestQueue", "QualityTestQueueService", TranscodeAttemptId)
            
            # Validate TranscodeAttemptId exists and was successful
            Attempt = self.DatabaseManager.GetTranscodeAttemptById(TranscodeAttemptId)
            if not Attempt:
                LoggingService.LogError(f"TranscodeAttempt {TranscodeAttemptId} not found", "QualityTestQueueService", "AddToQualityTestQueue")
                return None
            
            if not Attempt.Success:
                LoggingService.LogError(f"TranscodeAttempt {TranscodeAttemptId} was not successful", "QualityTestQueueService", "AddToQualityTestQueue")
                return None
            
            # Check for duplicate queue entries
            existing_query = """
                SELECT Id FROM QualityTestingQueue 
                WHERE TranscodeAttemptId = ?
            """
            existing_entries = self.DatabaseManager.DatabaseService.ExecuteQuery(existing_query, (TranscodeAttemptId,))
            
            if existing_entries:
                existing_id = existing_entries[0]['Id']
                LoggingService.LogWarning(f"Quality test queue entry already exists for TranscodeAttempt {TranscodeAttemptId} (ID: {existing_id})", 
                                        "QualityTestQueueService", "AddToQualityTestQueue")
                return existing_id
            
            # Query TemporaryFilePaths table for file paths
            temporary_paths_query = """
                SELECT OriginalPath, LocalSourcePath, LocalOutputPath
                FROM TemporaryFilePaths 
                WHERE TranscodeAttemptId = ?
            """
            temporary_paths_rows = self.DatabaseManager.DatabaseService.ExecuteQuery(temporary_paths_query, (TranscodeAttemptId,))
            
            if not temporary_paths_rows:
                LoggingService.LogError(f"No TemporaryFilePaths record found for TranscodeAttempt {TranscodeAttemptId}", 
                                      "QualityTestQueueService", "AddToQualityTestQueue")
                return None
            
            # Convert sqlite3.Row to dictionary - use dict() constructor like other code in codebase
            row = temporary_paths_rows[0]
            temporary_paths = dict(row)
            OriginalFilePath = temporary_paths.get('OriginalPath')
            LocalSourcePath = temporary_paths.get('LocalSourcePath')
            TranscodedFilePath = temporary_paths.get('LocalOutputPath')
            
            if not OriginalFilePath or not LocalSourcePath or not TranscodedFilePath:
                LoggingService.LogError(f"Missing file paths in TemporaryFilePaths for TranscodeAttempt {TranscodeAttemptId}", 
                                      "QualityTestQueueService", "AddToQualityTestQueue")
                return None
            
            # Call DatabaseManager to create the queue entry
            JobId = self.DatabaseManager.CreateQualityTestQueueEntry(
                TranscodeAttemptId, OriginalFilePath, LocalSourcePath, TranscodedFilePath
            )
            
            if JobId:
                LoggingService.LogInfo(f"Successfully added TranscodeAttempt {TranscodeAttemptId} to quality test queue with JobId {JobId}", 
                                     "QualityTestQueueService", "AddToQualityTestQueue")
                return JobId
            else:
                LoggingService.LogError(f"Failed to create quality test queue entry for TranscodeAttempt {TranscodeAttemptId}", 
                                      "QualityTestQueueService", "AddToQualityTestQueue")
                return None
                
        except Exception as e:
            LoggingService.LogException("Exception adding to quality test queue", e, "QualityTestQueueService", "AddToQualityTestQueue")
            return None
