import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.AudioPolicyAdmissionGate import AudioPolicyAdmissionGate


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S14
class TestBackfillAllPendingHook(unittest.TestCase):
    """S4 / S14: QMBS post-INSERT hook calls AudioPolicyAdmissionGate.BackfillAllPending; no time window."""

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S14
    def test_backfill_all_pending_executes_update_with_no_time_window(self):
        with patch(
            'Features.AudioNormalization.AudioPolicyAdmissionGate.DatabaseService'
        ) as MockDb:
            Instance = MagicMock()
            MockDb.return_value = Instance
            AudioPolicyAdmissionGate().BackfillAllPending()
            Instance.ExecuteNonQuery.assert_called_once()
            Sql = Instance.ExecuteNonQuery.call_args.args[0]
            self.assertIn('UPDATE TranscodeQueue', Sql)
            self.assertIn('AudioPolicyJson IS NULL', Sql)
            self.assertNotIn('INTERVAL', Sql)
            self.assertNotIn('60 seconds', Sql)

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S14
    def test_legacy_backfill_recent_inserts_still_uses_time_window(self):
        with patch(
            'Features.AudioNormalization.AudioPolicyAdmissionGate.DatabaseService'
        ) as MockDb:
            Instance = MagicMock()
            MockDb.return_value = Instance
            AudioPolicyAdmissionGate().BackfillRecentInserts()
            Sql = Instance.ExecuteNonQuery.call_args.args[0]
            self.assertIn('INTERVAL', Sql)

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S14
    def test_qmbs_helper_invokes_backfill_all_pending(self):
        """The QMBS-side wrapper routes to BackfillAllPending (verified by reading the source)."""
        import inspect
        from Features.TranscodeQueue import QueueManagementBusinessService as Mod
        Src = inspect.getsource(Mod.QueueManagementBusinessService._SnapshotAudioPoliciesOnRecentInserts)
        self.assertIn('BackfillAllPending', Src)
        self.assertNotIn('BackfillRecentInserts(', Src)


if __name__ == '__main__':
    unittest.main()
