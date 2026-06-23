import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from Core.Path.LocalPath import LocalExists


# see transcoded-output-placement.C13
class TestFileReplacementRollbackOnUpdateFailure(unittest.TestCase):

    def setUp(self):
        self.TempDir = tempfile.mkdtemp(prefix='bug0067_')
        self.AddPaths = []

    def tearDown(self):
        for P in self.AddPaths:
            if LocalExists(P):
                try:
                    os.remove(P)
                except OSError:
                    pass
        try:
            os.rmdir(self.TempDir)
        except OSError:
            pass

    def _PathStub(self, Canonical, _StorageRoots):
        Stub = MagicMock()
        Stub.Resolve = lambda _Worker: Canonical
        return Stub

    def _Placement(self):
        from Features.FileReplacement.TranscodedOutputPlacement import TranscodedOutputPlacement
        Inst = TranscodedOutputPlacement.__new__(TranscodedOutputPlacement)
        Inst.DatabaseManager = MagicMock()
        Inst.FileManager = MagicMock()
        Inst.WorkerName = 'test-worker'
        Inst._Worker = MagicMock()
        return Inst

    def _MakeFile(self, Name, Content=b'X'):
        P = os.path.join(self.TempDir, Name)  # allow: local-path; constructing a worker-local temp test path
        with open(P, 'wb') as F:
            F.write(Content)
        self.AddPaths.append(P)
        return P

    def test_rollback_nonsameslot_removes_orphan_and_keeps_source(self):
        SourceBytes = b'SRC' * 100
        SourcePath = self._MakeFile('Show.mkv', SourceBytes)
        StagedPath = self._MakeFile('Show-mv.mp4.inprogress', b'NEW' * 100)
        TargetPath = os.path.join(self.TempDir, 'Show-mv.mp4')  # allow: local-path; test-local target
        self.AddPaths.append(TargetPath)
        Inst = self._Placement()
        Inst._UpdateMediaFilesAfterReplacement = MagicMock(
            return_value={'Success': False, 'ErrorMessage': 'duplicate key on idx_mediafiles_storageroot_relpath_unique'}
        )
        with patch.object(Inst, '_GetStorageRoots', return_value=[]):
            with patch('Features.FileReplacement.TranscodedOutputPlacement.Path') as MockPath:
                MockPath.FromLegacyString.side_effect = self._PathStub
                Result = Inst.Execute(
                    OriginalFilePath=SourcePath,
                    TranscodedFilePath=StagedPath,
                    NetworkOriginalPath=SourcePath,
                    SourceMediaFileId=None,
                )
        self.assertFalse(Result.get('Success'), 'Execute must return Success=False on update failure')
        self.assertIn('duplicate key', Result.get('ErrorMessage', ''))
        self.assertFalse(LocalExists(TargetPath), 'Orphan -mv.mp4 must NOT remain on disk after rollback')
        self.assertTrue(LocalExists(SourcePath), 'Source must survive rollback')
        with open(SourcePath, 'rb') as F:
            self.assertEqual(F.read(), SourceBytes, 'Source bytes must match pre-call state')

    def test_rollback_sameslot_restores_source_and_removes_staging(self):
        SourceBytes = b'SRC' * 100
        SourcePath = self._MakeFile('Show-mv.mkv', SourceBytes)
        StagedPath = os.path.join(self.TempDir, 'Show-mv.mkv.inprogress')  # allow: local-path; test-local staged
        with open(StagedPath, 'wb') as F:
            F.write(b'NEW' * 100)
        self.AddPaths.append(StagedPath)
        BackupPath = SourcePath + '.replacing.bak'
        self.AddPaths.append(BackupPath)
        Inst = self._Placement()
        Inst._UpdateMediaFilesAfterReplacement = MagicMock(
            return_value={'Success': False, 'ErrorMessage': 'reprobe failed: corrupt mp4'}
        )
        with patch.object(Inst, '_GetStorageRoots', return_value=[]):
            with patch('Features.FileReplacement.TranscodedOutputPlacement.Path') as MockPath:
                MockPath.FromLegacyString.side_effect = self._PathStub
                Result = Inst.Execute(
                    OriginalFilePath=SourcePath,
                    TranscodedFilePath=StagedPath,
                    NetworkOriginalPath=SourcePath,
                    SourceMediaFileId=None,
                )
        self.assertFalse(Result.get('Success'), 'Execute must return Success=False on update failure')
        self.assertIn('reprobe failed', Result.get('ErrorMessage', ''))
        self.assertFalse(LocalExists(BackupPath), 'Backup must not survive rollback (renamed back to source)')
        self.assertFalse(LocalExists(StagedPath), 'Staging .inprogress artifact must not survive rollback')
        self.assertTrue(LocalExists(SourcePath), 'Source must be restored')
        with open(SourcePath, 'rb') as F:
            self.assertEqual(F.read(), SourceBytes, 'Restored source bytes must match pre-call state')

    def test_finalize_partial_replacement_fails_loud_on_update_failure(self):
        FinalPath = self._MakeFile('Show-mv.mp4', b'NEW' * 100)
        OriginalPath = os.path.join(self.TempDir, 'Show.mkv')  # allow: local-path; test-local original
        self.AddPaths.append(OriginalPath)
        Inst = self._Placement()
        Inst._UpdateMediaFilesAfterReplacement = MagicMock(
            return_value={'Success': False, 'ErrorMessage': 'media_file not found for path'}
        )
        with patch.object(Inst, '_GetStorageRoots', return_value=[]):
            with patch('Features.FileReplacement.TranscodedOutputPlacement.Path') as MockPath:
                MockPath.FromLegacyString.side_effect = self._PathStub
                Result = Inst.FinalizePartialReplacement(
                    OriginalLocalPath=OriginalPath,
                    FinalLocalPath=FinalPath,
                    CanonicalOriginalPath=OriginalPath,
                )
        self.assertFalse(Result.get('Success'), 'FinalizePartialReplacement must return Success=False on update failure')
        self.assertIn('media_file not found', Result.get('ErrorMessage', ''))


if __name__ == '__main__':
    unittest.main()
