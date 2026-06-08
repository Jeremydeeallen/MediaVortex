import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path as _PathLib

sys.path.insert(0, str(_PathLib(__file__).resolve().parent.parent.parent))

from Core.Database.DatabaseService import DatabaseService, EscapeLikePattern
from Features.TranscodeJob.LocalStagingService import LocalStagingService
from Features.TranscodeJob.LocalStagingConfigRepository import LocalStagingConfigRepository
from Features.Workers.WorkersRepository import WorkersRepository


SENTINEL = "_lst_test_"
WORKER_A = SENTINEL + "worker_a"


def _Cleanup(Db):
    SafePrefix = EscapeLikePattern(SENTINEL) + "%"
    Db.ExecuteNonQuery("DELETE FROM Workers WHERE WorkerName LIKE %s ESCAPE '!'", (SafePrefix,))


def _InsertWorker(Db, Name, ScratchDir, Enabled, VmafFirst):
    Db.ExecuteNonQuery("INSERT INTO Workers (WorkerName, Platform, Status, TranscodeEnabled, QualityTestEnabled, RemuxEnabled, ScanEnabled, Enabled, AcceptsInterlaced, LocalScratchDir, LocalStagingEnabled, LocalVmafFirst, LastHeartbeat) VALUES (%s, 'linux', 'Online', TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, %s, %s, %s, NOW())", (Name, ScratchDir, Enabled, VmafFirst))


class TestLocalStagingConfigDefault(unittest.TestCase):
    def test_post_migration_default_is_500mb(self):
        Repo = LocalStagingConfigRepository()
        Cfg = Repo.Get()
        self.assertEqual(Cfg.get('MinSizeMB'), 500, "Default MinSizeMB must be 500 per directive C1")


class TestShouldStageTruthTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.Db = DatabaseService()
        cls.Tmp = tempfile.mkdtemp(prefix='lst_truth_')
        _Cleanup(cls.Db)
        _InsertWorker(cls.Db, WORKER_A, None, False, False)

    @classmethod
    def tearDownClass(cls):
        _Cleanup(cls.Db)
        if os.path.exists(cls.Tmp):
            shutil.rmtree(cls.Tmp, ignore_errors=True)

    def test_disabled_off_returns_false(self):
        Db = self.Db
        Db.ExecuteNonQuery("UPDATE Workers SET LocalStagingEnabled=FALSE, LocalScratchDir=%s WHERE WorkerName=%s", (self.Tmp, WORKER_A))
        S = LocalStagingService(Db)
        self.assertFalse(S.ShouldStage(WORKER_A, 600))

    def test_enabled_but_no_scratch_dir_returns_false(self):
        Db = self.Db
        Db.ExecuteNonQuery("UPDATE Workers SET LocalStagingEnabled=TRUE, LocalScratchDir=NULL WHERE WorkerName=%s", (WORKER_A,))
        S = LocalStagingService(Db)
        self.assertFalse(S.ShouldStage(WORKER_A, 600))

    def test_enabled_with_scratch_below_floor_returns_false(self):
        Db = self.Db
        Db.ExecuteNonQuery("UPDATE Workers SET LocalStagingEnabled=TRUE, LocalScratchDir=%s WHERE WorkerName=%s", (self.Tmp, WORKER_A))
        S = LocalStagingService(Db)
        self.assertFalse(S.ShouldStage(WORKER_A, 100), "100 MB < default 500 MB floor -> no staging")

    def test_enabled_with_scratch_at_or_above_floor_returns_true(self):
        Db = self.Db
        Db.ExecuteNonQuery("UPDATE Workers SET LocalStagingEnabled=TRUE, LocalScratchDir=%s WHERE WorkerName=%s", (self.Tmp, WORKER_A))
        S = LocalStagingService(Db)
        self.assertTrue(S.ShouldStage(WORKER_A, 500))
        self.assertTrue(S.ShouldStage(WORKER_A, 5000))

    def test_mid_flight_floor_change_honored(self):
        Db = self.Db
        Db.ExecuteNonQuery("UPDATE Workers SET LocalStagingEnabled=TRUE, LocalScratchDir=%s WHERE WorkerName=%s", (self.Tmp, WORKER_A))
        Cfg = LocalStagingConfigRepository(Db)
        Original = Cfg.Get().get('MinSizeMB')
        try:
            self.assertTrue(Cfg.Update(MinSizeMB=2000))
            S = LocalStagingService(Db)
            self.assertFalse(S.ShouldStage(WORKER_A, 1000), "1000 MB < new 2000 MB floor -> no staging")
            self.assertTrue(S.ShouldStage(WORKER_A, 2500), "2500 MB >= 2000 MB floor -> stage")
        finally:
            Cfg.Update(MinSizeMB=Original)


class TestStageSourceRoundTrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.Db = DatabaseService()
        cls.SrcDir = tempfile.mkdtemp(prefix='lst_src_')
        cls.ScratchDir = tempfile.mkdtemp(prefix='lst_scratch_')
        cls.SrcFile = os.path.join(cls.SrcDir, 'sample.mkv')
        with open(cls.SrcFile, 'wb') as F:
            F.write(b'mediavortex-test-data' * 1000)
        _Cleanup(cls.Db)
        _InsertWorker(cls.Db, WORKER_A, cls.ScratchDir, True, False)

    @classmethod
    def tearDownClass(cls):
        _Cleanup(cls.Db)
        for D in (cls.SrcDir, cls.ScratchDir):
            if os.path.exists(D):
                shutil.rmtree(D, ignore_errors=True)

    def test_stage_source_copies_to_per_job_subdir_and_size_matches(self):
        S = LocalStagingService(self.Db)
        MediaFileId = 999001
        Staged = S.StageSource(WORKER_A, MediaFileId, self.SrcFile)
        self.assertIsNotNone(Staged)
        self.assertTrue(os.path.exists(Staged))
        self.assertEqual(os.path.getsize(Staged), os.path.getsize(self.SrcFile))
        self.assertEqual(os.path.basename(Staged), 'sample.mkv')
        self.assertIn(str(MediaFileId), Staged)
        S.CleanupJobScratchDir(WORKER_A, MediaFileId)
        self.assertFalse(os.path.exists(Staged))

    def test_resolve_local_output_path_lands_in_per_job_subdir(self):
        S = LocalStagingService(self.Db)
        MediaFileId = 999002
        OutPath = S.ResolveLocalOutputPath(WORKER_A, MediaFileId, 'sample-mv.mp4.inprogress')
        self.assertIsNotNone(OutPath)
        self.assertIn(str(MediaFileId), OutPath)
        self.assertTrue(OutPath.endswith('sample-mv.mp4.inprogress'))


class TestCleanupIdempotency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.Db = DatabaseService()
        cls.ScratchDir = tempfile.mkdtemp(prefix='lst_cleanup_')
        _Cleanup(cls.Db)
        _InsertWorker(cls.Db, WORKER_A, cls.ScratchDir, True, False)

    @classmethod
    def tearDownClass(cls):
        _Cleanup(cls.Db)
        if os.path.exists(cls.ScratchDir):
            shutil.rmtree(cls.ScratchDir, ignore_errors=True)

    def test_cleanup_on_existing_file_succeeds(self):
        S = LocalStagingService(self.Db)
        F = tempfile.NamedTemporaryFile(delete=False, dir=self.ScratchDir, suffix='.inprogress').name
        self.assertTrue(S.Cleanup(F))
        self.assertFalse(os.path.exists(F))

    def test_cleanup_on_nonexistent_path_returns_true(self):
        S = LocalStagingService(self.Db)
        self.assertTrue(S.Cleanup(os.path.join(self.ScratchDir, 'never_existed.inprogress')))

    def test_cleanup_on_none_returns_true(self):
        S = LocalStagingService(self.Db)
        self.assertTrue(S.Cleanup(None))


class TestIsLocalVmafFirstGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.Db = DatabaseService()
        _Cleanup(cls.Db)
        _InsertWorker(cls.Db, WORKER_A, '/tmp/lst', True, False)

    @classmethod
    def tearDownClass(cls):
        _Cleanup(cls.Db)

    def test_off_when_lvf_false(self):
        self.Db.ExecuteNonQuery("UPDATE Workers SET LocalVmafFirst=FALSE, QualityTestEnabled=TRUE WHERE WorkerName=%s", (WORKER_A,))
        S = LocalStagingService(self.Db)
        self.assertFalse(S.IsLocalVmafFirst(WORKER_A))

    def test_off_when_qt_disabled_even_with_lvf_true(self):
        self.Db.ExecuteNonQuery("UPDATE Workers SET LocalVmafFirst=TRUE, QualityTestEnabled=FALSE WHERE WorkerName=%s", (WORKER_A,))
        S = LocalStagingService(self.Db)
        self.assertFalse(S.IsLocalVmafFirst(WORKER_A))

    def test_on_when_both_true(self):
        self.Db.ExecuteNonQuery("UPDATE Workers SET LocalVmafFirst=TRUE, QualityTestEnabled=TRUE WHERE WorkerName=%s", (WORKER_A,))
        S = LocalStagingService(self.Db)
        self.assertTrue(S.IsLocalVmafFirst(WORKER_A))


class TestWorkersRepositoryStagingMethods(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.Db = DatabaseService()
        cls.Repo = WorkersRepository(cls.Db)
        _Cleanup(cls.Db)
        _InsertWorker(cls.Db, WORKER_A, None, False, False)

    @classmethod
    def tearDownClass(cls):
        _Cleanup(cls.Db)

    def test_update_and_get_round_trip(self):
        self.assertTrue(self.Repo.UpdateWorkerLocalStaging(WORKER_A, '/tmp/scratch_x', True, True))
        Cfg = self.Repo.GetWorkerLocalStagingConfig(WORKER_A)
        self.assertEqual(Cfg.get('LocalScratchDir'), '/tmp/scratch_x')
        self.assertTrue(Cfg.get('LocalStagingEnabled'))
        self.assertTrue(Cfg.get('LocalVmafFirst'))

    def test_clear_sets_null_path(self):
        self.assertTrue(self.Repo.UpdateWorkerLocalStaging(WORKER_A, None, False, False))
        Cfg = self.Repo.GetWorkerLocalStagingConfig(WORKER_A)
        self.assertIsNone(Cfg.get('LocalScratchDir'))
        self.assertFalse(Cfg.get('LocalStagingEnabled'))
        self.assertFalse(Cfg.get('LocalVmafFirst'))


if __name__ == '__main__':
    unittest.main()
