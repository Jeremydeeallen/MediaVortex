# directive: target-policy-1a-tables | # see policy.C9 -- a migration changes a verdict without touching the file; the pipeline changes a verdict by replacing or rescanning it (mtime moves)
import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

_SCRIPT = Path(__file__).resolve().parent.parent.parent / 'Scripts' / 'Golden' / 'SnapshotCompliance.py'


# directive: target-policy-1a-tables | # see policy.C9
def _LoadModule():
    Spec = importlib.util.spec_from_file_location('SnapshotCompliance', _SCRIPT)
    Module = importlib.util.module_from_spec(Spec)
    Spec.loader.exec_module(Module)
    return Module


# directive: target-policy-1a-tables | # see policy.C9
class TestComplianceCountsUnchanged(unittest.TestCase):

    @classmethod
    # directive: target-policy-1a-tables | # see policy.C9
    def setUpClass(cls):
        cls.Snap = _LoadModule()
        cls.Snapshot = cls.Snap.Load()
        cls.Live = cls.Snap.QueryLive()

    # directive: target-policy-1a-tables | # see policy.C9
    def test_snapshot_counts_match_its_own_files(self):
        self.assertEqual(self.Snapshot['Counts'], self.Snap.Counts(self.Snapshot['Files']))

    # directive: target-policy-1a-tables | # see policy.C9
    def test_unchanged_files_keep_their_verdicts(self):
        Result = self.Snap.Compare(self.Snapshot, self.Live)
        Summary = f"moved_by_pipeline={len(Result['Moved'])} new={len(Result['New'])} deleted={len(Result['Deleted'])} since {self.Snapshot['TakenAt']}"
        self.assertEqual(
            Result['Mismatches'], [],
            f"{len(Result['Mismatches'])} file(s) changed a compliance verdict without a file change ({Summary}):\n"
            + '\n'.join(str(M) for M in Result['Mismatches'][:25]),
        )
        print(Summary)


if __name__ == '__main__':
    unittest.main()
