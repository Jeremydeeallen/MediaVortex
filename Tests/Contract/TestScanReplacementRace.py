import os
import tempfile
import unittest

from Features.FileScanning.FileScanningBusinessService import FileScanningBusinessService


# directive: auto-handoff | # see ingest.ST3
class TestScanReplacementRace(unittest.TestCase):

    # directive: auto-handoff | # see ingest.ST3
    def setUp(self):
        self.Dir = tempfile.mkdtemp()

    # directive: auto-handoff | # see ingest.ST3
    def _Touch(self, Name: str) -> str:
        Full = os.path.join(self.Dir, Name)
        with open(Full, 'wb') as F:
            F.write(b'x')
        return Full

    # directive: auto-handoff | # see ingest.ST3
    def _Resolve(self, RelativePath: str) -> str:
        return os.path.join(self.Dir, RelativePath)

    # directive: auto-handoff | # see ingest.ST3
    def test_ReplacementBetweenWalkAndLibraryReadWritesNothing(self):
        self._Touch('show-mv.mp4')
        DiskMap = {'show.mkv': {'RelativePath': 'show.mkv'}}
        DbMap = {'show-mv.mp4': {'Id': 7, 'RelativePath': 'show-mv.mp4'}}
        New, Deleted = FileScanningBusinessService._ConfirmDiffAgainstDisk(
            {'show.mkv'}, {'show-mv.mp4'}, DiskMap, DbMap, self._Resolve)
        self.assertEqual(New, set())
        self.assertEqual(Deleted, set())

    # directive: auto-handoff | # see ingest.ST3
    def test_GenuineNewFileIsKept(self):
        self._Touch('new.mkv')
        New, Deleted = FileScanningBusinessService._ConfirmDiffAgainstDisk(
            {'new.mkv'}, set(), {'new.mkv': {'RelativePath': 'new.mkv'}}, {}, self._Resolve)
        self.assertEqual(New, {'new.mkv'})
        self.assertEqual(Deleted, set())

    # directive: auto-handoff | # see ingest.ST3
    def test_GenuineDeletionIsKept(self):
        New, Deleted = FileScanningBusinessService._ConfirmDiffAgainstDisk(
            set(), {'gone.mkv'}, {}, {'gone.mkv': {'Id': 9, 'RelativePath': 'gone.mkv'}}, self._Resolve)
        self.assertEqual(New, set())
        self.assertEqual(Deleted, {'gone.mkv'})


if __name__ == '__main__':
    unittest.main()
