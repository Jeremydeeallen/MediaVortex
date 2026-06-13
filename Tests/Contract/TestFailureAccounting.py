import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Core.Database.DatabaseService import DatabaseService
from Features.FailureAccounting.Services.FailureBudgetService import FailureBudgetService
from Features.FailureAccounting.Repositories.FailureBudgetConfigRepository import FailureBudgetConfigRepository
from Features.FailureAccounting.Repositories.FailedJobsRepository import FailedJobsRepository
from Core.Database.FailureBudgetPredicate import BuildCapPredicate


# directive: failure-accounting | # see failure-accounting.C3
class TestTranscodeAttemptsMediaFileIdNotNull(unittest.TestCase):
    """AC3: MediaFileId is NOT NULL post-migration; CleanupOrphanFailedAttempts archived the historical orphans."""

    # directive: failure-accounting | # see failure-accounting.C3
    def test_no_null_mediafileid_rows(self):
        n = int(DatabaseService().ExecuteQuery("SELECT COUNT(*) AS n FROM TranscodeAttempts WHERE MediaFileId IS NULL")[0]['n'])
        self.assertEqual(n, 0)

    # directive: failure-accounting | # see failure-accounting.C3
    def test_column_is_not_null_constraint(self):
        Rows = DatabaseService().ExecuteQuery(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'transcodeattempts' AND column_name = 'mediafileid'"
        )
        self.assertEqual(str(Rows[0]['is_nullable']).upper(), 'NO')


# directive: failure-accounting | # see failure-accounting.C5
class TestProfileNameOnFailureRows(unittest.TestCase):
    """AC5: failure rows written from this commit forward carry a non-null ProfileName."""

    # directive: failure-accounting | # see failure-accounting.C5
    def test_no_null_profilename_on_recent_failures(self):
        n = int(DatabaseService().ExecuteQuery(
            "SELECT COUNT(*) AS n FROM TranscodeAttempts "
            "WHERE Success = FALSE AND ProfileName IS NULL "
            "AND AttemptDate > NOW() - INTERVAL '24 hours'"
        )[0]['n'])
        self.assertEqual(n, 0)


# directive: failure-accounting | # see failure-accounting.C1
class TestFailureBudgetService(unittest.TestCase):
    """AC1: HasBudgetRemaining counts consecutive failures since last Success=TRUE OR LastFailureResetAt."""

    # directive: failure-accounting | # see failure-accounting.C1
    def setUp(self):
        self.Db = DatabaseService()
        self.Service = FailureBudgetService(Db=self.Db)
        self.Cfg = FailureBudgetConfigRepository().Get()
        self.Marker = "__test_failure_accounting__/" + str(id(self)) + ".mkv"
        self.Db.ExecuteNonQuery(
            "INSERT INTO MediaFiles (StorageRootId, RelativePath, FileName, SizeMB) "
            "VALUES (NULL, %s, %s, 1.0)",
            (self.Marker, "test.mkv")
        )
        Row = self.Db.ExecuteQuery("SELECT Id FROM MediaFiles WHERE RelativePath = %s", (self.Marker,))
        self.MediaFileId = int(Row[0]['Id'])

    # directive: failure-accounting | # see failure-accounting.C1
    def tearDown(self):
        self.Db.ExecuteNonQuery("DELETE FROM TranscodeAttempts WHERE MediaFileId = %s", (self.MediaFileId,))
        self.Db.ExecuteNonQuery("DELETE FROM FailureBudgetResets WHERE MediaFileId = %s", (self.MediaFileId,))
        self.Db.ExecuteNonQuery("DELETE FROM MediaFiles WHERE Id = %s", (self.MediaFileId,))

    # directive: failure-accounting | # see failure-accounting.C1
    def _InsertFailure(self):
        self.Db.ExecuteNonQuery(
            "INSERT INTO TranscodeAttempts (MediaFileId, AttemptDate, Success, ProfileName, ErrorMessage) "
            "VALUES (%s, NOW(), FALSE, 'TestProfile', 'synthetic')",
            (self.MediaFileId,)
        )

    # directive: failure-accounting | # see failure-accounting.C1
    def _InsertSuccess(self):
        self.Db.ExecuteNonQuery(
            "INSERT INTO TranscodeAttempts (MediaFileId, AttemptDate, Success, ProfileName) "
            "VALUES (%s, NOW(), TRUE, 'TestProfile')",
            (self.MediaFileId,)
        )

    # directive: failure-accounting | # see failure-accounting.C1
    def test_has_budget_when_zero_failures(self):
        self.assertTrue(self.Service.HasBudgetRemaining(self.MediaFileId))
        self.assertEqual(self.Service.CountConsecutiveFailures(self.MediaFileId), 0)

    # directive: failure-accounting | # see failure-accounting.C1
    def test_caps_at_max(self):
        for _ in range(self.Cfg.MaxEncodeFailures):
            self._InsertFailure()
        self.assertFalse(self.Service.HasBudgetRemaining(self.MediaFileId))

    # directive: failure-accounting | # see failure-accounting.C1
    def test_success_resets_counter(self):
        for _ in range(self.Cfg.MaxEncodeFailures):
            self._InsertFailure()
        self._InsertSuccess()
        self.assertEqual(self.Service.CountConsecutiveFailures(self.MediaFileId), 0)
        self.assertTrue(self.Service.HasBudgetRemaining(self.MediaFileId))


# directive: failure-accounting | # see failure-accounting.C7
class TestFailedJobsRepository(unittest.TestCase):
    """AC7: GetCappedJobs returns over-cap rows; ResetFailureBudget writes audit + bumps LastFailureResetAt."""

    # directive: failure-accounting | # see failure-accounting.C7
    def setUp(self):
        self.Db = DatabaseService()
        self.Repo = FailedJobsRepository()
        self.Cfg = FailureBudgetConfigRepository().Get()
        self.Marker = "__test_failedjobs__/" + str(id(self)) + ".mkv"
        self.Db.ExecuteNonQuery(
            "INSERT INTO MediaFiles (StorageRootId, RelativePath, FileName, SizeMB) "
            "VALUES (NULL, %s, %s, 1.0)",
            (self.Marker, "test_failedjobs.mkv")
        )
        Row = self.Db.ExecuteQuery("SELECT Id FROM MediaFiles WHERE RelativePath = %s", (self.Marker,))
        self.MediaFileId = int(Row[0]['Id'])
        for _ in range(self.Cfg.MaxEncodeFailures):
            self.Db.ExecuteNonQuery(
                "INSERT INTO TranscodeAttempts (MediaFileId, AttemptDate, Success, ProfileName, ErrorMessage, WorkerName) "
                "VALUES (%s, NOW(), FALSE, 'TestProfile', 'synthetic', 'TestWorker')",
                (self.MediaFileId,)
            )

    # directive: failure-accounting | # see failure-accounting.C7
    def tearDown(self):
        self.Db.ExecuteNonQuery("DELETE FROM TranscodeAttempts WHERE MediaFileId = %s", (self.MediaFileId,))
        self.Db.ExecuteNonQuery("DELETE FROM FailureBudgetResets WHERE MediaFileId = %s", (self.MediaFileId,))
        self.Db.ExecuteNonQuery("DELETE FROM MediaFiles WHERE Id = %s", (self.MediaFileId,))

    # directive: failure-accounting | # see failure-accounting.C7
    def test_capped_row_surfaces_in_get_capped(self):
        Rows = self.Repo.GetCappedJobs(Limit=500)
        Ids = [R.MediaFileId for R in Rows]
        self.assertIn(self.MediaFileId, Ids)

    # directive: failure-accounting | # see failure-accounting.C7
    def test_reset_writes_audit_and_bumps_lastreset(self):
        self.Repo.ResetFailureBudget(self.MediaFileId, "ci-test")
        Audit = self.Db.ExecuteQuery(
            "SELECT COUNT(*) AS n FROM FailureBudgetResets WHERE MediaFileId = %s AND OperatorName = %s",
            (self.MediaFileId, "ci-test")
        )
        self.assertEqual(int(Audit[0]['n']), 1)
        Bumped = self.Db.ExecuteQuery(
            "SELECT LastFailureResetAt FROM MediaFiles WHERE Id = %s",
            (self.MediaFileId,)
        )
        self.assertIsNotNone(Bumped[0]['LastFailureResetAt'])
        Rows = self.Repo.GetCappedJobs(Limit=500)
        Ids = [R.MediaFileId for R in Rows]
        self.assertNotIn(self.MediaFileId, Ids)


# directive: failure-accounting | # see failure-accounting.C6
class TestPendingQueueRespectsCap(unittest.TestCase):
    """AC6: every TranscodeQueue.Pending row has FailureBudgetService.HasBudgetRemaining = True."""

    # directive: failure-accounting | # see failure-accounting.C6
    def test_no_pending_row_exceeds_cap(self):
        Db = DatabaseService()
        Service = FailureBudgetService(Db=Db)
        Pending = Db.ExecuteQuery(
            "SELECT MediaFileId FROM TranscodeQueue WHERE Status = 'Pending' AND MediaFileId IS NOT NULL"
        )
        OverCap = []
        for R in Pending:
            Mfid = int(R['MediaFileId'])
            if not Service.HasBudgetRemaining(Mfid):
                OverCap.append(Mfid)
        self.assertEqual(OverCap, [])


# directive: failure-accounting | # see failure-accounting.C6
class TestBuildCapPredicate(unittest.TestCase):
    """AC6 helper: BuildCapPredicate emits a SQL fragment + empty params."""

    # directive: failure-accounting | # see failure-accounting.C6
    def test_fragment_shape(self):
        Frag, Params = BuildCapPredicate("mf.Id")
        self.assertIn("FailureBudgetConfig", Frag)
        self.assertIn("mf.Id", Frag)
        self.assertEqual(Params, ())


if __name__ == '__main__':
    unittest.main()
