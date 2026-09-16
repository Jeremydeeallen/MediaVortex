# directive: bug-0095-failure-classification | # see failure-accounting.C11
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Core.Database.DatabaseService import DatabaseService
from Core.Database.TerminalFailurePredicate import IsMediaFileTerminalBlocked, GetTerminalRemediation


class TestFailureClassTerminal(unittest.TestCase):
    """C11 Verifiable list: (a) classifier populates FailureClass at INSERT via dispatcher; (b) synthetic Terminal-class attempt + auto-requeue refuses insert; (c) AddJobToQueue returns Terminal envelope; (d) Reset clears via LastFailureResetAt bump + writes PriorFailureClass audit; (e) operator flip of FailureClasses.Terminal observed by next claim (no restart)."""

    @classmethod
    def setUpClass(cls):
        cls.Db = DatabaseService()
        cls.TestMediaFileId = cls._PickTestMediaFileId(cls.Db)

    @staticmethod
    def _PickTestMediaFileId(Db):
        """Pick a MediaFile that has at least one Success=FALSE TranscodeAttempts row and isn't currently in a live queue. Reversible by cleanup."""
        Rows = Db.ExecuteQuery(
            "SELECT mf.Id FROM MediaFiles mf "
            "JOIN TranscodeAttempts ta ON ta.MediaFileId = mf.Id "
            "LEFT JOIN TranscodeQueue tq ON tq.MediaFileId = mf.Id AND tq.Status IN ('Pending','Running') "
            "WHERE ta.Success = FALSE AND tq.Id IS NULL "
            "GROUP BY mf.Id ORDER BY mf.Id LIMIT 1"
        )
        if not Rows:
            raise unittest.SkipTest("no suitable test MediaFile with failing attempt available")
        return int(Rows[0]['Id'])

    def setUp(self):
        self._LatestAttemptRow = self.Db.ExecuteQuery(
            "SELECT Id, FailureClass FROM TranscodeAttempts WHERE MediaFileId = %s AND Success = FALSE ORDER BY AttemptDate DESC LIMIT 1",
            (self.TestMediaFileId,),
        )
        self._OriginalFailureClass = None
        if self._LatestAttemptRow:
            self._LatestAttemptId = int(self._LatestAttemptRow[0]['Id'])
            self._OriginalFailureClass = self._LatestAttemptRow[0].get('FailureClass')

    def tearDown(self):
        if hasattr(self, '_LatestAttemptId'):
            self.Db.ExecuteNonQuery(
                "UPDATE TranscodeAttempts SET FailureClass = %s WHERE Id = %s",
                (self._OriginalFailureClass, self._LatestAttemptId),
            )
        self.Db.ExecuteNonQuery(
            "UPDATE MediaFiles SET LastFailureResetAt = NULL WHERE Id = %s AND LastFailureResetAt > NOW() - INTERVAL '5 minutes'",
            (self.TestMediaFileId,),
        )
        self.Db.ExecuteNonQuery(
            "DELETE FROM FailureBudgetResets WHERE OperatorName = 'contract-test-2026-09-16'"
        )

    def test_a_classifier_populates_failureclass_at_update(self):
        """Auto-classify at UpdateTranscodeAttempt dispatcher writes FailureClass column."""
        from Features.TranscodeJob.TranscodeJobRepository import TranscodeJobRepository
        Repo = TranscodeJobRepository()
        self.Db.ExecuteNonQuery(
            "UPDATE TranscodeAttempts SET FailureClass = NULL WHERE Id = %s",
            (self._LatestAttemptId,),
        )
        Ok = Repo.UpdateTranscodeAttempt(self._LatestAttemptId, {
            'Success': False,
            'ErrorMessage': 'moov atom not found; test dispatcher auto-classify',
        })
        Rows = self.Db.ExecuteQuery(
            "SELECT FailureClass FROM TranscodeAttempts WHERE Id = %s",
            (self._LatestAttemptId,),
        )
        self.assertEqual(Rows[0].get('FailureClass'), 'source_unreadable')

    def test_b_terminal_class_blocks_predicate(self):
        """Point-query recognizes Terminal-classified attempt as blocked."""
        self.Db.ExecuteNonQuery(
            "UPDATE TranscodeAttempts SET FailureClass = 'source_unreadable' WHERE Id = %s",
            (self._LatestAttemptId,),
        )
        self.assertTrue(IsMediaFileTerminalBlocked(self.TestMediaFileId))
        Rem = GetTerminalRemediation(self.TestMediaFileId)
        self.assertIsNotNone(Rem)
        self.assertEqual(Rem[0], 'source_unreadable')
        self.assertIn('Regrab', Rem[1])

    def test_c_addjobtoqueue_returns_terminal_envelope(self):
        """AddJobToQueue returns Terminal envelope with CanOverride=False."""
        self.Db.ExecuteNonQuery(
            "UPDATE TranscodeAttempts SET FailureClass = 'source_unreadable' WHERE Id = %s",
            (self._LatestAttemptId,),
        )
        from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
        from Repositories.DatabaseManager import DatabaseManager
        DbMgr = DatabaseManager()
        Svc = QueueManagementBusinessService(DbMgr)
        Result = Svc.AddJobToQueue(self.TestMediaFileId, ForceAdd=True)
        self.assertFalse(Result.get('Success'))
        self.assertTrue(Result.get('FailureClassTerminal'))
        self.assertFalse(Result.get('CanOverride'))
        self.assertEqual(Result.get('FailureClass'), 'source_unreadable')
        self.assertIn('Regrab', str(Result.get('Remediation') or ''))

    def test_d_reset_clears_block_and_writes_audit(self):
        """Reset via ResetFailureBudget bumps LastFailureResetAt (clears predicate) + writes PriorFailureClass to audit."""
        from Features.FailureAccounting.Repositories.FailedJobsRepository import FailedJobsRepository
        self.Db.ExecuteNonQuery(
            "UPDATE TranscodeAttempts SET FailureClass = 'source_unreadable' WHERE Id = %s",
            (self._LatestAttemptId,),
        )
        self.assertTrue(IsMediaFileTerminalBlocked(self.TestMediaFileId))
        FailedJobsRepository().ResetFailureBudget(self.TestMediaFileId, 'contract-test-2026-09-16')
        self.assertFalse(IsMediaFileTerminalBlocked(self.TestMediaFileId))
        AuditRows = self.Db.ExecuteQuery(
            "SELECT PriorFailureClass FROM FailureBudgetResets WHERE MediaFileId = %s AND OperatorName = 'contract-test-2026-09-16'",
            (self.TestMediaFileId,),
        )
        self.assertTrue(AuditRows)
        self.assertEqual(AuditRows[0].get('PriorFailureClass'), 'source_unreadable')

    def test_e_operator_flip_observed_by_next_predicate_call(self):
        """Toggling FailureClasses.Terminal for a class flips the point-query result WITHOUT any restart / cache clear."""
        self.Db.ExecuteNonQuery(
            "UPDATE TranscodeAttempts SET FailureClass = 'source_unreadable' WHERE Id = %s",
            (self._LatestAttemptId,),
        )
        self.assertTrue(IsMediaFileTerminalBlocked(self.TestMediaFileId))
        try:
            self.Db.ExecuteNonQuery("UPDATE FailureClasses SET Terminal = FALSE WHERE ClassName = 'source_unreadable'")
            self.assertFalse(
                IsMediaFileTerminalBlocked(self.TestMediaFileId),
                "operator flip of FailureClasses.Terminal=FALSE must be observed by next predicate call without restart",
            )
        finally:
            self.Db.ExecuteNonQuery("UPDATE FailureClasses SET Terminal = TRUE WHERE ClassName = 'source_unreadable'")


if __name__ == '__main__':
    unittest.main()
