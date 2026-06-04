import pytest
from types import SimpleNamespace
from Core.Path.Path import Path, PathError


# directive: path-class-implementation | # see path.C8
def test_returns_worker_local_string():
    """C8: Resolve joins worker prefix to RelativePath."""
    Worker = SimpleNamespace(
        Name="i9", Platform="linux",
        ResolveStorageRoot=lambda Sid: {7: "/mnt/media_tv/"}.get(Sid),
    )
    p = Path(7, "Show/file.mkv")
    assert p.Resolve(Worker) == "/mnt/media_tv/Show/file.mkv"


# directive: path-class-implementation | # see path.C8
def test_windows_worker_uses_backslash():
    """C8: Windows worker -> backslash separators in output."""
    Worker = SimpleNamespace(
        Name="i9", Platform="windows",
        ResolveStorageRoot=lambda Sid: {7: "T:\\"}.get(Sid),
    )
    p = Path(7, "Show/file.mkv")
    assert p.Resolve(Worker) == "T:\\Show\\file.mkv"


# directive: path-class-implementation | # see path.C8
def test_linux_worker_uses_forward_slash():
    """C8: Linux worker -> forward slash separators in output."""
    Worker = SimpleNamespace(
        Name="larry", Platform="linux",
        ResolveStorageRoot=lambda Sid: {7: "/mnt/tv/"}.get(Sid),
    )
    p = Path(7, "Show/file.mkv")
    assert p.Resolve(Worker) == "/mnt/tv/Show/file.mkv"


# directive: path-class-implementation | # see path.C9
def test_orphan_storage_root_raises():
    """C9 / D4: Resolve raises PathError when worker.ResolveStorageRoot returns None."""
    Worker = SimpleNamespace(
        Name="i9", Platform="linux",
        ResolveStorageRoot=lambda Sid: {7: "/mnt/media_tv/"}.get(Sid),
    )
    p = Path(99, "Show/file.mkv")
    with pytest.raises(PathError):
        p.Resolve(Worker)
