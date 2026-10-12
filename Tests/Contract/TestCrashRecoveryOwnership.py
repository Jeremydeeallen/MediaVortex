# directive: crash-recovery-audiofix-type | # see workerservice.ST5
import ast
import os
import unittest
from pathlib import Path
from unittest import mock

import psycopg2.extras

from Core.Database.DatabaseService import DatabaseService
from Features.ServiceControl.CrashRecoveryService import CrashRecoveryService

REPO_ROOT = Path(__file__).resolve().parents[2]
SELF = '_test-crashrec-self'
OTHER = '_test-crashrec-other'


# directive: crash-recovery-audiofix-type | # see workerservice.ST5
class _TransactionDb:
    """DatabaseService stand-in bound to one connection; nothing it writes is committed, so live workers never see the rows."""

    # directive: crash-recovery-audiofix-type | # see workerservice.ST5
    def __init__(self):
        self.Real = DatabaseService()
        self.Connection = self.Real.GetConnection()

    # directive: crash-recovery-audiofix-type | # see workerservice.ST5
    def ExecuteNonQuery(self, Query, Parameters=()):
        Cursor = self.Connection.cursor()
        Cursor.execute(Query, Parameters)
        return Cursor.rowcount

    # directive: crash-recovery-audiofix-type | # see workerservice.ST5
    def ExecuteQuery(self, Query, Parameters=()):
        Cursor = self.Connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        Cursor.execute(Query, Parameters)
        return [dict(Row) for Row in Cursor.fetchall()]

    # directive: crash-recovery-audiofix-type | # see workerservice.ST5
    def Close(self):
        self.Connection.rollback()
        self.Real.CloseConnection(self.Connection)


# directive: crash-recovery-audiofix-type | # see workerservice.ST5
class _Manager:

    # directive: crash-recovery-audiofix-type | # see workerservice.ST5
    def __init__(self, Db):
        self.DatabaseService = Db


# directive: crash-recovery-audiofix-type | # see workerservice.ST5
class _ActiveJobs:

    # directive: crash-recovery-audiofix-type | # see workerservice.ST5
    def __init__(self, Rows):
        self.Rows = Rows

    # directive: crash-recovery-audiofix-type | # see workerservice.ST5
    def GetActiveJobsByService(self, Query):
        return self.Rows


# directive: crash-recovery-audiofix-type | # see workerservice.ST5
class _FailingDb:

    # directive: crash-recovery-audiofix-type | # see workerservice.ST5
    def ExecuteNonQuery(self, Query, Parameters=()):
        raise RuntimeError("database write failed")


# directive: crash-recovery-audiofix-type | # see workerservice.ST5
class TestCrashRecoveryOwnership(unittest.TestCase):

    # directive: crash-recovery-audiofix-type | # see workerservice.ST5
    def setUp(self):
        self.Db = _TransactionDb()
        self.addCleanup(self.Db.Close)

    # directive: crash-recovery-audiofix-type | # see workerservice.ST5
    def _Seed(self, Mode, Owner, WithAttempt=True, AwaitingQualityTest=False):
        FileName = f'_test-crashrec-{Mode}-{Owner}.mkv'
        self.Db.ExecuteNonQuery("INSERT INTO MediaFiles (FileName) VALUES (%s)", (FileName,))
        Mfid = self.Db.ExecuteQuery("SELECT Id FROM MediaFiles WHERE FileName = %s", (FileName,))[0]['id']
        self.Db.ExecuteNonQuery(
            "INSERT INTO TranscodeQueue (FileName, Directory, SizeBytes, SizeMB, Status, ProcessingMode, ClaimedBy, ClaimedAt, DateStarted, MediaFileId) "
            "VALUES (%s, '_test', 1, 1, 'Running', %s, %s, NOW(), NOW(), %s)",
            (FileName, Mode, Owner, Mfid),
        )
        QueueId = self.Db.ExecuteQuery("SELECT Id FROM TranscodeQueue WHERE MediaFileId = %s", (Mfid,))[0]['id']
        AttemptId = None
        if WithAttempt:
            self.Db.ExecuteNonQuery(
                "INSERT INTO TranscodeAttempts (MediaFileId, WorkerName, AttemptDate, Success, ProfileName) "
                "VALUES (%s, %s, NOW(), NULL, 'test-profile')",
                (Mfid, Owner),
            )
            AttemptId = self.Db.ExecuteQuery("SELECT Id FROM TranscodeAttempts WHERE MediaFileId = %s", (Mfid,))[0]['id']
            self.Db.ExecuteNonQuery("INSERT INTO TranscodeProgress (TranscodeAttemptId, PassNumber, PassType) VALUES (%s, 1, 'test')", (AttemptId,))
            if AwaitingQualityTest:
                self.Db.ExecuteNonQuery("INSERT INTO QualityTestingQueue (TranscodeAttemptId, Status) VALUES (%s, 'Pending')", (AttemptId,))
        return QueueId, AttemptId

    # directive: crash-recovery-audiofix-type | # see workerservice.ST5
    def _Recover(self, ActiveJobRows=()):
        Service = CrashRecoveryService(_Manager(self.Db), WorkerName=SELF, ActiveJobRepositoryInstance=_ActiveJobs(list(ActiveJobRows)))
        with mock.patch.object(Service, '_RecoverInProgressArtifacts', return_value=(0, 0)), mock.patch.object(Service, '_SweepLocalStagingOrphans', return_value=0):
            return Service.RecoverOwnedJobs()

    # directive: crash-recovery-audiofix-type | # see workerservice.ST5
    def _Queue(self, QueueId):
        return self.Db.ExecuteQuery("SELECT Status, ClaimedBy, ClaimedAt, DateStarted FROM TranscodeQueue WHERE Id = %s", (QueueId,))[0]

    # directive: crash-recovery-audiofix-type | # see workerservice.ST5
    def _Attempt(self, AttemptId):
        return self.Db.ExecuteQuery("SELECT Success, ErrorMessage, FailureClass FROM TranscodeAttempts WHERE Id = %s", (AttemptId,))[0]

    # directive: crash-recovery-audiofix-type | # see workerservice.ST5
    def _ProgressCount(self, AttemptId):
        return self.Db.ExecuteQuery("SELECT COUNT(*) AS n FROM TranscodeProgress WHERE TranscodeAttemptId = %s", (AttemptId,))[0]['n']

    # directive: crash-recovery-audiofix-type | # see workerservice.ST5
    def test_every_processing_mode_is_released(self):
        Modes = [Row['name'] for Row in self.Db.ExecuteQuery("SELECT Name FROM ProcessingModes")]
        self.assertIn('AudioFix', Modes)
        Seeded = {Mode: self._Seed(Mode, SELF) for Mode in Modes}
        ActiveJobRows = [{'Id': 1, 'JobType': Mode, 'QueueId': Ids[0], 'ProcessId': os.getpid()} for Mode, Ids in Seeded.items()]
        self._Recover(ActiveJobRows)
        for Mode, (QueueId, AttemptId) in Seeded.items():
            with self.subTest(Mode=Mode):
                Queue = self._Queue(QueueId)
                self.assertEqual(Queue['status'], 'Pending')
                self.assertIsNone(Queue['claimedby'])
                self.assertIsNone(Queue['claimedat'])
                self.assertIsNone(Queue['datestarted'])
                Attempt = self._Attempt(AttemptId)
                self.assertIs(Attempt['success'], False)
                self.assertEqual(Attempt['errormessage'], 'worker crashed/restarted')
                self.assertIsNotNone(Attempt['failureclass'])
                self.assertEqual(self._ProgressCount(AttemptId), 0)

    # directive: crash-recovery-audiofix-type | # see workerservice.ST5
    def test_job_with_no_active_job_record_is_released(self):
        ClaimedOnly, _ = self._Seed('AudioFix', SELF, WithAttempt=False)
        WithAttempt, AttemptId = self._Seed('Remux', SELF)
        self._Recover(ActiveJobRows=())
        self.assertEqual(self._Queue(ClaimedOnly)['status'], 'Pending')
        self.assertEqual(self._Queue(WithAttempt)['status'], 'Pending')
        self.assertIs(self._Attempt(AttemptId)['success'], False)

    # directive: crash-recovery-audiofix-type | # see workerservice.ST5
    def test_other_workers_job_is_untouched(self):
        QueueId, AttemptId = self._Seed('AudioFix', OTHER)
        self._Recover()
        Queue = self._Queue(QueueId)
        self.assertEqual(Queue['status'], 'Running')
        self.assertEqual(Queue['claimedby'], OTHER)
        Attempt = self._Attempt(AttemptId)
        self.assertIsNone(Attempt['success'])
        self.assertIsNone(Attempt['errormessage'])
        self.assertEqual(self._ProgressCount(AttemptId), 1)

    # directive: crash-recovery-audiofix-type | # see workerservice.ST5
    def test_attempt_awaiting_quality_test_is_kept(self):
        QueueId, AttemptId = self._Seed('Transcode', SELF, AwaitingQualityTest=True)
        self._Recover()
        self.assertIsNone(self._Attempt(AttemptId)['success'])
        self.assertEqual(self._Queue(QueueId)['status'], 'Running')
        self.assertEqual(self._ProgressCount(AttemptId), 1)

    # directive: crash-recovery-audiofix-type | # see workerservice.ST5
    def test_database_failure_propagates(self):
        Service = CrashRecoveryService(_Manager(_FailingDb()), WorkerName=SELF, ActiveJobRepositoryInstance=_ActiveJobs([]))
        with self.assertRaises(RuntimeError):
            Service.RecoverOwnedJobs()

    # directive: crash-recovery-audiofix-type | # see workerservice.ST5
    def test_worker_name_is_required(self):
        with self.assertRaises(ValueError):
            CrashRecoveryService(_Manager(_FailingDb()), WorkerName=None)

    # directive: crash-recovery-audiofix-type | # see workerservice.ST5
    def test_failed_recovery_stops_the_boot(self):
        Source = (REPO_ROOT / 'WorkerService' / 'Main.py').read_text(encoding='utf-8')
        Functions = {Node.name: Node for Node in ast.walk(ast.parse(Source)) if isinstance(Node, ast.FunctionDef)}
        Handlers = [Node for Node in ast.walk(Functions['_RecoverFromCrash']) if isinstance(Node, ast.Try)]
        self.assertEqual(Handlers, [], "_RecoverFromCrash must not catch a recovery failure")
        self.assertIn("if not App.Run():\n            sys.exit(1)", Source)


if __name__ == '__main__':
    unittest.main()
