#!/usr/bin/env python3
"""
Should Quality Test Service
Simple service to determine if a transcoded file should undergo quality testing
"""

from typing import Optional, Dict, Any
from Core.Logging.LoggingService import LoggingService
from Repositories.DatabaseManager import DatabaseManager
from Services.QualityTestQueueService import QualityTestQueueService


class ShouldQualityTestService:
    """Simple service to determine if a file should undergo quality testing."""

    def __init__(self, PathTranslation=None):
        """Initialize the service."""
        self.DatabaseManager = DatabaseManager()
        self.QualityTestQueue = QualityTestQueueService(self.DatabaseManager)
        self.PathTranslation = PathTranslation

    def _ReplaceFileDirectly(self, TranscodeAttemptId: int, Reason: str) -> Dict[str, Any]:
        """Skip quality testing and go straight to file replacement."""
        from Features.FileReplacement.FileReplacementBusinessService import FileReplacementBusinessService
        ReplacementService = FileReplacementBusinessService(self.DatabaseManager, PathTranslation=self.PathTranslation)
        ReplacementResult = ReplacementService.ProcessFileReplacement(TranscodeAttemptId, BypassVMAFCheck=True)
        return {
            "Success": ReplacementResult.get("Success", False),
            "Message": f"File replaced automatically because {Reason}",
            "QualityTestJobId": None
        }

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

            # Check QualityTestRequired on the TranscodeAttempt (set upstream by IsQualityTestEnabled)
            TranscodeAttempt = self.DatabaseManager.GetTranscodeAttemptById(TranscodeAttemptId)
            QualityTestRequired = bool(TranscodeAttempt and getattr(TranscodeAttempt, 'QualityTestRequired', False))

            if not QualityTestRequired:
                LoggingService.LogInfo(f"Quality testing not required for TranscodeAttempt {TranscodeAttemptId}, proceeding directly to file replacement",
                                     "ShouldQualityTestService", "ProcessTranscodedFile")
                return self._ReplaceFileDirectly(TranscodeAttemptId, "Quality testing is disabled for this worker/globally")

            # Quality testing is required -- check if the service is paused
            try:
                ServiceStatus = self.DatabaseManager.GetServiceStatus("QualityTestService")
                if ServiceStatus and ServiceStatus.get('Status') == 'Paused':
                    LoggingService.LogInfo(f"Quality test service is paused for TranscodeAttempt {TranscodeAttemptId}, skipping queue and replacing file immediately",
                                         "ShouldQualityTestService", "ProcessTranscodedFile")
                    return self._ReplaceFileDirectly(TranscodeAttemptId, "Quality testing service is paused")
            except Exception as e:
                LoggingService.LogException("Error checking quality test service status", e, "ShouldQualityTestService", "ProcessTranscodedFile")

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
