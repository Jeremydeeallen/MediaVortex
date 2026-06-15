import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.ServiceControl.StuckJobDetectionService import StuckJobDetectionService


def _svc():
    DbManager = MagicMock()
    Svc = StuckJobDetectionService(DbManager)
    Svc.WorkersRepository = MagicMock()
    return Svc


# directive: pause-not-stale | # see pause-not-stale.C1
class TestPausedWorkerIsNotStale(unittest.TestCase):
    """AC1+AC2: Paused workers are alive; only heartbeat-age determines staleness."""

    # directive: pause-not-stale | # see pause-not-stale.C1
    def test_paused_with_fresh_heartbeat_is_not_offline(self):
        Svc = _svc()
        Svc.WorkersRepository.GetWorkerConfig.return_value = {
            'LastHeartbeat': datetime.now(timezone.utc),
            'Status': 'Paused',
        }
        Offline, Reason = Svc._IsWorkerOffline('dot-worker-1')
        self.assertFalse(Offline, f"Paused + fresh heartbeat should NOT be offline; got reason={Reason}")

    # directive: pause-not-stale | # see pause-not-stale.C2
    def test_paused_with_stale_heartbeat_is_offline(self):
        Svc = _svc()
        Svc.WorkersRepository.GetWorkerConfig.return_value = {
            'LastHeartbeat': datetime.now(timezone.utc) - timedelta(minutes=10),
            'Status': 'Paused',
        }
        Offline, Reason = Svc._IsWorkerOffline('dot-worker-1')
        self.assertTrue(Offline, "Paused + stale heartbeat (>threshold) SHOULD be offline")
        self.assertIn('minutes ago', Reason)

    # directive: pause-not-stale | # see pause-not-stale.C1
    def test_online_with_fresh_heartbeat_is_not_offline(self):
        Svc = _svc()
        Svc.WorkersRepository.GetWorkerConfig.return_value = {
            'LastHeartbeat': datetime.now(timezone.utc),
            'Status': 'Online',
        }
        Offline, _ = Svc._IsWorkerOffline('dot-worker-1')
        self.assertFalse(Offline)

    # directive: pause-not-stale | # see pause-not-stale.C2
    def test_online_with_stale_heartbeat_is_offline(self):
        Svc = _svc()
        Svc.WorkersRepository.GetWorkerConfig.return_value = {
            'LastHeartbeat': datetime.now(timezone.utc) - timedelta(minutes=10),
            'Status': 'Online',
        }
        Offline, _ = Svc._IsWorkerOffline('dot-worker-1')
        self.assertTrue(Offline)

    # directive: pause-not-stale | # see pause-not-stale.C3
    def test_no_heartbeat_recorded_is_not_offline(self):
        Svc = _svc()
        Svc.WorkersRepository.GetWorkerConfig.return_value = {
            'LastHeartbeat': None,
            'Status': 'Paused',
        }
        Offline, Reason = Svc._IsWorkerOffline('new-worker')
        self.assertFalse(Offline)
        self.assertIn('No heartbeat', Reason)


if __name__ == '__main__':
    unittest.main()
