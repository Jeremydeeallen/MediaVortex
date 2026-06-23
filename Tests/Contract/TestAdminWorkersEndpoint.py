import json
import unittest
import urllib.request
import urllib.error


_BASE = 'http://127.0.0.1:5000'


# directive: activity-admin-and-worker-telemetry
def _Get(Path):
    Req = urllib.request.Request(_BASE + Path, method='GET')
    try:
        with urllib.request.urlopen(Req, timeout=5) as Resp:
            Body = Resp.read()
            try:
                return Resp.status, json.loads(Body)
            except Exception:
                return Resp.status, Body.decode('utf-8', errors='replace')
    except urllib.error.HTTPError as Ex:
        return Ex.code, Ex.read()


# directive: activity-admin-and-worker-telemetry
class TestAdminWorkersEndpoint(unittest.TestCase):

    # directive: activity-admin-and-worker-telemetry
    def test_admin_workers_page_renders(self):
        Status, Body = _Get('/Admin/Workers')
        self.assertEqual(Status, 200)
        self.assertIn('Workers', Body if isinstance(Body, str) else '')

    # directive: activity-admin-and-worker-telemetry
    def test_admin_workers_snapshot_shape(self):
        Status, Body = _Get('/api/Admin/Workers/Snapshot')
        self.assertEqual(Status, 200)
        self.assertTrue(Body.get('Success'))
        Data = Body.get('Data', {})
        self.assertIn('Workers', Data)
        self.assertIn('HeartbeatStaleThresholdSec', Data)
        self.assertIsInstance(Data['Workers'], list)


if __name__ == '__main__':
    unittest.main()
