#!/usr/bin/env python3
"""
OrphanCleanupService -- recurring sweep that catches operational-row leaks.

Owns the ActiveJobs / QualityTestingQueue / TemporaryFilePaths orphan sweeps (see KNOWN-ISSUES.md for the legacy stuck-item context)
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


# directive: bug-0020-worker-ownership
class OrphanCleanupService:

    # directive: bug-0020-worker-ownership
    def __init__(self, DatabaseServiceInstance=None):
        self.DatabaseService = DatabaseServiceInstance or DatabaseService()

    # directive: bug-0020-worker-ownership
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
        QtProgressSwept = self._SweepOrphanedQualityTestProgress()

        LoggingService.LogInfo(
            f"OrphanCleanup swept: TFP={TfpSwept} "
            f"ActiveJobs(Transcode)={TranscodeAjSwept} "
            f"ActiveJobs(QualityTest)={QtAjSwept} "
            f"QTQueue={QtQueueSwept} Progress={ProgressSwept} "
            f"QtProgress={QtProgressSwept}",
            "OrphanCleanupService", "SweepOrphans",
        )
        return {
            "TemporaryFilePaths": TfpSwept,
            "ActiveJobsTranscode": TranscodeAjSwept,
            "ActiveJobsQualityTest": QtAjSwept,
            "QualityTestingQueue": QtQueueSwept,
            "TranscodeProgress": ProgressSwept,
            "QualityTestProgress": QtProgressSwept,
        }

    # directive: bug-0020-worker-ownership
    def _SweepTemporaryFilePaths(self) -> int:
        # 2026-05-25: TFP sweep disabled pending redesign of the liveness-based predicate. Legacy
        # `Success IS NOT NULL` predicate and the first-attempt tighter predicate
        # (Success=FALSE / FileReplaced=TRUE / Disposition IN terminal-no-replace)
        # both raced FileReplacement during the VMAF window and silently deleted
        # in-flight TFP rows -- Doctor Who S06E04 canary v2 + v3 lost their TFP
        # mid-VMAF and ended with `.inprogress` files stranded on disk. Correct
        # design uses liveness signals (QualityTestingQueue + ActiveJobs rows for
        # the parent TranscodeAttemptId) instead of column inference. Until that
        # ships, no sweep -- real TFP cleanup is owned by FileReplacement on
        # Replace/BypassReplace and by _CommitDisposition on terminal-no-replace.
        # Small operator-cleanable accumulation is the accepted trade for not
        # racing the live pipeline.
        LoggingService.LogInfo(
            "TFP sweep disabled pending redesign (liveness-based predicate).",
            "OrphanCleanupService", "_SweepTemporaryFilePaths",
        )
        return 0

    # directive: bug-0020-worker-ownership
    def _SweepActiveJobs(self, ServiceName: str, QueueTable: str) -> int:
        SelectSql = (  # allow: R12 -- preexisting placement; format normalized
            "SELECT aj.Id, aj.QueueId, aj.WorkerName "
            "FROM ActiveJobs aj "
            f"LEFT JOIN {QueueTable} q ON q.Id = aj.QueueId "
            "WHERE aj.ServiceName = %s AND q.Id IS NULL "
            "  AND aj.WorkerName NOT IN ("
            "    SELECT WorkerName FROM Workers "
            "    WHERE LastHeartbeat > NOW() - INTERVAL '5 minutes'"
            "  )"
        )
        DeleteSql = (  # allow: R12 -- preexisting placement; format normalized
            "DELETE FROM ActiveJobs "
            "WHERE ServiceName = %s "
            f"  AND QueueId NOT IN (SELECT Id FROM {QueueTable}) "
            "  AND WorkerName NOT IN ("
            "    SELECT WorkerName FROM Workers "
            "    WHERE LastHeartbeat > NOW() - INTERVAL '5 minutes'"
            "  )"
        )
        try:
            Orphans = self.DatabaseService.ExecuteQuery(SelectSql, (ServiceName,))
            if not Orphans:
                return 0
            for Row in Orphans:
                LoggingService.LogWarning(
                    f"OrphanCleanup removing ActiveJobs row "
                    f"Id={Row.get('Id')} QueueId={Row.get('QueueId')} "
                    f"WorkerName={Row.get('WorkerName')} ServiceName={ServiceName} "
                    f"-- parent {QueueTable} row is gone AND owning worker is offline.",
                    "OrphanCleanupService", "_SweepActiveJobs",
                )
            self.DatabaseService.ExecuteNonQuery(DeleteSql, (ServiceName,))
            return len(Orphans)
        except Exception as Ex:
            LoggingService.LogException(
                f"ActiveJobs orphan sweep failed for ServiceName={ServiceName}",
                Ex, "OrphanCleanupService", "_SweepActiveJobs",
            )
            return 0

    # directive: bug-0020-worker-ownership
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

    # directive: bug-0020-worker-ownership
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

    # directive: bug-0020-worker-ownership
    def _SweepOrphanedQualityTestProgress(self) -> int:
        try:
            Removed = self.DatabaseService.ExecuteNonQuery(
                """
                DELETE FROM QualityTestProgress
                WHERE TranscodeAttemptId NOT IN (
                    SELECT TranscodeAttemptId FROM QualityTestingQueue
                    WHERE Status IN ('Pending','Running')
                )
                OR (Status = 'Processing' AND UpdatedAt < NOW() - INTERVAL '30 minutes')
                """,
                (),
            )
            return Removed or 0
        except Exception as Ex:
            LoggingService.LogException(
                "QualityTestProgress orphan sweep failed", Ex,
                "OrphanCleanupService", "_SweepOrphanedQualityTestProgress",
            )
            return 0