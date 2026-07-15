import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.ServiceControl.PhaseDetectors.SetupPhaseDetector import SetupPhaseDetector
from Features.ServiceControl.PhaseDetectors.PreEncodePhaseDetector import PreEncodePhaseDetector
from Features.ServiceControl.PhaseDetectors.EncodingPhaseDetector import EncodingPhaseDetector
from Features.ServiceControl.PhaseDetectors.PostEncodePhaseDetector import PostEncodePhaseDetector
from Features.ServiceControl.PhaseDetectors.VerifyingPhaseDetector import VerifyingPhaseDetector


# directive: transcode-flow-canonical
def _FakeSettingsFactory(Value):
    Repo = MagicMock()
    Repo.GetSystemSetting = MagicMock(return_value=Value)
    return lambda: Repo


class SetupPhaseDetectorTest(unittest.TestCase):

    def test_fresh_setup_returns_not_stuck(self):
        Detector = SetupPhaseDetector(_FakeSettingsFactory(30))
        Stuck, Reason = Detector.Detect(None, None, datetime.now(timezone.utc) - timedelta(minutes=5))
        self.assertFalse(Stuck)
        self.assertIn('in-progress', Reason)

    def test_setup_over_timeout_returns_stuck(self):
        Detector = SetupPhaseDetector(_FakeSettingsFactory(30))
        Stuck, Reason = Detector.Detect(None, None, datetime.now(timezone.utc) - timedelta(minutes=31))
        self.assertTrue(Stuck)
        self.assertIn('Setup phase stuck', Reason)

    def test_setup_at_25min_below_default_30(self):
        Detector = SetupPhaseDetector(_FakeSettingsFactory(None))
        Stuck, _ = Detector.Detect(None, None, datetime.now(timezone.utc) - timedelta(minutes=25))
        self.assertFalse(Stuck)


class PreEncodePhaseDetectorTest(unittest.TestCase):

    def test_fresh_preencode_returns_not_stuck(self):
        Detector = PreEncodePhaseDetector(_FakeSettingsFactory(20))
        Stuck, Reason = Detector.Detect(None, None, datetime.now(timezone.utc) - timedelta(minutes=8))
        self.assertFalse(Stuck)
        self.assertIn('in-progress', Reason)

    def test_preencode_over_timeout_returns_stuck(self):
        Detector = PreEncodePhaseDetector(_FakeSettingsFactory(20))
        Stuck, Reason = Detector.Detect(None, None, datetime.now(timezone.utc) - timedelta(minutes=21))
        self.assertTrue(Stuck)
        self.assertIn('PreEncode phase stuck', Reason)

    def test_preencode_default_20_min(self):
        Detector = PreEncodePhaseDetector(_FakeSettingsFactory(None))
        Stuck, _ = Detector.Detect(None, None, datetime.now(timezone.utc) - timedelta(minutes=15))
        self.assertFalse(Stuck)


class PostEncodePhaseDetectorTest(unittest.TestCase):

    def test_fresh_postencode_returns_not_stuck(self):
        Detector = PostEncodePhaseDetector(_FakeSettingsFactory(15))
        Stuck, _ = Detector.Detect(None, None, datetime.now(timezone.utc) - timedelta(minutes=3))
        self.assertFalse(Stuck)

    def test_postencode_over_timeout_returns_stuck(self):
        Detector = PostEncodePhaseDetector(_FakeSettingsFactory(15))
        Stuck, Reason = Detector.Detect(None, None, datetime.now(timezone.utc) - timedelta(minutes=16))
        self.assertTrue(Stuck)
        self.assertIn('PostEncode phase stuck', Reason)


class VerifyingPhaseDetectorTest(unittest.TestCase):

    def test_fresh_verifying_returns_not_stuck(self):
        Detector = VerifyingPhaseDetector(_FakeSettingsFactory(30))
        Stuck, _ = Detector.Detect(None, None, datetime.now(timezone.utc) - timedelta(minutes=10))
        self.assertFalse(Stuck)

    def test_verifying_over_timeout_returns_stuck(self):
        Detector = VerifyingPhaseDetector(_FakeSettingsFactory(30))
        Stuck, Reason = Detector.Detect(None, None, datetime.now(timezone.utc) - timedelta(minutes=31))
        self.assertTrue(Stuck)
        self.assertIn('Verifying phase stuck', Reason)


class EncodingPhaseDetectorTest(unittest.TestCase):

    # directive: transcode-flow-canonical
    def _MakeDetector(self, ProgressRow, PidName='ffmpeg', PidAlive=True):
        DbManager = MagicMock()
        DbManager.DatabaseService.ExecuteQuery.return_value = [ProgressRow] if ProgressRow else []
        Inspector = MagicMock()
        Inspector.GetProcessName.return_value = PidName if PidAlive else None
        Inspector.IsFFmpegProcessName.return_value = PidName in ('ffmpeg', 'ffmpeg.exe', 'cmd.exe', 'sh')
        Detector = EncodingPhaseDetector(
            DatabaseManager=DbManager,
            ProcessInspector=Inspector,
            SystemSettingsRepositoryFactory=_FakeSettingsFactory(5),
            LocalHostnameFn=lambda: 'wakko-worker-1',
        )
        return Detector

    # directive: transcode-flow-canonical
    def _MakeJob(self):
        Job = MagicMock()
        Job.Id = 42
        Job.StorageRootId = 1
        Job.RelativePath = 'x/y.mkv'
        return Job

    def test_fresh_frame_advance_returns_not_stuck(self):
        Detector = self._MakeDetector({
            'CurrentFrame': 1234,
            'LastFrameAdvance': datetime.now(timezone.utc) - timedelta(seconds=15),
            'ProgressPercent': 30.0,
            'CurrentFPS': 45.0,
        })
        Stuck, _ = Detector.Detect(self._MakeJob(), {'FFmpegPid': 100, 'WorkerName': 'wakko-worker-1'}, None)
        self.assertFalse(Stuck)

    def test_stale_frame_advance_returns_stuck(self):
        Detector = self._MakeDetector({
            'CurrentFrame': 1234,
            'LastFrameAdvance': datetime.now(timezone.utc) - timedelta(minutes=6),
            'ProgressPercent': 30.0,
            'CurrentFPS': 0.0,
        })
        Stuck, Reason = Detector.Detect(self._MakeJob(), {'FFmpegPid': 100, 'WorkerName': 'wakko-worker-1'}, None)
        self.assertTrue(Stuck)
        self.assertIn('frozen', Reason.lower())

    def test_no_progress_row_returns_not_stuck(self):
        Detector = self._MakeDetector(None)
        Stuck, _ = Detector.Detect(self._MakeJob(), {'FFmpegPid': None}, None)
        self.assertFalse(Stuck)

    def test_dead_pid_returns_stuck_when_local(self):
        Detector = self._MakeDetector({
            'CurrentFrame': 100,
            'LastFrameAdvance': datetime.now(timezone.utc),
            'ProgressPercent': 5.0,
            'CurrentFPS': 42.0,
        }, PidAlive=False)
        Stuck, Reason = Detector.Detect(self._MakeJob(), {'FFmpegPid': 239858, 'WorkerName': 'wakko-worker-1'}, None)
        self.assertTrue(Stuck)
        self.assertIn('no longer alive', Reason)

    def test_null_ffmpeg_pid_returns_not_stuck(self):
        Detector = self._MakeDetector({
            'CurrentFrame': 100,
            'LastFrameAdvance': datetime.now(timezone.utc),
            'ProgressPercent': 5.0,
            'CurrentFPS': 42.0,
        })
        Stuck, _ = Detector.Detect(self._MakeJob(), {'FFmpegPid': None, 'WorkerName': 'wakko-worker-1'}, None)
        self.assertFalse(Stuck)

    def test_cross_host_pid_check_skipped(self):
        Detector = self._MakeDetector({
            'CurrentFrame': 100,
            'LastFrameAdvance': datetime.now(timezone.utc),
            'ProgressPercent': 5.0,
            'CurrentFPS': 42.0,
        }, PidAlive=False)
        Stuck, _ = Detector.Detect(self._MakeJob(), {'FFmpegPid': 239858, 'WorkerName': 'dot-worker-1'}, None)
        self.assertFalse(Stuck)


if __name__ == '__main__':
    unittest.main()
