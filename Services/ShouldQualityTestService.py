#!/usr/bin/env python3
"""
Should Quality Test Service
Simple service to determine if a transcoded file should undergo quality testing
"""

import os
from typing import Optional, Dict, Any
from Services.LoggingService import LoggingService
from Repositories.DatabaseManager import DatabaseManager
from Services.QualityTestQueueService import QualityTestQueueService


class ShouldQualityTestService:
    """Simple service to determine if a file should undergo quality testing."""
    
    def __init__(self):
        """Initialize the service."""
        self.DatabaseManager = DatabaseManager()
        self.QualityTestQueue = QualityTestQueueService(self.DatabaseManager)
            # LoggingService.LogInfo("ShouldQualityTestService initialized", "ShouldQualityTestService", "__init__")
    
    def ShouldTestFile(self, FilePath: str) -> bool:
        """
        Determine if a file should undergo quality testing.
        
        Args:
            FilePath: Path to the transcoded file
            
        Returns:
            bool: True if file should be quality tested, False otherwise
        """
        try:
            LoggingService.LogFunctionEntry("ShouldTestFile", "ShouldQualityTestService", FilePath)
            
            # Test all files by default
            ShouldTest = True
            
                          # LoggingService.LogInfo(f"Quality test decision for {FilePath}: {ShouldTest}", "ShouldQualityTestService", "ShouldTestFile")
            return ShouldTest
            
        except Exception as e:
            LoggingService.LogException("Exception in ShouldTestFile", e, "ShouldQualityTestService", "ShouldTestFile")
            # Default to True on error to ensure quality testing happens
            return True
    
    def ProcessTranscodedFile(self, TranscodeAttemptId: int, OriginalFilePath: str, TranscodedFilePath: str) -> Dict[str, Any]:
        """
        Process a transcoded file - decide if it should be quality tested and add to queue if needed.
        
        Args:
            TranscodeAttemptId: ID of the transcode attempt
            OriginalFilePath: Original file path (remote)
            TranscodedFilePath: Transcoded file path (local)
            
        Returns:
            Dict with Success, Message, and QualityTestJobId if created
        """
        try:
            LoggingService.LogFunctionEntry("ProcessTranscodedFile", "ShouldQualityTestService", 
                                          TranscodeAttemptId, OriginalFilePath, TranscodedFilePath)
            
            # Check if quality test service is paused - if so, skip queue and go straight to replacement
            try:
                service_status = self.DatabaseManager.GetServiceStatus("QualityTestService")
                if service_status and service_status.get('Status') == 'Paused':
                    LoggingService.LogInfo(f"Quality test service is paused for TranscodeAttempt {TranscodeAttemptId}, skipping queue and replacing file immediately", 
                                         "ShouldQualityTestService", "ProcessTranscodedFile")
                    from Services.FileReplacementBusinessService import FileReplacementBusinessService
                    file_replacement_service = FileReplacementBusinessService(self.DatabaseManager)
                    replacement_result = file_replacement_service.ProcessFileReplacement(TranscodeAttemptId, BypassVMAFCheck=True)
                    
                    return {
                        "Success": replacement_result.get("Success", False),
                        "Message": "File replaced automatically because quality testing service is paused",
                        "QualityTestJobId": None
                    }
            except Exception as e:
                LoggingService.LogException("Error checking quality test service status", e, "ShouldQualityTestService", "ProcessTranscodedFile")
            
            # Check if file should be quality tested
            ShouldTest = self.ShouldTestFile(TranscodedFilePath)
            
            if not ShouldTest:
                              # LoggingService.LogInfo(f"File {TranscodedFilePath} should not undergo quality testing", 
                              #                    "ShouldQualityTestService", "ProcessTranscodedFile")
                # Automatically replace the file if quality testing is disabled
                LoggingService.LogInfo(f"Quality testing disabled for TranscodeAttempt {TranscodeAttemptId}, triggering automatic file replacement", 
                                     "ShouldQualityTestService", "ProcessTranscodedFile")
                from Services.FileReplacementBusinessService import FileReplacementBusinessService
                file_replacement_service = FileReplacementBusinessService(self.DatabaseManager)
                replacement_result = file_replacement_service.ProcessFileReplacement(TranscodeAttemptId, BypassVMAFCheck=True)
                
                return {
                    "Success": replacement_result.get("Success", False),
                    "Message": "File replaced automatically because quality testing is disabled",
                    "QualityTestJobId": None
                }
            
            # Use QualityTestQueueService to add to queue (handles all file path resolution)
            QualityTestJobId = self.QualityTestQueue.AddToQualityTestQueue(TranscodeAttemptId)
            
            if QualityTestJobId:
                              # LoggingService.LogInfo(f"Created quality test job {QualityTestJobId} for TranscodeAttempt {TranscodeAttemptId}", 
                              #                    "ShouldQualityTestService", "ProcessTranscodedFile")
                return {
                    "Success": True,
                    "Message": "Quality test job created successfully",
                    "QualityTestJobId": QualityTestJobId
                }
            else:
                LoggingService.LogError(f"Failed to create quality test job for TranscodeAttempt {TranscodeAttemptId}", 
                                      "ShouldQualityTestService", "ProcessTranscodedFile")
                return {
                    "Success": False,
                    "Message": "Failed to create quality test job",
                    "QualityTestJobId": None
                }
                
        except Exception as e:
            LoggingService.LogException("Exception in ProcessTranscodedFile", e, "ShouldQualityTestService", "ProcessTranscodedFile")
            return {
                "Success": False,
                "Message": f"Exception processing transcoded file: {str(e)}",
                "QualityTestJobId": None
            }
    
