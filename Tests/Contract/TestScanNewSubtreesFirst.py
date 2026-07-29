# directive: scan-new-subtrees-first
import os
import tempfile
import unittest
from unittest.mock import MagicMock

from Core.Database.DatabaseService import DatabaseService, EscapeLikePattern
from Core.Path.LocalPath import LocalJoin
from Features.FileScanning.FileScanningRepository import FileScanningRepository
from Features.FileScanning.FileScanningBusinessService import FileScanningBusinessService
from Features.FileScanning.Models.RootFolderModel import RootFolderModel


SENTINEL_PREFIX = '_test-newsubtrees-'


class TestGetKnownLevel1SubdirNames(unittest.TestCase):
    """Live-DB contract for FileScanningRepository.GetKnownLevel1SubdirNames (C1 diff)."""

    @classmethod
    def setUpClass(cls):
        cls.Db = DatabaseService()
        cls.Repo = FileScanningRepository(cls.Db)
        cls._Reset()
        cls.StorageRootId = cls._PickAnyStorageRootId()
        Rows = [
            (f'{SENTINEL_PREFIX}mount-root-a.mkv', cls.StorageRootId, 'AlphaShow/S01/ep.mkv'),
            (f'{SENTINEL_PREFIX}mount-root-b.mkv', cls.StorageRootId, 'BravoShow/S01/ep.mkv'),
            (f'{SENTINEL_PREFIX}sub-1.mkv', cls.StorageRootId, 'ParentDir/AlphaShow/ep.mkv'),
            (f'{SENTINEL_PREFIX}sub-2.mkv', cls.StorageRootId, 'ParentDir/BravoShow/ep.mkv'),
        ]
        for FileName, Srid, RelPath in Rows:
            cls.Db.ExecuteNonQuery(
                "INSERT INTO MediaFiles (FileName, StorageRootId, RelativePath) VALUES (%s, %s, %s)",
                (FileName, Srid, RelPath),
            )

    @classmethod
    def tearDownClass(cls):
        cls._Reset()

    @classmethod
    def _Reset(cls):
        cls.Db.ExecuteNonQuery(
            "DELETE FROM MediaFiles WHERE FileName LIKE %s ESCAPE '!'",
            (EscapeLikePattern(SENTINEL_PREFIX) + '%',),
        )

    @classmethod
    def _PickAnyStorageRootId(cls):
        Rows = cls.Db.ExecuteQuery("SELECT Id FROM StorageRoots ORDER BY Id LIMIT 1")
        return Rows[0]['Id'] if Rows else 1

    def test_MountRoot_returns_level1_of_relativepath(self):
        Known = self.Repo.GetKnownLevel1SubdirNames(self.StorageRootId, "")
        self.assertIn('alphashow', Known)
        self.assertIn('bravoshow', Known)
        self.assertIn('parentdir', Known)

    def test_SubfolderRoot_strips_prefix_before_split(self):
        Known = self.Repo.GetKnownLevel1SubdirNames(self.StorageRootId, "ParentDir")
        self.assertIn('alphashow', Known)
        self.assertIn('bravoshow', Known)
        self.assertNotIn('parentdir', Known)

    def test_UnknownPrefix_returns_empty_set(self):
        Known = self.Repo.GetKnownLevel1SubdirNames(self.StorageRootId, "NoSuchPrefix" + SENTINEL_PREFIX)
        self.assertEqual(Known, set())


class TestSortNewSubtreesFirst(unittest.TestCase):
    """Sort helper contract (C1 order, C4 excluded dirs, C6/C7 edges, log-line paths)."""

    def setUp(self):
        self.Svc = FileScanningBusinessService.__new__(FileScanningBusinessService)
        self.Svc.FileManager = MagicMock()
        self.Svc.FileManager.ShouldExcludeDirectory = MagicMock(return_value=False)
        self.Svc.Repository = MagicMock()

    def _MakeTree(self, TmpDir, Subdirs):
        Paths = []
        for Sub in Subdirs:
            SubLocal = LocalJoin(TmpDir, Sub)
            os.makedirs(SubLocal, exist_ok=True)
            for I in range(5):
                FileLocal = LocalJoin(SubLocal, f'ep{I}.mkv')
                open(FileLocal, 'w').close()
                Paths.append(FileLocal)
        return Paths

    def _MakeRootFolder(self):
        return RootFolderModel(Id=1, StorageRootId=1, RelativePath="")

    def test_C1_new_subtree_files_come_first(self):
        with tempfile.TemporaryDirectory() as Tmp:
            Files = self._MakeTree(Tmp, ['KnownShow', 'FreshDrop'])
            self.Svc.Repository.GetKnownLevel1SubdirNames.return_value = {'knownshow'}
            Result = self.Svc._SortNewSubtreesFirst(Files, Tmp, self._MakeRootFolder(), 'T:\\Root')
            NewCount = 5
            for P in Result[:NewCount]:
                self.assertIn('FreshDrop', P)
            for P in Result[NewCount:]:
                self.assertIn('KnownShow', P)

    def test_C2_no_new_returns_input_unchanged(self):
        with tempfile.TemporaryDirectory() as Tmp:
            Files = self._MakeTree(Tmp, ['KnownA', 'KnownB'])
            self.Svc.Repository.GetKnownLevel1SubdirNames.return_value = {'knowna', 'knownb'}
            Result = self.Svc._SortNewSubtreesFirst(Files, Tmp, self._MakeRootFolder(), 'T:\\Root')
            self.assertEqual(Result, Files)

    def test_C4_excluded_dirs_not_classified_as_new(self):
        with tempfile.TemporaryDirectory() as Tmp:
            Files = self._MakeTree(Tmp, ['KnownShow', 'SkipMe'])
            self.Svc.FileManager.ShouldExcludeDirectory = MagicMock(
                side_effect=lambda P: P.endswith('SkipMe')
            )
            self.Svc.Repository.GetKnownLevel1SubdirNames.return_value = {'knownshow'}
            Result = self.Svc._SortNewSubtreesFirst(Files, Tmp, self._MakeRootFolder(), 'T:\\Root')
            self.assertEqual(Result, Files)

    def test_C6_first_scan_empty_db_all_new(self):
        with tempfile.TemporaryDirectory() as Tmp:
            Files = self._MakeTree(Tmp, ['ShowA', 'ShowB'])
            self.Svc.Repository.GetKnownLevel1SubdirNames.return_value = set()
            Result = self.Svc._SortNewSubtreesFirst(Files, Tmp, self._MakeRootFolder(), 'T:\\Root')
            self.assertEqual(sorted(Result), sorted(Files))

    def test_C7_no_subdirs_returns_input(self):
        with tempfile.TemporaryDirectory() as Tmp:
            F1 = LocalJoin(Tmp, 'flat1.mkv')
            F2 = LocalJoin(Tmp, 'flat2.mkv')
            open(F1, 'w').close()
            open(F2, 'w').close()
            Files = [F1, F2]
            self.Svc.Repository.GetKnownLevel1SubdirNames.return_value = set()
            Result = self.Svc._SortNewSubtreesFirst(Files, Tmp, self._MakeRootFolder(), 'T:\\Root')
            self.assertEqual(Result, Files)

    def test_stable_within_partition(self):
        with tempfile.TemporaryDirectory() as Tmp:
            Files = self._MakeTree(Tmp, ['ShowA', 'ShowB', 'ShowC'])
            self.Svc.Repository.GetKnownLevel1SubdirNames.return_value = {'showa', 'showb', 'showc'}
            Result = self.Svc._SortNewSubtreesFirst(Files, Tmp, self._MakeRootFolder(), 'T:\\Root')
            self.assertEqual(Result, Files)


if __name__ == '__main__':
    unittest.main()
