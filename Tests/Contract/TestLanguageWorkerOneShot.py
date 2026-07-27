import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from WorkerService.LanguageWorker import LanguageWorker


# directive: audio-language-detection C3
class TestLanguageWorkerOneShot(unittest.TestCase):

    def test_fetch_batch_query_excludes_files_with_detection_row(self):
        Db = MagicMock()
        Db.ExecuteQuery.return_value = []
        Worker = LanguageWorker('test-worker', SettingsRepo=MagicMock(), Db=Db)
        Worker._FetchBatch(50)
        Sql = Db.ExecuteQuery.call_args.args[0]
        self.assertIn('NOT EXISTS', Sql)
        self.assertIn('MediaFileLanguageDetections', Sql)

    def test_fetch_batch_query_uses_capability_gate(self):
        Db = MagicMock()
        Db.ExecuteQuery.return_value = []
        Worker = LanguageWorker('test-worker', SettingsRepo=MagicMock(), Db=Db)
        Worker._FetchBatch(50)
        Sql = Db.ExecuteQuery.call_args.args[0]
        self.assertIn('LanguageEnabled', Sql)
        self.assertIn("Status = 'Online'", Sql)


if __name__ == '__main__':
    unittest.main()
