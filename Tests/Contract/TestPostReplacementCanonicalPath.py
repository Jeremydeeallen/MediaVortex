import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.Workers.PostEncodeAudioHandler import PostEncodeAudioHandler


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S4
class TestPostReplacementCanonicalPath(unittest.TestCase):
    """S4: SQL join MediaFiles + StorageRoots into a Windows-flavored canonical path."""

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S4
    def _Stub(self, Rows):
        """Build a mocked DatabaseService that returns the provided Rows from ExecuteQuery."""
        Patcher = patch(
            'Features.AudioNormalization.Workers.PostEncodeAudioHandler.DatabaseService'
        )
        Mock = Patcher.start()
        self.addCleanup(Patcher.stop)
        Instance = MagicMock()
        Mock.return_value = Instance
        Instance.ExecuteQuery.return_value = Rows
        return Instance

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S4
    def test_windows_drive_prefix(self):
        self._Stub([{'canonicalprefix': 'T:', 'relativepath': 'Show/Season 1/ep.mp4'}])
        Result = PostEncodeAudioHandler().ResolvePostReplacementCanonicalPath(1)
        self.assertEqual(Result, 'T:\\Show/Season 1/ep.mp4')

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S4
    def test_unc_prefix_uses_backslash(self):
        self._Stub([{'canonicalprefix': r'\\nas\media', 'relativepath': 'Show/ep.mp4'}])
        Result = PostEncodeAudioHandler().ResolvePostReplacementCanonicalPath(1)
        self.assertTrue(Result.startswith(r'\\nas\media'))

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S4
    def test_posix_prefix_uses_forward_slash(self):
        self._Stub([{'canonicalprefix': '/mnt/media', 'relativepath': 'Show/ep.mp4'}])
        Result = PostEncodeAudioHandler().ResolvePostReplacementCanonicalPath(1)
        self.assertEqual(Result, '/mnt/media/Show/ep.mp4')

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S4
    def test_empty_relative_path_returns_none(self):
        self._Stub([{'canonicalprefix': 'T:', 'relativepath': ''}])
        self.assertIsNone(PostEncodeAudioHandler().ResolvePostReplacementCanonicalPath(1))

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S4
    def test_missing_row_returns_none(self):
        self._Stub([])
        self.assertIsNone(PostEncodeAudioHandler().ResolvePostReplacementCanonicalPath(99))

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S4
    def test_trailing_separator_stripped_from_prefix(self):
        self._Stub([{'canonicalprefix': 'T:\\', 'relativepath': 'Show/ep.mp4'}])
        Result = PostEncodeAudioHandler().ResolvePostReplacementCanonicalPath(1)
        self.assertFalse(Result.startswith('T:\\\\'))
        self.assertTrue(Result.startswith('T:\\'))


if __name__ == '__main__':
    unittest.main()
