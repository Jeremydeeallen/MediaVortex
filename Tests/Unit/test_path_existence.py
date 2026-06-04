import pytest
from types import SimpleNamespace
from Core.Path.Path import Path, PathError


# directive: path-class-implementation | # see path.C10
def test_exists_returns_false_on_orphan():
    """C10: Exists / IsFile / IsDir return False (not raises) when StorageRoot orphaned."""
    Worker = SimpleNamespace(
        Name="i9", Platform="linux",
        ResolveStorageRoot=lambda Sid: None,
    )
    p = Path(7, "Show/file.mkv")
    assert p.Exists(Worker) is False
    assert p.IsFile(Worker) is False
    assert p.IsDir(Worker) is False


# directive: path-class-implementation | # see path.C10
def test_getsize_raises_on_orphan():
    """C10 / D11: GetSize and GetMTime raise PathError when StorageRoot orphaned."""
    Worker = SimpleNamespace(
        Name="i9", Platform="linux",
        ResolveStorageRoot=lambda Sid: None,
    )
    p = Path(7, "Show/file.mkv")
    with pytest.raises(PathError):
        p.GetSize(Worker)
    with pytest.raises(PathError):
        p.GetMTime(Worker)
