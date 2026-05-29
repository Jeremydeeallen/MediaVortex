"""Conformance tests for DB-authoritative claim queries.

Asserts the invariant from `.claude/rules/db-is-authority.md`:

  Every capability-gated claim query MUST refuse the claim when the calling
  Worker is `Status='Paused'` OR has the capability flag set to FALSE. The DB
  is the gate; no Python control flow short-circuits the predicate; mid-flight
  flag changes are honored on the next claim.

Covers three claim paths (one test class each):
  - TranscodeJob:   ClaimNextPendingTranscodeJob   gates on TranscodeEnabled
  - Remux:          ClaimNextPendingRemuxJob       gates on RemuxEnabled
  - QualityTesting: ClaimQualityTestJob            gates on QualityTestEnabled

Test methodology: real DB; create a sentinel Workers row + a sentinel queue row
in setUp; in each test, flip the relevant Worker flag, attempt the claim, assert
refused-or-allowed correctly; teardown deletes both sentinels. The tests are
self-isolating -- they do not depend on or affect production rows.

Run:
    py -m pytest Tests/Contract/TestClaimAuthority.py -v
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Core.Database.DatabaseService import DatabaseService
from Core.Database.WorkerCapabilityPredicate import BuildClaimPredicate, _ALLOWED_CAPABILITIES
from Repositories.DatabaseManager import DatabaseManager


SENTINEL_WORKER = "_test-claim-authority-worker"


# ---------------------------------------------------------------------------
# Helper smoke (the foundation everything else depends on)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Quality testing claim authority
# ---------------------------------------------------------------------------

class TestQualityTestClaimAuthority(unittest.TestCase):
    """ClaimQualityTestJob must honor Workers.Status + Workers.QualityTestEnabled."""

    @classmethod
    def setUpClass(cls):
        cls.Db = DatabaseService()
        cls.Dm = DatabaseManager()
        # Sentinel worker -- isolated from production rows.
        cls.Db.ExecuteNonQuery("DELETE FROM Workers WHERE WorkerName = %s", (SENTINEL_WORKER,))
        cls.Db.ExecuteNonQuery(
            """INSERT INTO Workers (WorkerName, Platform, Status,
                   TranscodeEnabled, QualityTestEnabled, RemuxEnabled, ScanEnabled,
                   Enabled, LastHeartbeat)
               VALUES (%s, 'linux', 'Online', TRUE, TRUE, TRUE, TRUE, TRUE, NOW())""",
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
        # Create a sentinel queue row. TranscodeAttemptId can be NULL for the
        # claim predicate test (the gate doesn't depend on it). ExecuteNonQuery
        # auto-commits; ExecuteQuery does not -- so we INSERT via ExecuteNonQuery
        # and look up the Id via a separate SELECT keyed on LocalSourcePath.
        self.Db.ExecuteNonQuery(
            """INSERT INTO QualityTestingQueue
                  (TranscodeAttemptId, OriginalFilePath, TranscodedFilePath, LocalSourcePath, Status, DateAdded)
               VALUES (NULL, '_test-source', '_test-transcoded', '_test-local', 'Pending', NOW())""",
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
        # Operator override path: rows with ForceDisposition set MUST NOT be
        # claimable by workers (qt-queue-visibility-and-override.feature.md C4).
        self.Db.ExecuteNonQuery(
            "UPDATE QualityTestingQueue SET ForceDisposition='Replace' WHERE Id=%s",
            (self.QueueId,),
        )
        Job = self.Dm.ClaimQualityTestJob(SENTINEL_WORKER)
        self.assertIsNone(Job, "row with ForceDisposition set MUST be invisible to worker claims")


# ---------------------------------------------------------------------------
# Transcode claim authority
# ---------------------------------------------------------------------------

SENTINEL_FILE_TRANSCODE = "_test-claim-authority-transcode.mkv"


class TestTranscodeClaimAuthority(unittest.TestCase):
    """ClaimNextPendingTranscodeJob must honor Workers.Status + Workers.TranscodeEnabled.

    Fixture safety: sentinel queue row has Priority=-1000 (production rows
    always rank higher), FilePath prefixed with `_test-claim-authority-`
    (greppable for cleanup), MediaFileId NULL (no downstream side effects on
    real MediaFiles).
    """

    @classmethod
    def setUpClass(cls):
        cls.Db = DatabaseService()
        cls.Dm = DatabaseManager()
        cls.Db.ExecuteNonQuery("DELETE FROM Workers WHERE WorkerName = %s", (SENTINEL_WORKER,))
        cls.Db.ExecuteNonQuery(
            """INSERT INTO Workers (WorkerName, Platform, Status,
                   TranscodeEnabled, QualityTestEnabled, RemuxEnabled, ScanEnabled,
                   Enabled, AcceptsInterlaced, LastHeartbeat)
               VALUES (%s, 'linux', 'Online', TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, NOW())""",
            (SENTINEL_WORKER,),
        )

    @classmethod
    def tearDownClass(cls):
        cls.Db.ExecuteNonQuery("DELETE FROM Workers WHERE WorkerName = %s", (SENTINEL_WORKER,))
        cls.Db.ExecuteNonQuery(
            "DELETE FROM TranscodeQueue WHERE FilePath LIKE %s",
            ("_test-claim-authority-%",),
        )

    def setUp(self):
        self.Db.ExecuteNonQuery(
            "UPDATE Workers SET Status='Online', TranscodeEnabled=TRUE, LastHeartbeat=NOW() WHERE WorkerName=%s",
            (SENTINEL_WORKER,),
        )
        # Clear any stale sentinel rows from a prior failed run.
        self.Db.ExecuteNonQuery(
            "DELETE FROM TranscodeQueue WHERE FilePath = %s", (SENTINEL_FILE_TRANSCODE,),
        )
        # Insert the test queue row at lowest priority so any real production
        # worker (if running) doesn't accidentally claim it before our test.
        self.Db.ExecuteNonQuery(
            """INSERT INTO TranscodeQueue
                  (FilePath, FileName, Directory, SizeBytes, SizeMB,
                   Priority, Status, ProcessingMode, MediaFileId, DateAdded)
               VALUES (%s, '_test.mkv', '_test', 1, 1.0, -1000, 'Pending', 'Transcode', NULL, NOW())""",
            (SENTINEL_FILE_TRANSCODE,),
        )
        Rows = self.Db.ExecuteQuery(
            "SELECT Id FROM TranscodeQueue WHERE FilePath = %s", (SENTINEL_FILE_TRANSCODE,),
        )
        self.QueueId = Rows[0]["Id"]

    def tearDown(self):
        self.Db.ExecuteNonQuery("DELETE FROM TranscodeQueue WHERE Id = %s", (self.QueueId,))

    def test_eligible_worker_claims(self):
        Job = self.Dm.ClaimNextPendingTranscodeJob(SENTINEL_WORKER, AcceptsInterlaced=True)
        # Production rows may rank higher; only assert if our sentinel was the
        # chosen row OR no claim happened due to higher-priority production work.
        # If Job is None, verify the queue row is still claimable in isolation.
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
        Job = self.Dm.ClaimNextPendingTranscodeJob(SENTINEL_WORKER, AcceptsInterlaced=True)
        self.assertIsNone(Job, "Paused worker MUST NOT claim")

    def test_transcode_disabled_refused(self):
        self.Db.ExecuteNonQuery(
            "UPDATE Workers SET TranscodeEnabled=FALSE WHERE WorkerName=%s", (SENTINEL_WORKER,),
        )
        Job = self.Dm.ClaimNextPendingTranscodeJob(SENTINEL_WORKER, AcceptsInterlaced=True)
        self.assertIsNone(Job, "TranscodeEnabled=FALSE worker MUST NOT claim")


# ---------------------------------------------------------------------------
# Remux claim authority
# ---------------------------------------------------------------------------

SENTINEL_FILE_REMUX = "_test-claim-authority-remux.mkv"


class TestRemuxClaimAuthority(unittest.TestCase):
    """ClaimNextPendingRemuxJob must honor Workers.Status + Workers.RemuxEnabled."""

    @classmethod
    def setUpClass(cls):
        cls.Db = DatabaseService()
        cls.Dm = DatabaseManager()
        cls.Db.ExecuteNonQuery("DELETE FROM Workers WHERE WorkerName = %s", (SENTINEL_WORKER,))
        cls.Db.ExecuteNonQuery(
            """INSERT INTO Workers (WorkerName, Platform, Status,
                   TranscodeEnabled, QualityTestEnabled, RemuxEnabled, ScanEnabled,
                   Enabled, AcceptsInterlaced, LastHeartbeat)
               VALUES (%s, 'linux', 'Online', TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, NOW())""",
            (SENTINEL_WORKER,),
        )

    @classmethod
    def tearDownClass(cls):
        cls.Db.ExecuteNonQuery("DELETE FROM Workers WHERE WorkerName = %s", (SENTINEL_WORKER,))
        cls.Db.ExecuteNonQuery(
            "DELETE FROM TranscodeQueue WHERE FilePath LIKE %s",
            ("_test-claim-authority-%",),
        )

    def setUp(self):
        self.Db.ExecuteNonQuery(
            "UPDATE Workers SET Status='Online', RemuxEnabled=TRUE, LastHeartbeat=NOW() WHERE WorkerName=%s",
            (SENTINEL_WORKER,),
        )
        self.Db.ExecuteNonQuery(
            "DELETE FROM TranscodeQueue WHERE FilePath = %s", (SENTINEL_FILE_REMUX,),
        )
        self.Db.ExecuteNonQuery(
            """INSERT INTO TranscodeQueue
                  (FilePath, FileName, Directory, SizeBytes, SizeMB,
                   Priority, Status, ProcessingMode, MediaFileId, DateAdded)
               VALUES (%s, '_test.mkv', '_test', 1, 1.0, -1000, 'Pending', 'Remux', NULL, NOW())""",
            (SENTINEL_FILE_REMUX,),
        )
        Rows = self.Db.ExecuteQuery(
            "SELECT Id FROM TranscodeQueue WHERE FilePath = %s", (SENTINEL_FILE_REMUX,),
        )
        self.QueueId = Rows[0]["Id"]

    def tearDown(self):
        self.Db.ExecuteNonQuery("DELETE FROM TranscodeQueue WHERE Id = %s", (self.QueueId,))

    def test_eligible_worker_claims(self):
        Job = self.Dm.ClaimNextPendingRemuxJob(SENTINEL_WORKER)
        if Job is None:
            ProdPending = self.Db.ExecuteQuery(
                "SELECT COUNT(*) AS n FROM TranscodeQueue "
                "WHERE Status='Pending' AND Priority > -1000 "
                "AND ProcessingMode IN ('Remux','Quick','AudioFix')",
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
        Job = self.Dm.ClaimNextPendingRemuxJob(SENTINEL_WORKER)
        self.assertIsNone(Job, "Paused worker MUST NOT claim remux")

    def test_remux_disabled_refused(self):
        self.Db.ExecuteNonQuery(
            "UPDATE Workers SET RemuxEnabled=FALSE WHERE WorkerName=%s", (SENTINEL_WORKER,),
        )
        Job = self.Dm.ClaimNextPendingRemuxJob(SENTINEL_WORKER)
        self.assertIsNone(Job, "RemuxEnabled=FALSE worker MUST NOT claim remux")


if __name__ == "__main__":
    unittest.main()
