import re
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from Core.Database.DatabaseService import DatabaseService
from Features.ServiceControl.ActiveJobRepository import ActiveJobRepository

TestWorkerName = '_test-insert-returning-id'
ReturnedId = 4242


# directive: insert-returning-id | # see database-architecture.C15
class TestNoSharedInsertId(unittest.TestCase):

    # directive: insert-returning-id | # see database-architecture.C15
    def test_no_code_reads_an_insert_id_from_shared_state(self):
        Files = subprocess.run(['git', 'ls-files', '*.py'], cwd=REPO_ROOT,
                               capture_output=True, text=True, check=True).stdout.splitlines()
        Pattern = re.compile(r'\b(Get)?' + 'LastInsertId' + r'\b')
        Hits = []
        for Rel in Files:
            if Rel.endswith('TestInsertReturningId.py'):
                continue
            Text = (REPO_ROOT / Rel).read_text(encoding='utf-8', errors='replace')
            Hits += [f'{Rel}:{N}' for N, Line in enumerate(Text.splitlines(), 1) if Pattern.search(Line)]
        self.assertEqual(Hits, [])


# directive: insert-returning-id | # see database-architecture.C15
class TestInsertReturnsItsOwnId(unittest.TestCase):

    # directive: insert-returning-id | # see database-architecture.C15
    def _Db(self):
        Db = MagicMock()
        Db.ExecuteReturning.return_value = [{'Id': ReturnedId}]
        Db.ExecuteQuery.return_value = []
        return Db

    # directive: insert-returning-id | # see database-architecture.C15
    def _AssertReturningInsert(self, Db, Result):
        self.assertEqual(Result, ReturnedId)
        Sql = Db.ExecuteReturning.call_args[0][0]
        self.assertIn('INSERT', Sql)
        self.assertIn('RETURNING Id', Sql)

    # directive: insert-returning-id | # see database-architecture.C15
    def test_active_job(self):
        Db = self._Db()
        self._AssertReturningInsert(Db, ActiveJobRepository(Db).CreateActiveJob('S', 'T', 1, WorkerName=TestWorkerName))

    # directive: insert-returning-id | # see database-architecture.C15
    def test_probe_active_job(self):
        from WorkerService.ProbeWorker import ProbeWorker
        Db = self._Db()
        self._AssertReturningInsert(Db, ProbeWorker(TestWorkerName, SettingsRepo=MagicMock(), Db=Db)._CreateActiveJob(1))

    # directive: insert-returning-id | # see database-architecture.C15
    def test_quality_test_inserts(self):
        from Features.QualityTesting.QualityTestRepository import QualityTestRepository
        for Call in (
            lambda R: R.CreateQualityTestQueueEntry(1, 'o', 'l', 't'),
            lambda R: R.CreateQualityTestResult(1),
            lambda R: R.CreateTemporaryFilePath(1, 1, 'rel'),
        ):
            Db = self._Db()
            Db.ExecuteQuery.return_value = [{'Id': 1}]
            Repo = QualityTestRepository(Db)
            Repo.PrivateValidateTranscodeAttemptId = lambda _Id: True
            Repo.PrivateLogTemporaryFilePathOperation = MagicMock()
            self._AssertReturningInsert(Db, Call(Repo))

    # directive: insert-returning-id | # see database-architecture.C15
    def test_quality_test_progress(self):
        from Features.QualityTesting.QualityTestingBusinessService import QualityTestingBusinessService
        Db = self._Db()
        Svc = QualityTestingBusinessService(SimpleNamespace(DatabaseService=Db), ActiveJobRepositoryInstance=MagicMock(),
                                            SystemSettingsRepositoryInstance=MagicMock())
        self._AssertReturningInsert(Db, Svc.CreateProgressRecord(1, {'TranscodeAttemptId': 1}))

    # directive: insert-returning-id | # see database-architecture.C15
    def test_transcode_progress_first_write(self):
        from Features.TranscodeJob.TranscodeJobRepository import TranscodeJobRepository
        Db = self._Db()
        self._AssertReturningInsert(Db, TranscodeJobRepository(Db).SaveTranscodeProgress(1, 'Encoding', 0.0, 0, 0.0, '', '', ''))


# directive: insert-returning-id | # see database-architecture.C15
class TestConcurrentInsertsGetTheirOwnIds(unittest.TestCase):

    # directive: insert-returning-id | # see database-architecture.C15
    def tearDown(self):
        DatabaseService().ExecuteNonQuery("DELETE FROM ActiveJobs WHERE WorkerName = %s", (TestWorkerName,))

    # directive: insert-returning-id | # see database-architecture.C15
    def test_two_threads_share_one_repository(self):
        Repo = ActiveJobRepository(DatabaseService())
        Results = {0: [], 1: []}

        # directive: insert-returning-id | # see database-architecture.C15
        def _Insert(ThreadNo):
            for I in range(50):
                QueueId = ThreadNo * 1000 + I
                Results[ThreadNo].append((QueueId, Repo.CreateActiveJob('_test', '_test', QueueId, ProcessId=0,
                                                                        ThreadId=threading.get_ident(), WorkerName=TestWorkerName)))

        Threads = [threading.Thread(target=_Insert, args=(N,)) for N in (0, 1)]
        for T in Threads:
            T.start()
        for T in Threads:
            T.join()
        Rows = DatabaseService().ExecuteQuery("SELECT Id, QueueId FROM ActiveJobs WHERE WorkerName = %s", (TestWorkerName,))
        Actual = {R['Id']: R['QueueId'] for R in Rows}
        Pairs = Results[0] + Results[1]
        self.assertEqual(len(Pairs), 100)
        self.assertEqual(len({Id for _Q, Id in Pairs}), 100)
        self.assertEqual([(Q, Id) for Q, Id in Pairs if Actual.get(Id) != Q], [])


if __name__ == '__main__':
    unittest.main()
