import pytest
from types import SimpleNamespace
from Core.Path.Path import Path, PathError
from Core.Path.PathFs import Exists, IsFile, IsDir, GetSize, GetMTime


# directive: path-class-perfection | # see path.C10
def test_pathfs_exists_returns_false_on_orphan():
    """C10: PathFs.Exists / IsFile / IsDir return False (not raises) when StorageRoot orphaned."""
    Worker = SimpleNamespace(
        Name="i9", Platform="linux",
        ResolveStorageRoot=lambda Sid: None,
    )
    p = Path(7, "Show/file.mkv")
    assert Exists(p, Worker) is False
    assert IsFile(p, Worker) is False
    assert IsDir(p, Worker) is False


# directive: path-class-perfection | # see path.C10
def test_pathfs_getsize_raises_on_orphan():
    """C10 / D11: PathFs.GetSize and GetMTime raise PathError when StorageRoot orphaned."""
    Worker = SimpleNamespace(
        Name="i9", Platform="linux",
        ResolveStorageRoot=lambda Sid: None,
    )
    p = Path(7, "Show/file.mkv")
    with pytest.raises(PathError):
        GetSize(p, Worker)
    with pytest.raises(PathError):
        GetMTime(p, Worker)
