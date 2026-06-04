import pytest
from Core.PathStorage import (
    LastSegment, ParentDir, Join, SplitExt,
    LocalExists, LocalIsFile, LocalIsDir,
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
