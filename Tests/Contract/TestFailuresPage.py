import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.Failures.FailuresController import FailuresBlueprint
from Features.Failures.FailuresRepository import _IsHousekeepingMessage


class TestHousekeepingFilter(unittest.TestCase):

    def test_housekeeping_messages_flagged(self):
        for Msg in [
            'Application restarted',
            'Zombie scan cleanup',
            'Stopped pre-redeploy',
            'Stuck scan cleaned by StuckJobDetectionService',
            'cleared post-restart',
        ]:
            self.assertTrue(_IsHousekeepingMessage(Msg), f"{Msg!r} should be flagged as housekeeping")

    def test_real_failures_pass_filter(self):
        for Msg in [
            "[Errno 2] No such file or directory: '/mnt/media'",
            'Permission denied',
            'ffprobe crashed',
            'Unknown storage root prefix',
            '',
            None,
        ]:
            self.assertFalse(_IsHousekeepingMessage(Msg), f"{Msg!r} should NOT be flagged as housekeeping")


class TestFailuresEndpoint(unittest.TestCase):

    def _AppClient(self):
        from flask import Flask
        App = Flask(__name__)
        App.register_blueprint(FailuresBlueprint)
        return App.test_client()

    def test_get_failures_returns_probe_and_scan(self):
        with patch('Features.Failures.FailuresController.FailuresRepository') as RepoCls:
            RepoInstance = RepoCls.return_value
            RepoInstance.GetProbeFailures.return_value = [{'id': 1, 'filename': 'x.mkv'}]
            RepoInstance.GetScanFailures.return_value = [{'id': 2, 'jobid': 'abc'}]
            Response = self._AppClient().get('/api/Failures')
            self.assertEqual(Response.status_code, 200)
            Data = Response.get_json()
            self.assertTrue(Data['Success'])
            self.assertEqual(len(Data['Probe']), 1)
            self.assertEqual(len(Data['Scan']), 1)

    def test_retry_probe_resets_state(self):
        with patch('Features.Failures.FailuresController.MediaFilesRepository') as MfrCls:
            MfrInstance = MfrCls.return_value
            MfrInstance.DatabaseService = MagicMock()
            MfrInstance.DatabaseService.ExecuteNonQuery.return_value = 1
            Response = self._AppClient().post('/api/Failures/42/Retry')
            self.assertEqual(Response.status_code, 200)
            self.assertTrue(Response.get_json()['Success'])
            MfrInstance.DatabaseService.ExecuteNonQuery.assert_called_once()
            Sql = MfrInstance.DatabaseService.ExecuteNonQuery.call_args[0][0]
            self.assertIn('FFprobeFailureCount = 0', Sql)
            self.assertIn('NeedsReprobe = TRUE', Sql)

    def test_retry_probe_not_found_returns_404(self):
        with patch('Features.Failures.FailuresController.MediaFilesRepository') as MfrCls:
            MfrInstance = MfrCls.return_value
            MfrInstance.DatabaseService = MagicMock()
            MfrInstance.DatabaseService.ExecuteNonQuery.return_value = 0
            Response = self._AppClient().post('/api/Failures/999999/Retry')
            self.assertEqual(Response.status_code, 404)


if __name__ == '__main__':
    unittest.main()
