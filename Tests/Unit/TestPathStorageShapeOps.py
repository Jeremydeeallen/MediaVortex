import pytest
from Core.PathStorage import (
    LastSegment, ParentDir, Join, SplitExt,
    LocalExists, LocalIsFile, LocalIsDir,
    Normalize, PathsEqual,
)


class TestLastSegment:
    @pytest.mark.parametrize("PathValue,Expected", [
        (r"\\server\share\Videos\foo.mp4", "foo.mp4"),
        (r"Z:\Videos\foo.mp4", "foo.mp4"),
        ("/mnt/storage/foo.mp4", "foo.mp4"),
        (r"\\server\share\foo.mp4", "foo.mp4"),
        ("foo.mp4", "foo.mp4"),
        ("", ""),
        (r"Z:\\", ""),
        ("/mnt/storage/", ""),
    ])
    def test_all_shapes(self, PathValue, Expected):
        assert LastSegment(PathValue) == Expected


class TestParentDir:
    @pytest.mark.parametrize("PathValue,Expected", [
        (r"\\server\share\Videos\foo.mp4", r"\\server\share\Videos"),
        (r"Z:\Videos\foo.mp4", r"Z:\Videos"),
        ("/mnt/storage/foo.mp4", "/mnt/storage"),
        ("foo.mp4", ""),
        ("", ""),
    ])
    def test_all_shapes(self, PathValue, Expected):
        assert ParentDir(PathValue) == Expected


class TestJoin:
    @pytest.mark.parametrize("Base,Child,Expected", [
        (r"\\server\share\Videos", "foo.mp4", r"\\server\share\Videos\foo.mp4"),
        (r"Z:\Videos", "foo.mp4", r"Z:\Videos\foo.mp4"),
        ("/mnt/storage", "foo.mp4", "/mnt/storage/foo.mp4"),
        (r"Z:\Videos\\", "foo.mp4", r"Z:\Videos\foo.mp4"),
        ("/mnt/storage/", "foo.mp4", "/mnt/storage/foo.mp4"),
        ("Z:", "foo.mp4", r"Z:\foo.mp4"),
        ("", "foo.mp4", "foo.mp4"),
        ("/mnt/storage", "", "/mnt/storage"),
    ])
    def test_all_shapes(self, Base, Child, Expected):
        assert Join(Base, Child) == Expected


class TestSplitExt:
    @pytest.mark.parametrize("PathValue,ExpectedRoot,ExpectedExt", [
        (r"Z:\Videos\foo.mp4", r"Z:\Videos\foo", ".mp4"),
        ("/mnt/storage/foo.mp4", "/mnt/storage/foo", ".mp4"),
        (r"\\server\share\foo.mp4", r"\\server\share\foo", ".mp4"),
        ("/mnt/storage/foo", "/mnt/storage/foo", ""),
        ("/mnt/foo.bar/baz", "/mnt/foo.bar/baz", ""),
        ("", "", ""),
        ("foo.tar.gz", "foo.tar", ".gz"),
    ])
    def test_all_shapes(self, PathValue, ExpectedRoot, ExpectedExt):
        Root, Ext = SplitExt(PathValue)
        assert Root == ExpectedRoot
        assert Ext == ExpectedExt


class TestLocalMarkers:
    def test_local_exists_real_file(self):
        assert LocalExists("Core/PathStorage.py") is True

    def test_local_exists_missing(self):
        assert LocalExists("Core/DefinitelyNotThere.py") is False

    def test_local_exists_empty(self):
        assert LocalExists("") is False

    def test_local_exists_none(self):
        assert LocalExists(None) is False

    def test_local_isfile_directory_returns_false(self):
        assert LocalIsFile("Core") is False

    def test_local_isdir_directory(self):
        assert LocalIsDir("Core") is True

    def test_local_isdir_file_returns_false(self):
        assert LocalIsDir("Core/PathStorage.py") is False


# directive: paths-normalize-completion  # see path-storage.C4
class TestNormalize:
    @pytest.mark.parametrize("PathValue,Expected", [
        (r"\\server\share\a\..\b", r"\\server\share\b"),
        (r"T:\a\..\b", r"T:\b"),
        (r"T:\a\.\b", r"T:\a\b"),
        (r"T:\\a\\b", r"T:\a\b"),
        ("/a/../b", "/b"),
        ("/a/./b", "/a/b"),
        ("/a/b/", "/a/b"),
        (r"T:\Show\Episode.mkv", r"T:\Show\Episode.mkv"),
        ("", ""),
    ])
    # directive: paths-normalize-completion  # see path-storage.C4
    def test_shape_preserving(self, PathValue, Expected):
        assert Normalize(PathValue) == Expected

    # directive: paths-normalize-completion  # see path-storage.C4
    def test_unc_keeps_double_backslash_root(self):
        assert Normalize(r"\\server\share\path").startswith("\\\\server\\share")

    # directive: paths-normalize-completion  # see path-storage.C4
    def test_does_not_lowercase(self):
        assert Normalize(r"T:\Show\Episode.MKV") == r"T:\Show\Episode.MKV"


# directive: paths-normalize-completion  # see path-storage.C4
class TestPathsEqual:
    # directive: paths-normalize-completion  # see path-storage.C4
    def test_unc_auto_case_insensitive(self):
        assert PathsEqual(r"\\server\share\Show", r"\\SERVER\share\show") is True

    # directive: paths-normalize-completion  # see path-storage.C4
    def test_windows_drive_auto_case_insensitive(self):
        assert PathsEqual(r"T:\Show\Episode.mkv", r"t:\show\episode.mkv") is True

    # directive: paths-normalize-completion  # see path-storage.C4
    def test_posix_auto_case_sensitive(self):
        assert PathsEqual("/show/episode.mkv", "/Show/Episode.mkv") is False

    # directive: paths-normalize-completion  # see path-storage.C4
    def test_posix_same_path_true(self):
        assert PathsEqual("/show/episode.mkv", "/show/episode.mkv") is True

    # directive: paths-normalize-completion  # see path-storage.C4
    def test_normalizes_before_compare(self):
        assert PathsEqual(r"T:\a\..\b\c", r"T:\b\c") is True

    # directive: paths-normalize-completion  # see path-storage.C4
    def test_override_case_sensitive_on_unc(self):
        assert PathsEqual(r"\\server\share\Show", r"\\server\share\show", case_insensitive=False) is False

    # directive: paths-normalize-completion  # see path-storage.C4
    def test_override_case_insensitive_on_posix(self):
        assert PathsEqual("/Show/Episode.mkv", "/show/episode.mkv", case_insensitive=True) is True

    # directive: paths-normalize-completion  # see path-storage.C4
    def test_different_paths(self):
        assert PathsEqual(r"T:\a", r"T:\b") is False
        assert PathsEqual("/a", "/b") is False
