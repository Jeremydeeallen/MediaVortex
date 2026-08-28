import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService
from Features.FailureAccounting.Repositories.FailureBudgetConfigRepository import FailureBudgetConfigRepository
from Features.FailureAccounting.Services.FailureBudgetService import FailureBudgetService
from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService


# directive: bug-0061-forceadd-autoreset-test
class TestAddJobToQueueForceAddAutoReset(unittest.TestCase):
    """G3: AddJobToQueue(ForceAdd=True) on cap-hit MediaFile auto-writes FailureBudgetResets + bumps LastFailureResetAt."""

    def setUp(self):
        self.Db = DatabaseService()
        self.Service = FailureBudgetService(Db=self.Db)
        self.Cfg = FailureBudgetConfigRepository().Get()
        self.Qmbs = QueueManagementBusinessService()
        self.Marker = "__test_forceadd_autoreset__/" + str(id(self)) + ".mkv"
        self.Db.ExecuteNonQuery(
            "INSERT INTO MediaFiles (StorageRootId, RelativePath, FileName, SizeMB, AssignedProfile, HasExplicitEnglishAudio) "
            "VALUES (1, %s, %s, 100.0, 'AV1 Tier 1 Efficient', TRUE)",
            (self.Marker, "test_forceadd.mkv"),
        )
        Row = self.Db.ExecuteQuery("SELECT Id FROM MediaFiles WHERE RelativePath = %s", (self.Marker,))
        self.MediaFileId = int(Row[0]['Id'])

    def tearDown(self):
        self.Db.ExecuteNonQuery("DELETE FROM TranscodeQueue WHERE MediaFileId = %s", (self.MediaFileId,))
        self.Db.ExecuteNonQuery("DELETE FROM TranscodeAttempts WHERE MediaFileId = %s", (self.MediaFileId,))
        self.Db.ExecuteNonQuery("DELETE FROM FailureBudgetResets WHERE MediaFileId = %s", (self.MediaFileId,))
        self.Db.ExecuteNonQuery("DELETE FROM MediaFiles WHERE Id = %s", (self.MediaFileId,))

    def _InsertFailure(self):
        self.Db.ExecuteNonQuery(
            "INSERT INTO TranscodeAttempts (MediaFileId, AttemptDate, Success, ProfileName, ErrorMessage) "
            "VALUES (%s, NOW(), FALSE, 'TestProfile', 'synthetic')",
            (self.MediaFileId,),
        )

    def test_forceadd_on_cap_hit_writes_audit_and_bumps_lastreset(self):
        for _ in range(self.Cfg.MaxEncodeFailures):
            self._InsertFailure()
        self.assertFalse(self.Service.HasBudgetRemaining(self.MediaFileId), "precondition: cap hit")

        Result = self.Qmbs.AddJobToQueue(self.MediaFileId, ForceAdd=True)

        self.assertTrue(Result.get('Success'), "expected admission success, got: " + repr(Result))

        Audit = self.Db.ExecuteQuery(
            "SELECT COUNT(*) AS n FROM FailureBudgetResets WHERE MediaFileId = %s AND OperatorName = %s",
            (self.MediaFileId, 'ForceAdd'),
        )
        self.assertEqual(int(Audit[0]['n']), 1, "expected exactly one 'ForceAdd' audit row")

        Reset = self.Db.ExecuteQuery(
            "SELECT LastFailureResetAt FROM MediaFiles WHERE Id = %s",
            (self.MediaFileId,),
        )
        self.assertIsNotNone(Reset[0]['LastFailureResetAt'], "LastFailureResetAt should be set")

        self.assertTrue(self.Service.HasBudgetRemaining(self.MediaFileId), "budget should be reset")

    def test_forceadd_when_budget_available_does_not_write_audit(self):
        self.assertTrue(self.Service.HasBudgetRemaining(self.MediaFileId), "precondition: budget available")

        self.Qmbs.AddJobToQueue(self.MediaFileId, ForceAdd=True)

        Audit = self.Db.ExecuteQuery(
            "SELECT COUNT(*) AS n FROM FailureBudgetResets WHERE MediaFileId = %s",
            (self.MediaFileId,),
        )
        self.assertEqual(int(Audit[0]['n']), 0, "no audit row expected when budget was available")

    def test_no_forceadd_on_cap_hit_writes_no_audit(self):
        for _ in range(self.Cfg.MaxEncodeFailures):
            self._InsertFailure()
        self.assertFalse(self.Service.HasBudgetRemaining(self.MediaFileId), "precondition: cap hit")

        Result = self.Qmbs.AddJobToQueue(self.MediaFileId, ForceAdd=False)

        self.assertFalse(Result.get('Success'), "expected refusal without ForceAdd")

        Audit = self.Db.ExecuteQuery(
            "SELECT COUNT(*) AS n FROM FailureBudgetResets WHERE MediaFileId = %s",
            (self.MediaFileId,),
        )
        self.assertEqual(int(Audit[0]['n']), 0, "no auto-reset expected without ForceAdd")


if __name__ == "__main__":
    unittest.main()
