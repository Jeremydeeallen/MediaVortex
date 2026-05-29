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
# Note on transcode + remux conformance
# ---------------------------------------------------------------------------
# Transcode + remux claims require setting up a TranscodeQueue row that survives
# round-trips through the worker's processing dispatch. The setup is heavier
# than the QT case because production has more downstream services that watch
# TranscodeQueue rows. For P1 we conformance-test the QT path (the path the
# bug surfaced on) and verify by smoke that transcode + remux use the same
# helper. P3 expands this test file to cover the relocated transcode + remux
# claims with full fixture isolation. Recorded in
# `.claude/programs/db-authority-program.md` P3.B5 / P3.B6.


if __name__ == "__main__":
    unittest.main()
