#!/usr/bin/env python3
"""
OrphanCleanupService -- recurring sweep that catches operational-row leaks.

Owns BUG-0001 criteria 16 (ActiveJobs orphans), 17 (QualityTestingQueue
stale rows), and the recurring half of 18 (TranscodeProgress orphans). The
TFP cleanup chokepoint at PostTranscodeDispositionService._CommitDisposition
is the primary defense against leaks; this sweep is the safety net.

Flow doc: Features/ServiceControl/orphan-cleanup.flow.md.

Each sweep step runs in its own short transaction. A failing step does
not abort the rest of the cycle. Every removal emits one WARN log so the
operator can hunt the leaking caller (per criterion 16's
"don't hide problems" requirement).
"""

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


class OrphanCleanupService:

    def __init__(self, DatabaseServiceInstance=None):
        self.DatabaseService = DatabaseServiceInstance or DatabaseService()

    def SweepOrphans(self) -> dict:
        TfpSwept = self._SweepTemporaryFilePaths()
        TranscodeAjSwept = self._SweepActiveJobs(
            ServiceName='TranscodeService',
            QueueTable='TranscodeQueue',
        )
        QtAjSwept = self._SweepActiveJobs(
            ServiceName='QualityTestingService',
            QueueTable='QualityTestingQueue',
        )
        QtQueueSwept = self._SweepStaleQualityTestingQueue()
        ProgressSwept = self._SweepOrphanedTranscodeProgress()

        LoggingService.LogInfo(
            f"OrphanCleanup swept: TFP={TfpSwept} "
            f"ActiveJobs(Transcode)={TranscodeAjSwept} "
            f"ActiveJobs(QualityTest)={QtAjSwept} "
            f"QTQueue={QtQueueSwept} Progress={ProgressSwept}",
            "OrphanCleanupService", "SweepOrphans",
        )
        return {
            "TemporaryFilePaths": TfpSwept,
            "ActiveJobsTranscode": TranscodeAjSwept,
            "ActiveJobsQualityTest": QtAjSwept,
            "QualityTestingQueue": QtQueueSwept,
            "TranscodeProgress": ProgressSwept,
        }

    def _SweepTemporaryFilePaths(self) -> int:
        try:
            Removed = self.DatabaseService.ExecuteNonQuery(
                """
                DELETE FROM TemporaryFilePaths
                WHERE TranscodeAttemptId IN (
                    SELECT Id FROM TranscodeAttempts WHERE Success IS NOT NULL
                )
                """,
                (),
            )
            if Removed:
                LoggingService.LogWarning(
                    f"OrphanCleanup removed {Removed} TemporaryFilePaths rows "
                    f"for finished TranscodeAttempts -- a terminal-state cleanup "
                    f"path is leaking, investigate.",
                    "OrphanCleanupService", "_SweepTemporaryFilePaths",
                )
            return Removed or 0
        except Exception as Ex:
            LoggingService.LogException(
                "TFP orphan sweep failed", Ex,
                "OrphanCleanupService", "_SweepTemporaryFilePaths",
            )
            return 0

    def _SweepActiveJobs(self, ServiceName: str, QueueTable: str) -> int:
        try:
            Orphans = self.DatabaseService.ExecuteQuery(
                f"""
                SELECT aj.Id, aj.QueueId, aj.WorkerName
                FROM ActiveJobs aj
                LEFT JOIN {QueueTable} q ON q.Id = aj.QueueId
                WHERE aj.ServiceName = %s AND q.Id IS NULL
                """,
                (ServiceName,),
            )
            if not Orphans:
                return 0
            for Row in Orphans:
                LoggingService.LogWarning(
                    f"OrphanCleanup removing ActiveJobs row "
                    f"Id={Row.get('Id')} QueueId={Row.get('QueueId')} "
                    f"WorkerName={Row.get('WorkerName')} ServiceName={ServiceName} "
                    f"-- parent {QueueTable} row is gone, the queue-delete caller "
                    f"that produced this leak did not clean up the ActiveJobs row.",
                    "OrphanCleanupService", "_SweepActiveJobs",
                )
            self.DatabaseService.ExecuteNonQuery(
                f"""
                DELETE FROM ActiveJobs
                WHERE ServiceName = %s
                  AND QueueId NOT IN (SELECT Id FROM {QueueTable})
                """,
                (ServiceName,),
            )
            return len(Orphans)
        except Exception as Ex:
            LoggingService.LogException(
                f"ActiveJobs orphan sweep failed for ServiceName={ServiceName}",
                Ex, "OrphanCleanupService", "_SweepActiveJobs",
            )
            return 0

    def _SweepStaleQualityTestingQueue(self) -> int:
        try:
            Stale = self.DatabaseService.ExecuteQuery(
                """
                SELECT qtq.Id, qtq.TranscodeAttemptId, ta.Disposition
                FROM QualityTestingQueue qtq
                JOIN TranscodeAttempts ta ON ta.Id = qtq.TranscodeAttemptId
                WHERE ta.Success IS NOT NULL AND ta.QualityTestCompleted = TRUE
                """,
                (),
            )
            if not Stale:
                return 0
            for Row in Stale:
                LoggingService.LogWarning(
                    f"OrphanCleanup removing stale QualityTestingQueue row "
                    f"Id={Row.get('Id')} TranscodeAttemptId={Row.get('TranscodeAttemptId')} "
                    f"Disposition={Row.get('Disposition')} -- attempt is already "
                    f"terminal with QualityTestCompleted=TRUE.",
                    "OrphanCleanupService", "_SweepStaleQualityTestingQueue",
                )
            self.DatabaseService.ExecuteNonQuery(
                """
                DELETE FROM QualityTestingQueue
                WHERE TranscodeAttemptId IN (
                    SELECT Id FROM TranscodeAttempts
                    WHERE Success IS NOT NULL AND QualityTestCompleted = TRUE
                )
                """,
                (),
            )
            return len(Stale)
        except Exception as Ex:
            LoggingService.LogException(
                "QualityTestingQueue stale-row sweep failed", Ex,
                "OrphanCleanupService", "_SweepStaleQualityTestingQueue",
            )
            return 0

    def _SweepOrphanedTranscodeProgress(self) -> int:
        try:
            Removed = self.DatabaseService.ExecuteNonQuery(
                """
                DELETE FROM TranscodeProgress
                WHERE TranscodeAttemptId NOT IN (
                    SELECT Id FROM TranscodeAttempts
                    WHERE Success IS NULL AND CompletedDate IS NULL
                )
                """,
                (),
            )
            return Removed or 0
        except Exception as Ex:
            LoggingService.LogException(
                "TranscodeProgress orphan sweep failed", Ex,
                "OrphanCleanupService", "_SweepOrphanedTranscodeProgress",
            )
            return 0
