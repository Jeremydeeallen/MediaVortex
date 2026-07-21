import unittest
from pathlib import Path as _PyPath

from Core.Database.DatabaseService import DatabaseService


_REPO = _PyPath(__file__).resolve().parents[2]


# directive: e2e-bug-fixes | # see e2e-bug-fixes.C29
class TestFileReplacementDrain(unittest.TestCase):

    # directive: e2e-bug-fixes | # see e2e-bug-fixes.C29
    def test_no_stuck_replace_rows_in_steady_state(self):
        Db = DatabaseService()
        Rows = Db.ExecuteQuery(
            "SELECT COUNT(*) AS stuck FROM TranscodeAttempts "
            "WHERE Disposition = 'Replace' "
            "AND FileReplaced = FALSE "
            "AND AttemptDate < NOW() - INTERVAL '15 minutes'"
        )
        Stuck = int(Rows[0]['stuck'])
        self.assertEqual(Stuck, 0, f"FileReplacement drain invariant violated: {Stuck} attempts have Disposition=Replace AND FileReplaced=False for >15min")

    # directive: e2e-bug-fixes | # see e2e-bug-fixes.C29
    def test_dispatchdisposition_fails_loud_on_pfr_failure(self):
        Source = (_REPO / 'Features' / 'TranscodeJob' / 'ProcessTranscodeQueueService.py').read_text(encoding='utf-8')
        Idx = Source.find('def DispatchDisposition')
        self.assertNotEqual(Idx, -1, "DispatchDisposition method not found")
        EndIdx = Source.find('\n    def ', Idx + 1)
        if EndIdx == -1:
            EndIdx = len(Source)
        Body = Source[Idx:EndIdx]
        self.assertIn('PfrResult', Body,
                      "DispatchDisposition must inspect ProcessFileReplacement's return value")
        self.assertIn('raise RuntimeError', Body,
                      "DispatchDisposition must raise on PFR Success=False (fail-loud, not silent swallow)")

    # directive: e2e-bug-fixes | # see e2e-bug-fixes.C29
    def test_selfheal_service_deleted(self):
        Path = _REPO / 'Features' / 'FileReplacement' / 'FileReplacementSelfHealService.py'
        self.assertFalse(Path.exists(),
                         "FileReplacementSelfHealService.py must NOT exist -- cross-tenant WebService-doing-Worker-work was a DDD violation; deleted in C29")
        WebSvc = (_REPO / 'WebService' / 'Main.py').read_text(encoding='utf-8')
        self.assertNotIn('FileReplacementSelfHeal', WebSvc,
                         "WebService must not spawn a FileReplacementSelfHeal thread")


if __name__ == '__main__':
    unittest.main()
