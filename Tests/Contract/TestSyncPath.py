import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.Sync.SyncPathController import SyncPathBlueprint


class TestSyncPath(unittest.TestCase):

    def _AppClient(self):
        from flask import Flask
        App = Flask(__name__)
        App.register_blueprint(SyncPathBlueprint)
        return App.test_client()

    def test_missing_body_returns_400(self):
        Response = self._AppClient().post('/api/Sync/Path', json={})
        self.assertEqual(Response.status_code, 400)
        self.assertFalse(Response.get_json()['Success'])

    def test_unknown_storage_root_returns_400(self):
        with patch('Features.Sync.SyncPathController.Path') as PathCls:
            from Core.Path.Path import PathError
            PathCls.FromLegacyString.side_effect = PathError('no root')
            Response = self._AppClient().post('/api/Sync/Path', json={'CanonicalPath': 'ZZZ:\\nowhere\\here'})
            self.assertEqual(Response.status_code, 400)
            self.assertFalse(Response.get_json()['Success'])

    def test_valid_path_enqueues_scan(self):
        with patch('Features.Sync.SyncPathController.Path') as PathCls, \
             patch('Features.Sync.SyncPathController.GetStorageRoots', return_value=[]):
            PathCls.FromLegacyString.return_value = MagicMock(StorageRootId=1, RelativePath='Full Circle (2023)/Season 1')
            with patch('Features.FileScanning.FileScanningBusinessService.FileScanningBusinessService') as FsbsCls:
                FsbsInstance = FsbsCls.return_value
                FsbsInstance.StartScanning.return_value = {'Success': True, 'JobId': 'abc-123'}
                FsbsInstance.CurrentJobId = 'abc-123'
                Response = self._AppClient().post('/api/Sync/Path', json={'CanonicalPath': 'T:\\Full Circle (2023)\\Season 1'})
                self.assertEqual(Response.status_code, 200)
                Data = Response.get_json()
                self.assertTrue(Data['Success'])
                self.assertEqual(Data['ScanJobId'], 'abc-123')


if __name__ == '__main__':
    unittest.main()
