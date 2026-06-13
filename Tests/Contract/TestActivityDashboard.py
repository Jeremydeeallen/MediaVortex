import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Core.Database.DatabaseService import DatabaseService
from Features.TranscodeJob.Models.TranscodeProgressModel import TranscodeProgressModel
from Features.Activity.Models.DashboardSnapshot import DashboardSnapshot
from Features.Activity.Models.ActiveJobRow import ActiveJobRow
from Features.Activity.Models.WorkerTile import WorkerTile
from Features.Activity.Services.ProgressSmoothingService import ProgressSmoothingService
from Features.Activity.Services.DashboardSnapshotService import DashboardSnapshotService


# directive: activity-dashboard-solid | # see activity-dashboard-solid.C1
class TestDashboardSnapshotShape(unittest.TestCase):
    """AC1: BuildSnapshot returns DashboardSnapshot with all expected fields."""

    # directive: activity-dashboard-solid | # see activity-dashboard-solid.C1
    def test_snapshot_has_expected_fields(self):
        Snap = DashboardSnapshotService().BuildSnapshot()
        self.assertIsInstance(Snap, DashboardSnapshot)
        self.assertIsInstance(Snap.Workers, list)
        self.assertIsInstance(Snap.ActiveJobs, list)
        self.assertIsInstance(Snap.QueueCounts, dict)
        self.assertIsInstance(Snap.BadgeState, dict)
        self.assertIn('ActiveJobs', Snap.BadgeState)
        self.assertIn('FailedJobs', Snap.BadgeState)
        self.assertGreaterEqual(Snap.StaleProgressThresholdSec, 1)
        self.assertGreaterEqual(Snap.HeartbeatStaleThresholdSec, 1)


# directive: activity-dashboard-solid | # see activity-dashboard-solid.C2
class TestProgressSmoothingService(unittest.TestCase):
    """AC2: synthetic samples + stale-window behavior."""

    # directive: activity-dashboard-solid | # see activity-dashboard-solid.C2
    def setUp(self):
        self.Db = MagicMock()
        self.Service = ProgressSmoothingService(Db=self.Db, StaleSec=15)

    # directive: activity-dashboard-solid | # see activity-dashboard-solid.C2
    def test_no_rows_returns_none_tuple(self):
        self.Db.ExecuteQuery.return_value = []
        self.assertEqual(self.Service.SmoothForAttempt(1), (None, None, None))

    # directive: activity-dashboard-solid | # see activity-dashboard-solid.C2
    def test_arithmetic_mean_of_fps_samples(self):
        Now = datetime.now(timezone.utc)
        Samples = [100, 5, 95, 0, 80, 105, 8, 90, 0, 100]
        Rows = [
            {
                'CurrentFPS': F, 'CurrentSpeed': '1.0x',
                'ProgressPercent': 50, 'CurrentFrame': 100, 'TotalFrames': 1000,
                'LastProgressUpdate': Now - timedelta(seconds=i),
            }
            for i, F in enumerate(Samples)
        ]
        self.Db.ExecuteQuery.return_value = Rows
        Fps, Speed, Eta = self.Service.SmoothForAttempt(1)
        self.assertAlmostEqual(Fps, round(sum(Samples) / len(Samples), 1))
        self.assertEqual(Speed, 1.0)

    # directive: activity-dashboard-solid | # see activity-dashboard-solid.C2
    def test_stale_window_returns_none(self):
        StaleRow = {
            'CurrentFPS': 50.0, 'CurrentSpeed': '1.0x',
            'ProgressPercent': 50, 'CurrentFrame': 100, 'TotalFrames': 1000,
            'LastProgressUpdate': datetime.now(timezone.utc) - timedelta(seconds=60),
        }
        self.Db.ExecuteQuery.return_value = [StaleRow]
        self.assertEqual(self.Service.SmoothForAttempt(1), (None, None, None))

    # directive: activity-dashboard-solid | # see activity-dashboard-solid.C2
    def test_eta_computed_from_remaining_frames(self):
        Now = datetime.now(timezone.utc)
        Rows = [{
            'CurrentFPS': 50.0, 'CurrentSpeed': '1.0x',
            'ProgressPercent': 50, 'CurrentFrame': 100, 'TotalFrames': 200,
            'LastProgressUpdate': Now,
        }]
        self.Db.ExecuteQuery.return_value = Rows
        Fps, Speed, Eta = self.Service.SmoothForAttempt(1)
        self.assertEqual(Eta, 2)


# directive: activity-dashboard-solid | # see activity-dashboard-solid.C11
class TestTranscodeProgressTimestampDefault(unittest.TestCase):
    """AC11: TranscodeProgressModel.__post_init__ always populates LastProgressUpdate."""

    # directive: activity-dashboard-solid | # see activity-dashboard-solid.C11
    def test_default_is_now_when_missing(self):
        M = TranscodeProgressModel(TranscodeAttemptId=42)
        self.assertIsNotNone(M.LastProgressUpdate)
        self.assertLessEqual((datetime.now(timezone.utc).replace(tzinfo=None) - M.LastProgressUpdate.replace(tzinfo=None)).total_seconds(), 5)


# directive: activity-dashboard-solid | # see activity-dashboard-solid.C4
class TestWorkerStatusAcceptedValues(unittest.TestCase):
    """AC4: Workers.Status renderer falls back gracefully; live values must be non-null."""

    # directive: activity-dashboard-solid | # see activity-dashboard-solid.C4
    def test_live_status_values_are_non_null(self):
        Db = DatabaseService()
        Rows = Db.ExecuteQuery("SELECT DISTINCT Status FROM Workers")
        self.assertIsInstance(Rows, list)
        for R in Rows:
            self.assertIsNotNone(R.get('Status'))


# directive: activity-dashboard-solid | # see activity-dashboard-solid.C3
class TestActiveJobsDecoupledFromWorkerStatus(unittest.TestCase):
    """AC3: ActiveJobRow carries WorkerName for display only -- NEVER Worker.Status."""

    # directive: activity-dashboard-solid | # see activity-dashboard-solid.C3
    def test_active_jobs_row_dataclass_does_not_carry_worker_status(self):
        Row = ActiveJobRow(
            AttemptId=1, MediaFileId=1, FileName='x.mkv', WorkerName='paused-worker',
            ProfileName='p', SizeMB=1.0, ProgressPercent=50,
            SmoothedFPS=10.0, SmoothedSpeed=1.0, EtaSeconds=10,
        )
        self.assertEqual(Row.WorkerName, 'paused-worker')
        self.assertFalse(hasattr(Row, 'WorkerStatus'))


if __name__ == '__main__':
    unittest.main()
