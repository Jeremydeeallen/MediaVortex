import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from WorkerService.LanguageWorker import LanguageWorker
from Features.AudioNormalization.Services.LanguageEnrichmentError import LanguageEnrichmentError


def _MakeRow(Id, RelativePath='series/ep.mp4', StorageRootId=1):
    return {'id': Id, 'storagerootid': StorageRootId, 'relativepath': RelativePath, 'filename': 'ep.mp4'}


# directive: audio-language-detection C6
class TestLanguageWorkerActiveJobs(unittest.TestCase):

    def _MakeWorker(self, Service=None, InsertReturnsId=99):
        Service = Service or MagicMock()
        Settings = MagicMock()
        Db = MagicMock()
        Db.ExecuteQuery.return_value = [{'id': InsertReturnsId}]
        return LanguageWorker('test-worker', Service=Service, SettingsRepo=Settings, Db=Db)

    def test_active_job_created_and_deleted_on_success(self):
        Service = MagicMock()
        Worker = self._MakeWorker(Service=Service, InsertReturnsId=777)
        with patch('WorkerService.LanguageWorker.CorePath') as MockPath, \
             patch('WorkerService.LanguageWorker.CoreWorker'), \
             patch('WorkerService.LanguageWorker.LocalExists', return_value=True):
            MockPath.return_value.Resolve.return_value = '/tmp/x.mp4'
            Worker._ProcessOne(_MakeRow(42))
        InsertSql = Worker.Db.ExecuteQuery.call_args.args[0]
        self.assertIn('INSERT INTO ActiveJobs', InsertSql)
        self.assertIn("'LanguageService'", InsertSql)
        DeleteCall = Worker.Db.ExecuteNonQuery.call_args
        self.assertIn('DELETE FROM ActiveJobs', DeleteCall.args[0])
        self.assertEqual(DeleteCall.args[1], (777,))

    def test_active_job_deleted_on_service_failure(self):
        Service = MagicMock()
        Service.EnrichAndStamp.side_effect = LanguageEnrichmentError(42, 'ffmpeg_returncode_nonzero')
        Worker = self._MakeWorker(Service=Service, InsertReturnsId=888)
        with patch('WorkerService.LanguageWorker.CorePath') as MockPath, \
             patch('WorkerService.LanguageWorker.CoreWorker'), \
             patch('WorkerService.LanguageWorker.LocalExists', return_value=True):
            MockPath.return_value.Resolve.return_value = '/tmp/x.mp4'
            Worker._ProcessOne(_MakeRow(42))
        DeleteCall = Worker.Db.ExecuteNonQuery.call_args
        self.assertIn('DELETE FROM ActiveJobs', DeleteCall.args[0])
        self.assertEqual(DeleteCall.args[1], (888,))


if __name__ == '__main__':
    unittest.main()
