import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.ServiceControl.ActiveJobRepository import ActiveJobRepository
from Features.ServiceControl.JobPhase import JobPhase


class JobPhaseTransitionsTest(unittest.TestCase):

    def _MakeRepo(self):
        Db = MagicMock()
        Db.ExecuteNonQuery.return_value = 1
        Repo = ActiveJobRepository(DatabaseServiceInstance=Db)
        return Repo, Db

    def test_setphase_setup_writes_phase_and_timestamp(self):
        Repo, Db = self._MakeRepo()
        self.assertTrue(Repo.SetJobPhase(99, JobPhase.Setup))
        Args, _ = Db.ExecuteNonQuery.call_args
        Sql, Params = Args
        self.assertIn("Phase = %s", Sql)
        self.assertIn("PhaseTransitionedAt = NOW()", Sql)
        self.assertEqual(Params[0], 'Setup')
        self.assertEqual(Params[1], 99)
        self.assertNotIn("FFmpegPid = NULL", Sql)

    def test_setphase_encoding_writes_encoding(self):
        Repo, Db = self._MakeRepo()
        Repo.SetJobPhase(99, JobPhase.Encoding)
        Args, _ = Db.ExecuteNonQuery.call_args
        Sql, Params = Args
        self.assertEqual(Params[0], 'Encoding')
        self.assertNotIn("FFmpegPid = NULL", Sql)

    def test_setphase_postencode_clears_ffmpegpid(self):
        Repo, Db = self._MakeRepo()
        Repo.SetJobPhase(99, JobPhase.PostEncode)
        Args, _ = Db.ExecuteNonQuery.call_args
        Sql, Params = Args
        self.assertEqual(Params[0], 'PostEncode')
        self.assertIn("FFmpegPid = NULL", Sql)

    def test_setphase_verifying_writes_verifying(self):
        Repo, Db = self._MakeRepo()
        Repo.SetJobPhase(99, JobPhase.Verifying)
        Args, _ = Db.ExecuteNonQuery.call_args
        _, Params = Args
        self.assertEqual(Params[0], 'Verifying')

    def test_getjobphase_returns_none_when_row_missing(self):
        Repo, Db = self._MakeRepo()
        Db.ExecuteQuery.return_value = []
        self.assertIsNone(Repo.GetJobPhase(999))

    def test_getjobphase_returns_none_when_phase_null(self):
        Repo, Db = self._MakeRepo()
        Db.ExecuteQuery.return_value = [{'Phase': None, 'PhaseTransitionedAt': None}]
        self.assertIsNone(Repo.GetJobPhase(999))

    def test_getjobphase_returns_enum_and_timestamp(self):
        Repo, Db = self._MakeRepo()
        Db.ExecuteQuery.return_value = [{'Phase': 'Encoding', 'PhaseTransitionedAt': 'ts'}]
        Result = Repo.GetJobPhase(999)
        self.assertIsNotNone(Result)
        Phase, Ts = Result
        self.assertEqual(Phase, JobPhase.Encoding)
        self.assertEqual(Ts, 'ts')

    def test_createactivejob_writes_setup_phase_in_insert(self):
        Repo, Db = self._MakeRepo()
        Db.LastInsertId = 42
        Db.ExecuteNonQuery.return_value = 1
        Result = Repo.CreateActiveJob('TranscodeService', 'Transcode', 999, ProcessId=1, ThreadId=2, WorkerName='wakko-worker-1')
        self.assertEqual(Result, 42)
        Args, _ = Db.ExecuteNonQuery.call_args
        Sql, _ = Args
        self.assertIn("Phase", Sql)
        self.assertIn("'Setup'", Sql)


if __name__ == '__main__':
    unittest.main()
