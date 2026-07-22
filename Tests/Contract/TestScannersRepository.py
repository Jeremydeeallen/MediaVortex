import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.FileScanning.ScannersRepository import ScannersRepository


# directive: transcode-flow-canonical -- C33 AudioVerticalHealth row removed with self-heal deletion
class TestScannersRepository(unittest.TestCase):
    """Live-DB contract: read seeded rows, round-trip Update on ContinuousScan."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('MEDIAVORTEX_DB_HOST', '10.0.0.15')

    def test_list_returns_seeded_scanners(self):
        Rows = ScannersRepository().List()
        Names = {R['scannername'] for R in Rows}
        self.assertIn('ContinuousScan', Names)

    def test_get_unknown_returns_none(self):
        self.assertIsNone(ScannersRepository().Get('NotARealScanner'))

    def test_update_rejects_unknown(self):
        self.assertFalse(ScannersRepository().Update('NotARealScanner', True, 300, 100, False))

    def test_update_round_trips(self):
        Repo = ScannersRepository()
        Before = Repo.Get('ContinuousScan')
        try:
            self.assertTrue(Repo.Update('ContinuousScan', True, 600, 250, True))
            After = Repo.Get('ContinuousScan')
            self.assertEqual(After['enabled'], True)
            self.assertEqual(After['intervalsec'], 600)
            self.assertEqual(After['batchsize'], 250)
            self.assertEqual(After['dryrun'], True)
        finally:
            Repo.Update('ContinuousScan',
                        bool(Before['enabled']),
                        int(Before['intervalsec']),
                        int(Before['batchsize']),
                        bool(Before['dryrun']))

    def test_update_clamps_interval_to_60(self):
        Repo = ScannersRepository()
        Before = Repo.Get('ContinuousScan')
        try:
            Repo.Update('ContinuousScan', False, 5, 100, False)
            After = Repo.Get('ContinuousScan')
            self.assertGreaterEqual(After['intervalsec'], 60)
        finally:
            Repo.Update('ContinuousScan',
                        bool(Before['enabled']),
                        int(Before['intervalsec']),
                        int(Before['batchsize']),
                        bool(Before['dryrun']))


if __name__ == '__main__':
    unittest.main()
