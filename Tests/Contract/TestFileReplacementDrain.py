import re
import unittest
from pathlib import Path as _PyPath

from Core.Database.DatabaseService import DatabaseService


_REPO = _PyPath(__file__).resolve().parents[2]


# directive: filereplacement-drain-bug
class TestFileReplacementDrain(unittest.TestCase):

    # directive: filereplacement-drain-bug
    def test_no_stuck_replace_rows_in_steady_state(self):
        Db = DatabaseService()
        Rows = Db.ExecuteQuery(
            "SELECT COUNT(*) AS stuck FROM TranscodeAttempts "
            "WHERE Disposition IN ('Replace','BypassReplace') "
            "AND FileReplaced = FALSE "
            "AND AttemptDate < NOW() - INTERVAL '15 minutes' "
            "AND (ErrorMessage IS NULL OR ErrorMessage NOT ILIKE '%%Recovery refused%%')"
        )
        Stuck = int(Rows[0]['stuck'])
        self.assertEqual(Stuck, 0, f"FileReplacement drain invariant violated: {Stuck} attempts have Disposition Replace/BypassReplace AND FileReplaced=False for >15min with no ErrorMessage")

    # directive: filereplacement-drain-bug
    def test_dispatchdisposition_no_longer_silently_swallows(self):
        Source = (_REPO / 'Features' / 'TranscodeJob' / 'ProcessTranscodeQueueService.py').read_text(encoding='utf-8')
        Idx = Source.find('def DispatchDisposition')
        self.assertNotEqual(Idx, -1, "DispatchDisposition method not found")
        EndIdx = Source.find('\n    def ', Idx + 1)
        if EndIdx == -1:
            EndIdx = len(Source)
        Body = Source[Idx:EndIdx]
        self.assertIn('UPDATE TranscodeAttempts', Body,
                      "DispatchDisposition exception handler must write ErrorMessage to surface the failure (no silent swallow)")
        self.assertIn('DispatchDisposition failed', Body)

    # directive: filereplacement-drain-bug
    def test_defense_in_depth_has_fallback_for_zero_oldsize(self):
        Source = (_REPO / 'Features' / 'FileReplacement' / 'FileReplacementBusinessService.py').read_text(encoding='utf-8')
        self.assertIn('EffectiveOldBytes', Source,
                      "FileReplacementBusinessService must use EffectiveOldBytes (fallback computed when OldSizeBytes is 0 or NULL)")
        self.assertIn('LocalGetSize', Source,
                      "FileReplacementBusinessService must fall back to LocalGetSize when stored OldSizeBytes is 0 or NULL")

    # directive: filereplacement-drain-bug
    def test_selfheal_service_exists(self):
        Path = _REPO / 'Features' / 'FileReplacement' / 'FileReplacementSelfHealService.py'
        self.assertTrue(Path.exists(), "FileReplacementSelfHealService.py must exist")
        Source = Path.read_text(encoding='utf-8')
        self.assertIn('class FileReplacementSelfHealService', Source)
        self.assertIn('def Run', Source)

    # directive: filereplacement-drain-bug
    def test_selfheal_wired_into_webservice(self):
        Source = (_REPO / 'WebService' / 'Main.py').read_text(encoding='utf-8')
        self.assertIn('PrivateStartFileReplacementSelfHeal', Source)
        self.assertIn('FileReplacementSelfHealService', Source)

    # directive: filereplacement-drain-bug
    @staticmethod
    def _ExtractFunctionBody(Source, FunctionName):
        Match = re.search(rf'def {FunctionName}\(self[^)]*\):\n(.*?)(?=\n    def |\n[a-zA-Z])', Source, re.DOTALL)
        return Match.group(1) if Match else None


if __name__ == '__main__':
    unittest.main()
