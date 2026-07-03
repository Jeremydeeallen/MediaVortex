# see transcodequeue.S3 -- enqueue non-null contract enforced by source-inspection + live-DB audit.

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Core.Database.DatabaseService import DatabaseService


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

TOP_LEVEL_PRODUCERS = [
    "Features/TranscodeQueue/QueueManagementBusinessService.py",
    "Features/AudioNormalization/SelfHealing/Remediations/EnqueueRetranscode.py",
    "Features/QualityTesting/QualityTestController.py",
]

REPOSITORY_INSERTS = [
    "Features/TranscodeQueue/TranscodeQueueRepository.py",
]

PRODUCTION_INSERT_FILES = TOP_LEVEL_PRODUCERS + REPOSITORY_INSERTS

SNAPSHOT_HOOKS = (
    "SnapshotPolicyOnQueueRow",
    "_SnapshotAudioPoliciesOnRecentInserts",
    "BackfillAllPending",
)


def _ReadFile(RelPath: str) -> str:
    return (REPO_ROOT / RelPath).read_text(encoding="utf-8")


# see transcodequeue.S3
class TestEnqueueSourceContract(unittest.TestCase):
    """Every production file that INSERTs into TranscodeQueue must invoke an AudioPolicy snapshot hook."""

    def test_every_top_level_producer_calls_snapshot_hook(self):
        for RelPath in TOP_LEVEL_PRODUCERS:
            Src = _ReadFile(RelPath)
            self.assertRegex(
                Src, r"INSERT INTO [Tt]ranscode[Qq]ueue",
                f"{RelPath} listed as producer but has no INSERT INTO TranscodeQueue",
            )
            HookHit = any(Hook in Src for Hook in SNAPSHOT_HOOKS)
            self.assertTrue(
                HookHit,
                f"{RelPath} INSERTs into TranscodeQueue but never calls an AudioPolicy snapshot hook "
                f"({', '.join(SNAPSHOT_HOOKS)}). Every producer must satisfy the S3 non-null contract.",
            )

    def test_every_insert_stanza_names_processingmode_column(self):
        Pattern = re.compile(
            r"INSERT INTO [Tt]ranscode[Qq]ueue\s*\(([^)]*)\)",
            re.IGNORECASE | re.DOTALL,
        )
        for RelPath in PRODUCTION_INSERT_FILES:
            Src = _ReadFile(RelPath)
            for Match in Pattern.finditer(Src):
                Columns = Match.group(1)
                self.assertIn(
                    "ProcessingMode", Columns,
                    f"{RelPath} INSERT stanza omits ProcessingMode: {Columns.strip()[:120]}",
                )
                self.assertIn(
                    "StorageRootId", Columns,
                    f"{RelPath} INSERT stanza omits StorageRootId: {Columns.strip()[:120]}",
                )
                self.assertIn(
                    "RelativePath", Columns,
                    f"{RelPath} INSERT stanza omits RelativePath: {Columns.strip()[:120]}",
                )

    def test_no_new_production_producers_bypass_the_contract(self):
        ProductionRoots = ("Features", "Repositories", "Core", "WebService", "WorkerService", "Workers")
        Whitelist = set(str(REPO_ROOT / P) for P in PRODUCTION_INSERT_FILES)
        InsertPattern = re.compile(r"INSERT INTO [Tt]ranscode[Qq]ueue", re.IGNORECASE)
        Offenders = []
        for Root in ProductionRoots:
            RootPath = REPO_ROOT / Root
            if not RootPath.exists():
                continue
            for PyFile in RootPath.rglob("*.py"):
                if str(PyFile) in Whitelist:
                    continue
                try:
                    Src = PyFile.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                if InsertPattern.search(Src):
                    Offenders.append(str(PyFile.relative_to(REPO_ROOT)))
        self.assertEqual(
            Offenders, [],
            f"Unlisted production producer(s) INSERT into TranscodeQueue: {Offenders}. "
            "Add to PRODUCTION_INSERT_FILES here and ensure they call a snapshot hook."
        )


# see transcodequeue.S3 -- live audit of recent pending rows
class TestEnqueueLiveDbAudit(unittest.TestCase):
    """Recent Pending TranscodeQueue rows must have the four contract columns NOT NULL."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.Db = DatabaseService()
            cls.Db.ExecuteQuery("SELECT 1")
        except Exception as Ex:
            raise unittest.SkipTest(f"DB unreachable: {Ex}")

    def test_recent_pending_rows_have_non_null_contract_columns(self):
        Rows = self.Db.ExecuteQuery(
            "SELECT COUNT(*) AS n, "
            "SUM(CASE WHEN StorageRootId IS NULL THEN 1 ELSE 0 END) AS null_sri, "
            "SUM(CASE WHEN RelativePath IS NULL THEN 1 ELSE 0 END) AS null_rp, "
            "SUM(CASE WHEN ProcessingMode IS NULL THEN 1 ELSE 0 END) AS null_pm, "
            "SUM(CASE WHEN AudioPolicyJson IS NULL THEN 1 ELSE 0 END) AS null_apj "
            "FROM TranscodeQueue "
            "WHERE Status = 'Pending' AND DateAdded > NOW() - INTERVAL '1 hour'"
        )
        if not Rows or int(Rows[0].get('n') or 0) == 0:
            self.skipTest("No Pending rows in the last hour to audit")
        Row = Rows[0]
        Total = int(Row.get('n'))
        NullSri = int(Row.get('null_sri') or 0)
        NullRp = int(Row.get('null_rp') or 0)
        NullPm = int(Row.get('null_pm') or 0)
        NullApj = int(Row.get('null_apj') or 0)
        Msg = (
            f"Contract violation across {Total} recent Pending rows: "
            f"NullStorageRootId={NullSri}, NullRelativePath={NullRp}, "
            f"NullProcessingMode={NullPm}, NullAudioPolicyJson={NullApj}"
        )
        self.assertEqual(NullSri, 0, Msg)
        self.assertEqual(NullRp, 0, Msg)
        self.assertEqual(NullPm, 0, Msg)
        self.assertEqual(NullApj, 0, Msg)


if __name__ == "__main__":
    unittest.main()
