#!/usr/bin/env python3
"""Quality test queue service -- business logic for QualityTestingQueue inserts."""

from typing import Optional, List
from Services.LoggingService import LoggingService
from Repositories.DatabaseManager import DatabaseManager
from Core.Path import Path, Worker, PathError


# directive: path-schema-migration | # see path.S1
class QualityTestQueueService:
    """Business service for quality testing queue operations."""

    # directive: path-schema-migration | # see path.S1
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None):
        """Initialize the service with dependencies."""
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self._Worker: Optional[Worker] = None
        self._StorageRoots: Optional[List[dict]] = None
        self._PrefixMap: Optional[dict] = None

    # directive: path-schema-migration | # see path.S3
    def _GetWorker(self) -> Worker:
        if self._Worker is None:
            self._Worker = Worker.FromWorkerContext()
        return self._Worker

    # directive: path-schema-migration | # see path.S8
    def _GetPrefixMap(self) -> dict:
        if self._PrefixMap is None:
            from Core.Database.DatabaseService import DatabaseService
            Rows = DatabaseService().ExecuteQuery(
                "SELECT Id, CanonicalPrefix FROM StorageRoots ORDER BY length(CanonicalPrefix) DESC"
            )
            self._StorageRoots = [
                {"Id": R.get("id", R.get("Id")),
                 "CanonicalPrefix": R.get("canonicalprefix", R.get("CanonicalPrefix"))}
                for R in Rows
            ]
            self._PrefixMap = {Sr["Id"]: Sr["CanonicalPrefix"] for Sr in self._StorageRoots}
        return self._PrefixMap
    
    # directive: path-schema-migration | # see path.S1
    def AddToQualityTestQueue(self, TranscodeAttemptId: int) -> Optional[int]:
        """Add a transcode attempt to the quality testing queue. Returns JobId or None."""
        try:
            LoggingService.LogFunctionEntry("AddToQualityTestQueue", "QualityTestQueueService", TranscodeAttemptId)

            Attempt = self.DatabaseManager.GetTranscodeAttemptById(TranscodeAttemptId)
            if not Attempt:
                LoggingService.LogError(f"TranscodeAttempt {TranscodeAttemptId} not found", "QualityTestQueueService", "AddToQualityTestQueue")
                return None

            if not Attempt.Success:
                LoggingService.LogError(f"TranscodeAttempt {TranscodeAttemptId} was not successful", "QualityTestQueueService", "AddToQualityTestQueue")
                return None

            # Duplicate-check via repository helper; in-memory filter avoids inline SQL
            ExistingQueue = self.DatabaseManager.GetQualityTestQueue() or []
            for Existing in ExistingQueue:
                if Existing.get('TranscodeAttemptId') == TranscodeAttemptId:
                    ExistingId = Existing.get('Id')
                    LoggingService.LogWarning(f"Quality test queue entry already exists for TranscodeAttempt {TranscodeAttemptId} (ID: {ExistingId})",
                                            "QualityTestQueueService", "AddToQualityTestQueue")
                    return ExistingId

            # Read TemporaryFilePaths via the repository helper (typed-pair columns post-Phase 8)
            TempPaths = self.DatabaseManager.GetTemporaryFilePath(TranscodeAttemptId)
            if not TempPaths:
                LoggingService.LogError(f"No TemporaryFilePaths record found for TranscodeAttempt {TranscodeAttemptId}",
                                      "QualityTestQueueService", "AddToQualityTestQueue")
                return None

            SourcePath = Path.FromRow(TempPaths, Prefix="Source")
            OutputPath = Path.FromRow(TempPaths, Prefix="Output")

            if SourcePath is None or OutputPath is None:
                LoggingService.LogError(
                    f"Missing typed-pair columns in TemporaryFilePaths for TranscodeAttempt {TranscodeAttemptId}",
                    "QualityTestQueueService", "AddToQualityTestQueue")
                return None

            try:
                PrefixMap = self._GetPrefixMap()
                OriginalFilePath = SourcePath.CanonicalDisplay(PrefixMap)
                LocalSourcePath = SourcePath.Resolve(self._GetWorker())
                TranscodedFilePath = OutputPath.Resolve(self._GetWorker())
            except PathError as PathErr:
                LoggingService.LogError(
                    f"Failed to resolve typed-pair paths for TranscodeAttempt {TranscodeAttemptId}: {PathErr}",
                    "QualityTestQueueService", "AddToQualityTestQueue")
                return None

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
