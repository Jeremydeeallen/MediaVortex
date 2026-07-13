import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.ServiceControl.StuckJobDetectionService import StuckJobDetectionService
from Features.ServiceControl.JobPhase import JobPhase


# directive: transcode-flow-canonical
def _MakeJob(QueueId=42):
    Job = MagicMock()
    Job.Id = QueueId
    Job.StorageRootId = 1
    Job.RelativePath = 'x/y.mkv'
    return Job


# directive: transcode-flow-canonical
def _MakeService(Phase, TransitionedAt, DetectorResult=(False, 'ok'), ActiveJob=None):
    Svc = StuckJobDetectionService.__new__(StuckJobDetectionService)
    Svc.DatabaseManager = MagicMock()
    Svc.ActiveJobRepository = MagicMock()
    Svc.WorkersRepository = MagicMock()
    Svc.WorkersRepository.GetWorkerConfig.return_value = {'LastHeartbeat': datetime.now(timezone.utc), 'Status': 'Online'}
    Svc.ProcessManagementService = MagicMock()
    ActiveJobRow = ActiveJob or {'Id': 70000, 'QueueId': 42, 'WorkerName': 'wakko-worker-1', 'FFmpegPid': 100, 'ProcessId': 1}
    Svc.ActiveJobRepository.GetActiveJobsByService.return_value = [ActiveJobRow]
    Svc.ActiveJobRepository.GetJobPhase.return_value = (Phase, TransitionedAt)
    Detector = MagicMock()
    Detector.Detect.return_value = DetectorResult
    Registry = MagicMock()
    Registry.GetDetector.return_value = Detector
    Svc.PhaseDetectorRegistry = Registry
    Svc.WORKER_HEARTBEAT_STALE_MINUTES = 5
    return Svc, Detector, Registry


class StuckJobDetectionPhaseAwareTest(unittest.TestCase):

    def test_setup_phase_dispatches_to_setup_detector(self):
        Svc, Detector, Registry = _MakeService(JobPhase.Setup, datetime.now(timezone.utc) - timedelta(minutes=5))
        Stuck, _ = Svc.IsJobStuck(_MakeJob())
        Registry.GetDetector.assert_called_once_with(JobPhase.Setup)
        self.assertFalse(Stuck)

    def test_encoding_phase_dispatches_to_encoding_detector(self):
        Svc, Detector, Registry = _MakeService(JobPhase.Encoding, datetime.now(timezone.utc) - timedelta(minutes=1))
        Svc.IsJobStuck(_MakeJob())
        Registry.GetDetector.assert_called_once_with(JobPhase.Encoding)

    def test_postencode_phase_dispatches_to_postencode_detector(self):
        Svc, Detector, Registry = _MakeService(JobPhase.PostEncode, datetime.now(timezone.utc) - timedelta(minutes=3))
        Svc.IsJobStuck(_MakeJob())
        Registry.GetDetector.assert_called_once_with(JobPhase.PostEncode)

    def test_verifying_phase_dispatches_to_verifying_detector(self):
        Svc, Detector, Registry = _MakeService(JobPhase.Verifying, datetime.now(timezone.utc) - timedelta(minutes=10))
        Svc.IsJobStuck(_MakeJob())
        Registry.GetDetector.assert_called_once_with(JobPhase.Verifying)

    def test_missing_activejob_returns_stuck(self):
        Svc, _, _ = _MakeService(JobPhase.Setup, datetime.now(timezone.utc))
        Svc.ActiveJobRepository.GetActiveJobsByService.return_value = []
        Stuck, Reason = Svc.IsJobStuck(_MakeJob())
        self.assertTrue(Stuck)
        self.assertIn('No ActiveJob', Reason)

    def test_null_phase_returns_not_stuck(self):
        Svc, _, _ = _MakeService(JobPhase.Setup, datetime.now(timezone.utc))
        Svc.ActiveJobRepository.GetJobPhase.return_value = None
        Stuck, Reason = Svc.IsJobStuck(_MakeJob())
        self.assertFalse(Stuck)
        self.assertIn('not yet set', Reason)

    def test_detector_stuck_propagates(self):
        Svc, Detector, _ = _MakeService(JobPhase.Encoding, datetime.now(timezone.utc), DetectorResult=(True, 'frozen'))
        Stuck, Reason = Svc.IsJobStuck(_MakeJob())
        self.assertTrue(Stuck)
        self.assertEqual(Reason, 'frozen')

    def test_worker_offline_returns_stuck_before_phase_dispatch(self):
        Svc, Detector, Registry = _MakeService(JobPhase.Setup, datetime.now(timezone.utc))
        Svc.WorkersRepository.GetWorkerConfig.return_value = {'LastHeartbeat': datetime.now(timezone.utc) - timedelta(minutes=20), 'Status': 'Online'}
        Stuck, Reason = Svc.IsJobStuck(_MakeJob())
        self.assertTrue(Stuck)
        self.assertIn('offline', Reason)
        Registry.GetDetector.assert_not_called()

    # directive: transcode-flow-canonical -- Reset 28 item 6: pre-C21 RuntimeState-based kill path retired
    def test_no_pre_c21_hung_encode_kill_path(self):
        self.assertFalse(
            hasattr(StuckJobDetectionService, 'DetectAndCleanHungEncodes'),
            'DetectAndCleanHungEncodes retired (Reset 28); EncodingPhaseDetector is sole source of truth for Encoding-phase stuck detection.',
        )


if __name__ == '__main__':
    unittest.main()
