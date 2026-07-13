# directive: transcode-flow-canonical
import unittest

from Core.Path import LocalPath


# directive: transcode-flow-canonical
class TestLocalPathCanonicalGuard(unittest.TestCase):
    """Fail-loud when a canonical drive-letter path lands in a local FS op on a Linux worker."""

    def setUp(self):
        self._OriginalIsWindows = LocalPath._IS_WINDOWS
        LocalPath._IS_WINDOWS = False

    def tearDown(self):
        LocalPath._IS_WINDOWS = self._OriginalIsWindows

    def test_local_get_mtime_refuses_canonical_drive_letter(self):
        with self.assertRaises(ValueError):
            LocalPath.LocalGetMTime(r'M:\Blended\file.mp4')

    def test_local_exists_refuses_canonical_drive_letter(self):
        with self.assertRaises(ValueError):
            LocalPath.LocalExists(r'T:\Show\ep.mkv')

    def test_local_get_size_refuses_canonical_drive_letter(self):
        with self.assertRaises(ValueError):
            LocalPath.LocalGetSize(r'Z:\Some\file.mp4')

    def test_local_is_file_refuses_canonical_drive_letter(self):
        with self.assertRaises(ValueError):
            LocalPath.LocalIsFile(r'M:\file.mp4')

    def test_local_is_dir_refuses_canonical_drive_letter(self):
        with self.assertRaises(ValueError):
            LocalPath.LocalIsDir(r'T:\SomeDir')

    def test_local_path_accepts_posix_absolute(self):
        # No ValueError. May raise OSError (file doesn't exist) -- that's expected + separate.
        try:
            LocalPath.LocalExists('/mnt/movies/nonexistent-test-file.mp4')
        except ValueError:
            self.fail("guard fired on POSIX absolute path")

    def test_guard_ignored_on_windows(self):
        LocalPath._IS_WINDOWS = True
        try:
            LocalPath.LocalExists(r'M:\Blended\file.mp4')
        except ValueError:
            self.fail("guard fired on Windows")


if __name__ == '__main__':
    unittest.main()
