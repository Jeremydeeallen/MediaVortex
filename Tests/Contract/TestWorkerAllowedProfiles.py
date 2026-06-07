import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Core.Database.DatabaseService import DatabaseService, EscapeLikePattern
from Core.Database.WorkerCapabilityPredicate import BuildAllowedProfilesPredicate
from Features.Profiles.ProfileRepository import ProfileRepository
from Features.Workers.WorkersRepository import WorkersRepository
from Models.TranscodeProfileModel import TranscodeProfileModel


SENTINEL = "_wr_test_"
WORKER_ONE = SENTINEL + "worker_1"
WORKER_TWO = SENTINEL + "worker_2"
PROFILE_X = SENTINEL + "profile_X"
PROFILE_Y = SENTINEL + "profile_Y"
PROFILE_Z = SENTINEL + "profile_Z"


def _CleanupSentinels(Db):
    SafePrefix = EscapeLikePattern(SENTINEL) + "%"
    Db.ExecuteNonQuery("DELETE FROM Workers WHERE WorkerName LIKE %s ESCAPE '!'", (SafePrefix,))
    Db.ExecuteNonQuery("DELETE FROM ProfileThresholds WHERE ProfileId IN (SELECT Id FROM Profiles WHERE ProfileName LIKE %s ESCAPE '!')", (SafePrefix,))
    Db.ExecuteNonQuery("DELETE FROM Profiles WHERE ProfileName LIKE %s ESCAPE '!'", (SafePrefix,))


def _InsertWorker(Db, Name, AllowedProfiles):
    Db.ExecuteNonQuery("INSERT INTO Workers (WorkerName, Platform, Status, TranscodeEnabled, QualityTestEnabled, RemuxEnabled, ScanEnabled, Enabled, AcceptsInterlaced, AllowedProfiles, LastHeartbeat) VALUES (%s, 'linux', 'Online', TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, %s, NOW())", (Name, AllowedProfiles))


def _InsertProfile(Db, Name):
    Db.ExecuteNonQuery("INSERT INTO Profiles (ProfileName, Description, CreatedDate, LastModified, Codec, Preset, FilmGrain, YadifMode, YadifParity, YadifDeint, UseNvidiaHardware, SortOrder) VALUES (%s, 'sentinel', NOW(), NOW(), 'libsvtav1', 6, 0, 1, 1, 1, 0, 99999)", (Name,))


def _GetWorkerAllowed(Db, Name):
    Rows = Db.ExecuteQuery("SELECT AllowedProfiles FROM Workers WHERE WorkerName = %s", (Name,))
    if not Rows:
        return "MISSING"
    return Rows[0].get('allowedprofiles')


def _GetProfileIdByName(Db, Name):
    Rows = Db.ExecuteQuery("SELECT Id FROM Profiles WHERE ProfileName = %s", (Name,))
    return Rows[0]['id'] if Rows else None


class TestBuildAllowedProfilesPredicate(unittest.TestCase):
    def test_fragment_is_correlated_exists_with_w3_alias(self):
        Frag, Params = BuildAllowedProfilesPredicate(WORKER_ONE)
        self.assertIn("EXISTS", Frag)
        self.assertIn("Workers w3", Frag)
        self.assertIn("AllowedProfiles IS NULL", Frag)
        self.assertIn("mf.AssignedProfile = ANY(string_to_array", Frag)
        self.assertEqual(Params, (WORKER_ONE,))


class TestProfileRenameSweepsWorkerAllowlist(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.Db = DatabaseService()
        cls.Repo = ProfileRepository()
        _CleanupSentinels(cls.Db)
        _InsertProfile(cls.Db, PROFILE_X)
        _InsertProfile(cls.Db, PROFILE_Y)
        _InsertWorker(cls.Db, WORKER_ONE, f"{PROFILE_X},{PROFILE_Y}")
        _InsertWorker(cls.Db, WORKER_TWO, PROFILE_X)

    @classmethod
    def tearDownClass(cls):
        _CleanupSentinels(cls.Db)

    def test_rename_substitutes_old_name_in_csv(self):
        Renamed = PROFILE_X + "_renamed"
        Pid = _GetProfileIdByName(self.Db, PROFILE_X)
        self.assertIsNotNone(Pid)
        Profile = TranscodeProfileModel(Id=Pid, ProfileName=Renamed, Description='sentinel-renamed', CreatedDate=None, LastModified=None, Codec='libsvtav1', Preset=6, FilmGrain=0, YadifMode=1, YadifParity=1, YadifDeint=1, UseNvidiaHardware=0)
        self.Repo.SaveProfile(Profile)
        try:
            One = _GetWorkerAllowed(self.Db, WORKER_ONE) or ''
            self.assertIn(Renamed, One)
            self.assertNotIn(PROFILE_X + ",", One + ",")
            self.assertEqual(_GetWorkerAllowed(self.Db, WORKER_TWO), Renamed)
        finally:
            Profile.ProfileName = PROFILE_X
            self.Repo.SaveProfile(Profile)


class TestProfileDeleteSweepsWorkerAllowlist(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.Db = DatabaseService()
        cls.Repo = ProfileRepository()
        _CleanupSentinels(cls.Db)
        _InsertProfile(cls.Db, PROFILE_X)
        _InsertProfile(cls.Db, PROFILE_Y)
        _InsertWorker(cls.Db, WORKER_ONE, f"{PROFILE_X},{PROFILE_Y}")
        _InsertWorker(cls.Db, WORKER_TWO, PROFILE_X)

    @classmethod
    def tearDownClass(cls):
        _CleanupSentinels(cls.Db)

    def test_delete_removes_name_and_normalizes_single_member_to_empty(self):
        Pid = _GetProfileIdByName(self.Db, PROFILE_X)
        self.Repo.DeleteProfile(Pid)
        self.assertEqual(_GetWorkerAllowed(self.Db, WORKER_ONE), PROFILE_Y)
        self.assertEqual(_GetWorkerAllowed(self.Db, WORKER_TWO), "")


class TestWorkersRepositoryUpdateAndRead(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.Db = DatabaseService()
        cls.Repo = WorkersRepository()
        _CleanupSentinels(cls.Db)
        _InsertWorker(cls.Db, WORKER_ONE, None)

    @classmethod
    def tearDownClass(cls):
        _CleanupSentinels(cls.Db)

    def test_update_persists_csv(self):
        Ok = self.Repo.UpdateWorkerAllowedProfiles(WORKER_ONE, "P1,P2")
        self.assertTrue(Ok)
        self.assertEqual(self.Repo.GetWorkerAllowedProfiles(WORKER_ONE), "P1,P2")

    def test_update_persists_empty_string(self):
        Ok = self.Repo.UpdateWorkerAllowedProfiles(WORKER_ONE, "")
        self.assertTrue(Ok)
        self.assertEqual(self.Repo.GetWorkerAllowedProfiles(WORKER_ONE), "")

    def test_update_persists_null(self):
        Ok = self.Repo.UpdateWorkerAllowedProfiles(WORKER_ONE, None)
        self.assertTrue(Ok)
        self.assertIsNone(self.Repo.GetWorkerAllowedProfiles(WORKER_ONE))


if __name__ == '__main__':
    unittest.main()
