import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestBuildProbeSummary(unittest.TestCase):

    def _MakeService(self, BacklogRow=None, WorkerRows=None):
        from Features.Activity.Services.DashboardSnapshotService import DashboardSnapshotService
        DbMock = MagicMock()
        DbMock.ExecuteQuery = MagicMock(side_effect=[
            [{'SettingValue': '15'}],
            [{'SettingValue': '300'}],
        ])
        with patch('Features.Activity.Services.DashboardSnapshotService.ProgressSmoothingService'):
            Svc = DashboardSnapshotService(Db=DbMock)
        Svc.Db = MagicMock()
        Svc.Db.ExecuteQuery = MagicMock(side_effect=[
            [BacklogRow or {'needsreprobe': 0, 'freshunprobed': 0, 'failurecap': 0, 'probedlasthour': 0}],
            WorkerRows or [],
        ])
        return Svc

    def test_empty_state_returns_zeroes(self):
        Svc = self._MakeService()
        Result = Svc._BuildProbeSummary()
        self.assertEqual(Result['NeedsReprobe'], 0)
        self.assertEqual(Result['FreshUnprobed'], 0)
        self.assertEqual(Result['FailureCap'], 0)
        self.assertEqual(Result['ProbedLastHour'], 0)
        self.assertEqual(Result['Workers'], [])

    def test_backlog_counts_populated(self):
        Svc = self._MakeService(
            BacklogRow={'needsreprobe': 24678, 'freshunprobed': 59, 'failurecap': 56, 'probedlasthour': 48},
        )
        Result = Svc._BuildProbeSummary()
        self.assertEqual(Result['NeedsReprobe'], 24678)
        self.assertEqual(Result['FreshUnprobed'], 59)
        self.assertEqual(Result['FailureCap'], 56)
        self.assertEqual(Result['ProbedLastHour'], 48)

    def test_per_worker_populated(self):
        Svc = self._MakeService(
            WorkerRows=[
                {'workername': 'I9-2024', 'status': 'Online', 'probeenabled': True, 'inflightprobes': 1},
                {'workername': 'mediavortex-workers-worker-1', 'status': 'Online', 'probeenabled': True, 'inflightprobes': 0},
            ],
        )
        Result = Svc._BuildProbeSummary()
        self.assertEqual(len(Result['Workers']), 2)
        self.assertEqual(Result['Workers'][0]['WorkerName'], 'I9-2024')
        self.assertEqual(Result['Workers'][0]['InFlightProbes'], 1)
        self.assertTrue(Result['Workers'][0]['ProbeEnabled'])
        self.assertEqual(Result['Workers'][1]['InFlightProbes'], 0)


if __name__ == '__main__':
    unittest.main()
