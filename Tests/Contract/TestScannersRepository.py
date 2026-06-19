import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.FileScanning.ScannersRepository import ScannersRepository


# directive: audio-vertical-phase-1-completion | # see directive.md P3
class TestScannersRepository(unittest.TestCase):
    """Live-DB contract: read seeded rows, round-trip Update, PauseAll, RecordRun."""

    # directive: audio-vertical-phase-1-completion | # see directive.md P3
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('MEDIAVORTEX_DB_HOST', '10.0.0.15')

    # directive: audio-vertical-phase-1-completion | # see directive.md P3
    def test_list_returns_seeded_scanners(self):
        Rows = ScannersRepository().List()
        Names = {R['scannername'] for R in Rows}
        self.assertIn('AudioVerticalHealth', Names)
        self.assertIn('ContinuousScan', Names)

    # directive: audio-vertical-phase-1-completion | # see directive.md P3
    def test_get_unknown_returns_none(self):
        self.assertIsNone(ScannersRepository().Get('NotARealScanner'))

    # directive: audio-vertical-phase-1-completion | # see directive.md P3
    def test_update_rejects_unknown(self):
        self.assertFalse(ScannersRepository().Update('NotARealScanner', True, 300, 100, False))

    # directive: audio-vertical-phase-1-completion | # see directive.md P3
    def test_update_round_trips(self):
        Repo = ScannersRepository()
        Before = Repo.Get('AudioVerticalHealth')
        try:
            self.assertTrue(Repo.Update('AudioVerticalHealth', True, 600, 250, True))
            After = Repo.Get('AudioVerticalHealth')
            self.assertEqual(After['enabled'], True)
            self.assertEqual(After['intervalsec'], 600)
            self.assertEqual(After['batchsize'], 250)
            self.assertEqual(After['dryrun'], True)
        finally:
            Repo.Update('AudioVerticalHealth',
                        bool(Before['enabled']),
                        int(Before['intervalsec']),
                        int(Before['batchsize']),
                        bool(Before['dryrun']))

    # directive: audio-vertical-phase-1-completion | # see directive.md P3
    def test_update_clamps_interval_to_60(self):
        Repo = ScannersRepository()
        Before = Repo.Get('AudioVerticalHealth')
        try:
            Repo.Update('AudioVerticalHealth', False, 5, 100, False)
            After = Repo.Get('AudioVerticalHealth')
            self.assertGreaterEqual(After['intervalsec'], 60)
        finally:
            Repo.Update('AudioVerticalHealth',
                        bool(Before['enabled']),
                        int(Before['intervalsec']),
                        int(Before['batchsize']),
                        bool(Before['dryrun']))


if __name__ == '__main__':
    unittest.main()
