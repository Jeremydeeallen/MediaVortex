# see .claude/rules/db-is-authority.md -- conformance tests for capability-gated claim queries

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Core.Database.DatabaseService import DatabaseService, EscapeLikePattern
from Core.Database.WorkerCapabilityPredicate import BuildClaimPredicate, _ALLOWED_CAPABILITIES
from Repositories.DatabaseManager import DatabaseManager


SENTINEL_WORKER = "_test-claim-authority-worker"
SENTINEL_STORAGE_ROOT_ID = 1


# Helper smoke (the foundation everything else depends on)

class TestWorkerCapabilityPredicate(unittest.TestCase):
    def test_emits_workers_exists_clause(self):
        Frag, Params = BuildClaimPredicate("w1", "QualityTestEnabled")
        self.assertIn("EXISTS", Frag)
        self.assertIn("FROM Workers", Frag)
        self.assertIn("w.QualityTestEnabled = TRUE", Frag)
        self.assertIn("w.Status = 'Online'", Frag)
        self.assertEqual(Params, ("w1",))

    def test_rejects_unknown_capability(self):
        with self.assertRaises(ValueError):
            BuildClaimPredicate("w1", "TotallyMadeUp")

    def test_whitelist_lists_the_known_capabilities(self):
        for Cap in ("TranscodeEnabled", "QualityTestEnabled", "RemuxEnabled", "ScanEnabled"):
            self.assertIn(Cap, _ALLOWED_CAPABILITIES)


# Quality testing claim authority

class TestQualityTestClaimAuthority(unittest.TestCase):
    """ClaimQualityTestJob must honor Workers.Status + Workers.QualityTestEnabled."""

    @classmethod
    def setUpClass(cls):
        cls.Db = DatabaseService()
        cls.Dm = DatabaseManager()
        # Sentinel worker -- isolated from production rows.
        cls.Db.ExecuteNonQuery("DELETE FROM Workers WHERE WorkerName = %s", (SENTINEL_WORKER,))
        cls.Db.ExecuteNonQuery(
            "INSERT INTO Workers (WorkerName, Platform, Status, "
            "TranscodeEnabled, QualityTestEnabled, RemuxEnabled, ScanEnabled, "
            "Enabled, LastHeartbeat) "
            "VALUES (%s, 'linux', 'Online', TRUE, TRUE, TRUE, TRUE, TRUE, NOW())",
            (SENTINEL_WORKER,),
        )

    @classmethod
    def tearDownClass(cls):
        cls.Db.ExecuteNonQuery("DELETE FROM Workers WHERE WorkerName = %s", (SENTINEL_WORKER,))

    def setUp(self):
        # Reset sentinel to the "claimable" baseline before every test.
        self.Db.ExecuteNonQuery(
            "UPDATE Workers SET Status='Online', QualityTestEnabled=TRUE, LastHeartbeat=NOW() WHERE WorkerName=%s",
            (SENTINEL_WORKER,),
        )
        # Wipe any stale sentinel rows from a prior failed run.
        self.Db.ExecuteNonQuery(
            "DELETE FROM QualityTestingQueue WHERE LocalSourcePath = %s", ("_test-local",),
        )
        # sentinel queue row: TranscodeAttemptId NULL (gate-independent); ExecuteNonQuery auto-commits
        self.Db.ExecuteNonQuery(
            "INSERT INTO QualityTestingQueue "
            "(TranscodeAttemptId, OriginalFilePath, TranscodedFilePath, LocalSourcePath, Status, DateAdded) "
            "VALUES (NULL, '_test-source', '_test-transcoded', '_test-local', 'Pending', NOW())",
        )
        Rows = self.Db.ExecuteQuery(
            "SELECT Id FROM QualityTestingQueue WHERE LocalSourcePath = %s",
            ("_test-local",),
        )
        self.QueueId = Rows[0]["Id"]

    def tearDown(self):
        self.Db.ExecuteNonQuery("DELETE FROM QualityTestingQueue WHERE Id = %s", (self.QueueId,))

    def test_eligible_worker_claims(self):
        Job = self.Dm.ClaimQualityTestJob(SENTINEL_WORKER)
        self.assertIsNotNone(Job, "eligible worker should claim the pending row")
        self.assertEqual(Job["Id"], self.QueueId)
        # Re-reset for tearDown's DELETE.
        self.Db.ExecuteNonQuery(
            "UPDATE QualityTestingQueue SET DateStarted=NULL, Status='Pending' WHERE Id=%s",
            (self.QueueId,),
        )

    def test_paused_worker_refused(self):
        self.Db.ExecuteNonQuery(
            "UPDATE Workers SET Status='Paused' WHERE WorkerName=%s", (SENTINEL_WORKER,),
        )
        Job = self.Dm.ClaimQualityTestJob(SENTINEL_WORKER)
        self.assertIsNone(Job, "Paused worker MUST NOT claim")

    def test_capability_false_refused(self):
        self.Db.ExecuteNonQuery(
            "UPDATE Workers SET QualityTestEnabled=FALSE WHERE WorkerName=%s", (SENTINEL_WORKER,),
        )
        Job = self.Dm.ClaimQualityTestJob(SENTINEL_WORKER)
        self.assertIsNone(Job, "QualityTestEnabled=FALSE worker MUST NOT claim")

    def test_midflight_flip_honored_on_next_claim(self):
        # First claim: capability ON -> success.
        Job = self.Dm.ClaimQualityTestJob(SENTINEL_WORKER)
        self.assertIsNotNone(Job)
        # Re-pend the row to simulate it being re-eligible.
        self.Db.ExecuteNonQuery(
            "UPDATE QualityTestingQueue SET DateStarted=NULL, Status='Pending' WHERE Id=%s",
            (self.QueueId,),
        )
        # Flip capability OFF mid-flight. Next claim must refuse.
        self.Db.ExecuteNonQuery(
            "UPDATE Workers SET QualityTestEnabled=FALSE WHERE WorkerName=%s", (SENTINEL_WORKER,),
        )
        Job2 = self.Dm.ClaimQualityTestJob(SENTINEL_WORKER)
        self.assertIsNone(Job2, "mid-flight QualityTestEnabled=FALSE MUST refuse")

    def test_force_disposition_row_invisible(self):
        # see qt-queue-visibility-and-override.feature.md C4 -- ForceDisposition rows MUST NOT be claimable
        self.Db.ExecuteNonQuery(
            "UPDATE QualityTestingQueue SET ForceDisposition='Replace' WHERE Id=%s",
            (self.QueueId,),
        )
        Job = self.Dm.ClaimQualityTestJob(SENTINEL_WORKER)
        self.assertIsNone(Job, "row with ForceDisposition set MUST be invisible to worker claims")


# Transcode claim authority

SENTINEL_FILE_TRANSCODE = "_test-claim-authority-transcode.mkv"


class TestTranscodeClaimAuthority(unittest.TestCase):
    """ClaimNextPendingJob must honor Workers.Status + Workers.TranscodeEnabled; sentinel queue row at Priority=-1000 with MediaFileId=NULL for safety."""

    @classmethod
    def setUpClass(cls):
        cls.Db = DatabaseService()
        cls.Dm = DatabaseManager()
        cls.Db.ExecuteNonQuery("DELETE FROM Workers WHERE WorkerName = %s", (SENTINEL_WORKER,))
        cls.Db.ExecuteNonQuery(
            "INSERT INTO Workers (WorkerName, Platform, Status, "
            "TranscodeEnabled, QualityTestEnabled, RemuxEnabled, ScanEnabled, "
            "Enabled, AcceptsInterlaced, LastHeartbeat) "
            "VALUES (%s, 'linux', 'Online', TRUE, TRUE, FALSE, TRUE, TRUE, TRUE, NOW())",
            (SENTINEL_WORKER,),
        )

    @classmethod
    def tearDownClass(cls):
        cls.Db.ExecuteNonQuery("DELETE FROM Workers WHERE WorkerName = %s", (SENTINEL_WORKER,))
        cls.Db.ExecuteNonQuery(
            "DELETE FROM TranscodeQueue WHERE RelativePath LIKE %s ESCAPE '!'",
            (EscapeLikePattern("_test-claim-authority-") + "%",),
        )

    def setUp(self):
        self.Db.ExecuteNonQuery(
            "UPDATE Workers SET Status='Online', TranscodeEnabled=TRUE, RemuxEnabled=FALSE, LastHeartbeat=NOW() WHERE WorkerName=%s",
            (SENTINEL_WORKER,),
        )
        # Clear any stale sentinel rows from a prior failed run.
        self.Db.ExecuteNonQuery(
            "DELETE FROM TranscodeQueue WHERE StorageRootId = %s AND RelativePath = %s",
            (SENTINEL_STORAGE_ROOT_ID, SENTINEL_FILE_TRANSCODE),
        )
        self.Db.ExecuteNonQuery(
            "INSERT INTO TranscodeQueue "
            "(StorageRootId, RelativePath, FileName, Directory, SizeBytes, SizeMB, "
            "Priority, Status, ProcessingMode, MediaFileId, DateAdded) "
            "VALUES (%s, %s, '_test.mkv', '_test', 1, 1.0, -1000, 'Pending', 'Transcode', NULL, NOW())",
            (SENTINEL_STORAGE_ROOT_ID, SENTINEL_FILE_TRANSCODE),
        )
        Rows = self.Db.ExecuteQuery(
            "SELECT Id FROM TranscodeQueue WHERE StorageRootId = %s AND RelativePath = %s",
            (SENTINEL_STORAGE_ROOT_ID, SENTINEL_FILE_TRANSCODE),
        )
        self.QueueId = Rows[0]["Id"]

    def tearDown(self):
        self.Db.ExecuteNonQuery("DELETE FROM TranscodeQueue WHERE Id = %s", (self.QueueId,))

    def test_eligible_worker_claims(self):
        Job = self.Dm.ClaimNextPendingJob(SENTINEL_WORKER, AcceptsInterlaced=True)
        # production rows outrank our Priority=-1000 sentinel; only verify claim shape when sentinel wins
        if Job is None:
            ProdPending = self.Db.ExecuteQuery(
                "SELECT COUNT(*) AS n FROM TranscodeQueue WHERE Status='Pending' AND Priority > -1000",
            )
            self.assertGreater(
                ProdPending[0]["n"], 0,
                "claim returned None and no production rows exist -- eligible worker should have claimed sentinel",
            )
        else:
            self.assertIsNotNone(Job.Id, "claim returned a job with no Id")
            # If we did claim our sentinel, re-pend it for tearDown DELETE.
            if Job.Id == self.QueueId:
                self.Db.ExecuteNonQuery(
                    "UPDATE TranscodeQueue SET Status='Pending', ClaimedBy=NULL, ClaimedAt=NULL, DateStarted=NULL WHERE Id=%s",
                    (self.QueueId,),
                )

    def test_paused_worker_refused(self):
        self.Db.ExecuteNonQuery(
            "UPDATE Workers SET Status='Paused' WHERE WorkerName=%s", (SENTINEL_WORKER,),
        )
        Job = self.Dm.ClaimNextPendingJob(SENTINEL_WORKER, AcceptsInterlaced=True)
        self.assertIsNone(Job, "Paused worker MUST NOT claim")

    def test_transcode_disabled_refused(self):
        self.Db.ExecuteNonQuery(
            "UPDATE Workers SET TranscodeEnabled=FALSE WHERE WorkerName=%s", (SENTINEL_WORKER,),
        )
        Job = self.Dm.ClaimNextPendingJob(SENTINEL_WORKER, AcceptsInterlaced=True)
        self.assertIsNone(Job, "TranscodeEnabled=FALSE worker MUST NOT claim Transcode row")


# Remux claim authority

SENTINEL_FILE_REMUX = "_test-claim-authority-remux.mkv"


class TestRemuxClaimAuthority(unittest.TestCase):
    """ClaimNextPendingJob must honor Workers.Status + Workers.RemuxEnabled for Remux-mode rows."""

    @classmethod
    def setUpClass(cls):
        cls.Db = DatabaseService()
        cls.Dm = DatabaseManager()
        cls.Db.ExecuteNonQuery("DELETE FROM Workers WHERE WorkerName = %s", (SENTINEL_WORKER,))
        cls.Db.ExecuteNonQuery(
            "INSERT INTO Workers (WorkerName, Platform, Status, "
            "TranscodeEnabled, QualityTestEnabled, RemuxEnabled, ScanEnabled, "
            "Enabled, AcceptsInterlaced, LastHeartbeat) "
            "VALUES (%s, 'linux', 'Online', FALSE, TRUE, TRUE, TRUE, TRUE, TRUE, NOW())",
            (SENTINEL_WORKER,),
        )

    @classmethod
    def tearDownClass(cls):
        cls.Db.ExecuteNonQuery("DELETE FROM Workers WHERE WorkerName = %s", (SENTINEL_WORKER,))
        cls.Db.ExecuteNonQuery(
            "DELETE FROM TranscodeQueue WHERE RelativePath LIKE %s ESCAPE '!'",
            (EscapeLikePattern("_test-claim-authority-") + "%",),
        )

    def setUp(self):
        self.Db.ExecuteNonQuery(
            "UPDATE Workers SET Status='Online', TranscodeEnabled=FALSE, RemuxEnabled=TRUE, LastHeartbeat=NOW() WHERE WorkerName=%s",
            (SENTINEL_WORKER,),
        )
        self.Db.ExecuteNonQuery(
            "DELETE FROM TranscodeQueue WHERE StorageRootId = %s AND RelativePath = %s",
            (SENTINEL_STORAGE_ROOT_ID, SENTINEL_FILE_REMUX),
        )
        self.Db.ExecuteNonQuery(
            "INSERT INTO TranscodeQueue "
            "(StorageRootId, RelativePath, FileName, Directory, SizeBytes, SizeMB, "
            "Priority, Status, ProcessingMode, MediaFileId, DateAdded) "
            "VALUES (%s, %s, '_test.mkv', '_test', 1, 1.0, -1000, 'Pending', 'Remux', NULL, NOW())",
            (SENTINEL_STORAGE_ROOT_ID, SENTINEL_FILE_REMUX),
        )
        Rows = self.Db.ExecuteQuery(
            "SELECT Id FROM TranscodeQueue WHERE StorageRootId = %s AND RelativePath = %s",
            (SENTINEL_STORAGE_ROOT_ID, SENTINEL_FILE_REMUX),
        )
        self.QueueId = Rows[0]["Id"]

    def tearDown(self):
        self.Db.ExecuteNonQuery("DELETE FROM TranscodeQueue WHERE Id = %s", (self.QueueId,))

    def test_eligible_worker_claims(self):
        Job = self.Dm.ClaimNextPendingJob(SENTINEL_WORKER)
        if Job is None:
            ProdPending = self.Db.ExecuteQuery(
                "SELECT COUNT(*) AS n FROM TranscodeQueue "
                "WHERE Status='Pending' AND Priority > -1000 "
                "AND ProcessingMode IN ('Remux','Quick','AudioFix','SubtitleFix')",
            )
            self.assertGreater(
                ProdPending[0]["n"], 0,
                "claim returned None and no production remux rows exist -- eligible worker should have claimed sentinel",
            )
        else:
            self.assertIsNotNone(Job.Id)
            if Job.Id == self.QueueId:
                self.Db.ExecuteNonQuery(
                    "UPDATE TranscodeQueue SET Status='Pending', ClaimedBy=NULL, ClaimedAt=NULL, DateStarted=NULL WHERE Id=%s",
                    (self.QueueId,),
                )

    def test_paused_worker_refused(self):
        self.Db.ExecuteNonQuery(
            "UPDATE Workers SET Status='Paused' WHERE WorkerName=%s", (SENTINEL_WORKER,),
        )
        Job = self.Dm.ClaimNextPendingJob(SENTINEL_WORKER)
        self.assertIsNone(Job, "Paused worker MUST NOT claim remux")

    def test_remux_disabled_refused(self):
        self.Db.ExecuteNonQuery(
            "UPDATE Workers SET RemuxEnabled=FALSE WHERE WorkerName=%s", (SENTINEL_WORKER,),
        )
        Job = self.Dm.ClaimNextPendingJob(SENTINEL_WORKER)
        self.assertIsNone(Job, "RemuxEnabled=FALSE worker with TranscodeEnabled=FALSE MUST NOT claim any row")


# directive: worker-routing | # see worker-routing.C15 -- NVENC routing truth-table

NVENC_TEST_WORKER_CAPABLE = "_test-nvenc-routing-capable"
NVENC_TEST_WORKER_NOT_CAPABLE = "_test-nvenc-routing-not-capable"
NVENC_TEST_PROFILE_NVENC = "_test-nvenc-routing-NVENC-profile"
NVENC_TEST_PROFILE_CPU = "_test-nvenc-routing-CPU-profile"
NVENC_TEST_FILE_NVENC = "_test-nvenc-routing-nvenc-file.mkv"
NVENC_TEST_FILE_CPU = "_test-nvenc-routing-cpu-file.mkv"


# directive: worker-routing | # see worker-routing.C15
class TestNvencRouting(unittest.TestCase):
    """ClaimNextPendingJob NVENC truth table: 2 sentinel workers x 2 sentinel profiles x 2 sentinel media files; Priority=+10000 so sentinels outrank production."""

    @classmethod
    def setUpClass(cls):
        cls.Db = DatabaseService()
        cls.Dm = DatabaseManager()
        cls._WipeFixtures()
        cls.Db.ExecuteNonQuery(
            "INSERT INTO Profiles (ProfileName, usenvidiahardware) VALUES (%s, 1)",
            (NVENC_TEST_PROFILE_NVENC,),
        )
        cls.Db.ExecuteNonQuery(
            "INSERT INTO Profiles (ProfileName, usenvidiahardware) VALUES (%s, 0)",
            (NVENC_TEST_PROFILE_CPU,),
        )
        cls.Db.ExecuteNonQuery(
            "INSERT INTO MediaFiles (FileName, AssignedProfile) VALUES (%s, %s)",
            (NVENC_TEST_FILE_NVENC, NVENC_TEST_PROFILE_NVENC),
        )
        cls.Db.ExecuteNonQuery(
            "INSERT INTO MediaFiles (FileName, AssignedProfile) VALUES (%s, %s)",
            (NVENC_TEST_FILE_CPU, NVENC_TEST_PROFILE_CPU),
        )
        Rows = cls.Db.ExecuteQuery(
            "SELECT Id, FileName FROM MediaFiles WHERE FileName IN (%s, %s)",
            (NVENC_TEST_FILE_NVENC, NVENC_TEST_FILE_CPU),
        )
        cls.MfIdByName = {(R.get('FileName') or R.get('filename')): (R.get('Id') or R.get('id')) for R in Rows}
        cls.Db.ExecuteNonQuery(
            "INSERT INTO Workers (WorkerName, Platform, Status, TranscodeEnabled, "
            "QualityTestEnabled, RemuxEnabled, ScanEnabled, Enabled, AcceptsInterlaced, "
            "nvenccapable, LastHeartbeat) "
            "VALUES (%s, 'linux', 'Online', TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, NOW())",
            (NVENC_TEST_WORKER_CAPABLE,),
        )
        cls.Db.ExecuteNonQuery(
            "INSERT INTO Workers (WorkerName, Platform, Status, TranscodeEnabled, "
            "QualityTestEnabled, RemuxEnabled, ScanEnabled, Enabled, AcceptsInterlaced, "
            "nvenccapable, LastHeartbeat) "
            "VALUES (%s, 'linux', 'Online', TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, FALSE, NOW())",
            (NVENC_TEST_WORKER_NOT_CAPABLE,),
        )

    @classmethod
    def tearDownClass(cls):
        cls._WipeFixtures()

    @classmethod
    def _WipeFixtures(cls):
        """Delete all sentinel rows across TranscodeQueue/MediaFiles/Profiles/Workers (idempotent)."""
        cls.Db.ExecuteNonQuery(
            "DELETE FROM TranscodeQueue WHERE FileName IN (%s, %s)",
            (NVENC_TEST_FILE_NVENC, NVENC_TEST_FILE_CPU),
        )
        cls.Db.ExecuteNonQuery(
            "DELETE FROM MediaFiles WHERE FileName IN (%s, %s)",
            (NVENC_TEST_FILE_NVENC, NVENC_TEST_FILE_CPU),
        )
        cls.Db.ExecuteNonQuery(
            "DELETE FROM Profiles WHERE ProfileName IN (%s, %s)",
            (NVENC_TEST_PROFILE_NVENC, NVENC_TEST_PROFILE_CPU),
        )
        cls.Db.ExecuteNonQuery(
            "DELETE FROM Workers WHERE WorkerName IN (%s, %s)",
            (NVENC_TEST_WORKER_CAPABLE, NVENC_TEST_WORKER_NOT_CAPABLE),
        )

    def _EnqueueRow(self, FileName):
        """Insert a high-priority sentinel TranscodeQueue row pointing at one sentinel MediaFile; returns new queue row Id."""
        MfId = self.MfIdByName[FileName]
        self.Db.ExecuteNonQuery(
            "INSERT INTO TranscodeQueue "
            "(StorageRootId, RelativePath, FileName, Directory, SizeBytes, SizeMB, "
            "Priority, Status, ProcessingMode, MediaFileId, DateAdded) "
            "VALUES (%s, %s, %s, '_test', 1, 1.0, 10000, 'Pending', 'Transcode', %s, NOW())",
            (SENTINEL_STORAGE_ROOT_ID, FileName, FileName, MfId),
        )
        Rows = self.Db.ExecuteQuery(
            "SELECT Id FROM TranscodeQueue WHERE FileName = %s AND Status = 'Pending'",
            (FileName,),
        )
        return Rows[0]["Id"] if Rows else None

    def _DeleteQueueRow(self, QueueId):
        """Delete one sentinel queue row by Id (idempotent on None)."""
        if QueueId is not None:
            self.Db.ExecuteNonQuery("DELETE FROM TranscodeQueue WHERE Id = %s", (QueueId,))

    def test_nvenc_profile_capable_worker_claims(self):
        """NVENC profile + nvenccapable=TRUE -> claim succeeds."""
        QId = self._EnqueueRow(NVENC_TEST_FILE_NVENC)
        try:
            Job = self.Dm.ClaimNextPendingJob(NVENC_TEST_WORKER_CAPABLE, AcceptsInterlaced=True)
            self.assertIsNotNone(Job, "nvenccapable=TRUE worker MUST claim NVENC profile row")
            self.assertEqual(Job.Id, QId, "Claimed row Id mismatch -- expected sentinel queue row")
        finally:
            self._DeleteQueueRow(QId)

    def test_nvenc_profile_not_capable_worker_refused(self):
        """NVENC profile + nvenccapable=FALSE -> claim refused (NvencGate blocks)."""
        QId = self._EnqueueRow(NVENC_TEST_FILE_NVENC)
        try:
            Job = self.Dm.ClaimNextPendingJob(NVENC_TEST_WORKER_NOT_CAPABLE, AcceptsInterlaced=True)
            self.assertIsNone(Job, "nvenccapable=FALSE worker MUST NOT claim NVENC profile row")
        finally:
            self._DeleteQueueRow(QId)

    def test_cpu_profile_capable_worker_claims(self):
        """Non-NVENC profile + nvenccapable=TRUE -> claim succeeds."""
        QId = self._EnqueueRow(NVENC_TEST_FILE_CPU)
        try:
            Job = self.Dm.ClaimNextPendingJob(NVENC_TEST_WORKER_CAPABLE, AcceptsInterlaced=True)
            self.assertIsNotNone(Job, "nvenccapable=TRUE worker MUST claim CPU profile row")
            self.assertEqual(Job.Id, QId, "Claimed row Id mismatch -- expected sentinel queue row")
        finally:
            self._DeleteQueueRow(QId)

    def test_cpu_profile_not_capable_worker_claims(self):
        """Non-NVENC profile + nvenccapable=FALSE -> claim succeeds (NvencGate inactive when usenvidiahardware=0)."""
        QId = self._EnqueueRow(NVENC_TEST_FILE_CPU)
        try:
            Job = self.Dm.ClaimNextPendingJob(NVENC_TEST_WORKER_NOT_CAPABLE, AcceptsInterlaced=True)
            self.assertIsNotNone(Job, "nvenccapable=FALSE worker MUST claim CPU profile row (NVENC gate not applicable)")
            self.assertEqual(Job.Id, QId, "Claimed row Id mismatch -- expected sentinel queue row")
        finally:
            self._DeleteQueueRow(QId)


if __name__ == "__main__":
    unittest.main()
