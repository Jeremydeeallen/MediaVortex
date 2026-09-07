# directive: canonical-path-definition | # see path.S16
import os
import tempfile
import unittest
from unittest.mock import patch

from Core.Path import PathFs


class _FakeWorker:
    def __init__(self, Name, Platform, LocalPrefix):
        self.Name = Name
        self.Platform = Platform
        self._LocalPrefix = LocalPrefix

    def ResolveStorageRoot(self, StorageRootId):
        return self._LocalPrefix


# directive: canonical-path-definition | # see path.S16
class TestPathFsCanonicalExists(unittest.TestCase):
    """CanonicalExists / CanonicalGetSize translate a canonical string via worker mapping before FS op."""

    def setUp(self):
        self._TmpDir = tempfile.mkdtemp(prefix='cpd_')
        self._Platform = 'windows' if os.name == 'nt' else 'linux'
        self._Worker = _FakeWorker('test-worker', self._Platform, self._TmpDir)
        self._Roots = [{"Id": 9999, "CanonicalPrefix": "Z:\\"}]

    def tearDown(self):
        try:
            for Root, _, Files in os.walk(self._TmpDir, topdown=False):
                for F in Files:
                    os.remove(os.path.join(Root, F))
            os.rmdir(self._TmpDir)
        except OSError:
            pass

    def test_canonical_exists_true_when_local_file_present(self):
        LocalFile = os.path.join(self._TmpDir, 'sample.mp4')
        with open(LocalFile, 'wb') as F:
            F.write(b'x' * 1024)
        with patch('Core.Path.PathFs.GetStorageRoots', create=True, return_value=self._Roots), \
             patch('Core.Path.PathStorageRoots.GetStorageRoots', return_value=self._Roots):
            self.assertTrue(PathFs.CanonicalExists(r'Z:\sample.mp4', self._Worker))

    def test_canonical_exists_false_when_local_file_absent(self):
        with patch('Core.Path.PathStorageRoots.GetStorageRoots', return_value=self._Roots):
            self.assertFalse(PathFs.CanonicalExists(r'Z:\missing.mp4', self._Worker))

    def test_canonical_exists_false_on_empty_input(self):
        self.assertFalse(PathFs.CanonicalExists('', self._Worker))
        self.assertFalse(PathFs.CanonicalExists(None, self._Worker))

    def test_canonical_exists_false_on_unmatched_prefix(self):
        with patch('Core.Path.PathStorageRoots.GetStorageRoots', return_value=self._Roots):
            self.assertFalse(PathFs.CanonicalExists(r'Q:\nomatch.mp4', self._Worker))

    def test_canonical_get_size_returns_correct_bytes(self):
        LocalFile = os.path.join(self._TmpDir, 'size.bin')
        with open(LocalFile, 'wb') as F:
            F.write(b'y' * 4096)
        with patch('Core.Path.PathStorageRoots.GetStorageRoots', return_value=self._Roots):
            self.assertEqual(PathFs.CanonicalGetSize(r'Z:\size.bin', self._Worker), 4096)

    def test_canonical_get_size_raises_on_unmatched_prefix(self):
        from Core.Path.Path import PathError
        with patch('Core.Path.PathStorageRoots.GetStorageRoots', return_value=self._Roots):
            with self.assertRaises(PathError):
                PathFs.CanonicalGetSize(r'Q:\nomatch.bin', self._Worker)


if __name__ == '__main__':
    unittest.main()
