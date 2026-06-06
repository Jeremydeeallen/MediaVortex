# directive: path-worker-class | # see path.S3
from unittest.mock import MagicMock

import pytest

from Core.Path.Worker import Worker
from Core.Path.Path import Path, PathError


# directive: path-worker-class | # see path.S3
def _MockDbReturning(Rows: list):
    """Build a mock DatabaseService whose ExecuteQuery returns the given rows."""
    Mock = MagicMock()
    Mock.ExecuteQuery.return_value = Rows
    return Mock


# directive: path-worker-class | # see path.S3
def test_constructor_sets_name_platform():
    """C2: Worker exposes Name and Platform attributes per the Protocol."""
    W = Worker(Name="i9-2024", Platform="windows", Db=_MockDbReturning([]))
    assert W.Name == "i9-2024"
    assert W.Platform == "windows"


# directive: path-worker-class | # see path.S3
def test_resolve_storage_root_returns_prefix_on_match():
    """C3: ResolveStorageRoot returns the AbsolutePath when a row matches."""
    Mock = _MockDbReturning([{"AbsolutePath": "T:\\"}])
    W = Worker(Name="i9-2024", Platform="windows", Db=Mock)
    Result = W.ResolveStorageRoot(7)
    assert Result == "T:\\"
    Mock.ExecuteQuery.assert_called_once()


# directive: path-worker-class | # see path.S3
def test_resolve_storage_root_returns_none_on_miss():
    """C5: ResolveStorageRoot returns None when no row matches (D4 contract; Path.Resolve raises)."""
    Mock = _MockDbReturning([])
    W = Worker(Name="i9-2024", Platform="windows", Db=Mock)
    assert W.ResolveStorageRoot(999) is None


# directive: path-worker-class | # see path.S3
def test_cache_prevents_second_db_call_for_same_sid():
    """C4: repeated calls for the same sid hit the cache (mock-DB called once)."""
    Mock = _MockDbReturning([{"AbsolutePath": "T:\\"}])
    W = Worker(Name="i9-2024", Platform="windows", Db=Mock)
    W.ResolveStorageRoot(7)
    W.ResolveStorageRoot(7)
    W.ResolveStorageRoot(7)
    assert Mock.ExecuteQuery.call_count == 1


# directive: path-worker-class | # see path.S3
def test_cache_separate_per_sid():
    """C4: different sids each trigger their own DB call (then cache independently)."""
    Mock = MagicMock()
    Mock.ExecuteQuery.side_effect = [
        [{"AbsolutePath": "T:\\"}],
        [{"AbsolutePath": "M:\\"}],
        [{"AbsolutePath": "Z:\\"}],
    ]
    W = Worker(Name="i9-2024", Platform="windows", Db=Mock)
    assert W.ResolveStorageRoot(1) == "T:\\"
    assert W.ResolveStorageRoot(2) == "M:\\"
    assert W.ResolveStorageRoot(3) == "Z:\\"
    assert W.ResolveStorageRoot(1) == "T:\\"
    assert W.ResolveStorageRoot(2) == "M:\\"
    assert Mock.ExecuteQuery.call_count == 3


# directive: path-worker-class | # see path.S3
def test_cache_miss_also_cached():
    """C4: a None result is cached so the second miss doesn't re-query."""
    Mock = _MockDbReturning([])
    W = Worker(Name="i9-2024", Platform="windows", Db=Mock)
    assert W.ResolveStorageRoot(999) is None
    assert W.ResolveStorageRoot(999) is None
    assert Mock.ExecuteQuery.call_count == 1


# directive: path-worker-class | # see path.S3
def test_two_worker_instances_have_independent_caches():
    """C4: cache is per-instance; constructing a new Worker re-fetches fresh data."""
    MockA = _MockDbReturning([{"AbsolutePath": "T:\\"}])
    MockB = _MockDbReturning([{"AbsolutePath": "T-NEW:\\"}])
    A = Worker(Name="i9-2024", Platform="windows", Db=MockA)
    B = Worker(Name="i9-2024", Platform="windows", Db=MockB)
    assert A.ResolveStorageRoot(7) == "T:\\"
    assert B.ResolveStorageRoot(7) == "T-NEW:\\"


# directive: path-worker-class | # see path.S3
def test_resolve_query_filters_by_worker_name():
    """C3: the SQL parameter binding uses the Worker's Name."""
    Mock = _MockDbReturning([{"AbsolutePath": "T:\\"}])
    W = Worker(Name="larry-worker-3", Platform="linux", Db=Mock)
    W.ResolveStorageRoot(7)
    Args = Mock.ExecuteQuery.call_args
    assert Args[0][1] == (7, "larry-worker-3")


# directive: path-worker-class | # see path.S3
def test_path_resolve_consumes_worker_structurally():
    """C2: Path.Resolve(worker) accepts our concrete Worker without AttributeError (Protocol satisfaction)."""
    Mock = _MockDbReturning([{"AbsolutePath": "/mnt/media/"}])
    W = Worker(Name="larry-worker-3", Platform="linux", Db=Mock)
    P = Path(7, "Show/file.mkv")
    Result = P.Resolve(W)
    assert "/mnt/media/" in Result
    assert "Show/file.mkv" in Result


# directive: path-worker-class | # see path.S3
def test_path_resolve_raises_path_error_when_worker_returns_none():
    """C5 / D4: when Worker.ResolveStorageRoot returns None, Path.Resolve raises PathError."""
    Mock = _MockDbReturning([])
    W = Worker(Name="larry-worker-3", Platform="linux", Db=Mock)
    P = Path(7, "Show/file.mkv")
    with pytest.raises(PathError):
        P.Resolve(W)


# directive: path-worker-class | # see path.S3
def test_from_worker_context_uses_singleton():
    """C7: Worker.Current reads WorkerContext.Current() for Name + Platform."""
    from Core.WorkerContext import WorkerContext
    WorkerContext.Reset()
    try:
        WorkerContext.Initialize(WorkerName="test-worker-name", Platform="linux")
        W = Worker.Current(Db=_MockDbReturning([]))
        assert W.Name == "test-worker-name"
        assert W.Platform == "linux"
    finally:
        WorkerContext.Reset()


# directive: path-worker-class | # see path.S3
def test_from_worker_context_falls_back_to_hostname_when_uninitialized():
    """C7: Worker.Current falls back to socket.gethostname() when WorkerContext is uninitialized."""
    import socket
    from Core.WorkerContext import WorkerContext
    WorkerContext.Reset()
    W = Worker.Current(Db=_MockDbReturning([]))
    assert W.Name == socket.gethostname()
    assert W.Platform == "linux"


# directive: path-worker-class | # see path.S3
def test_realdictcursor_lowercase_keys_accepted():
    """C3: psycopg2 RealDictCursor returns lowercase keys; Worker handles both casings."""
    Mock = _MockDbReturning([{"absolutepath": "T:\\"}])
    W = Worker(Name="i9-2024", Platform="windows", Db=Mock)
    assert W.ResolveStorageRoot(7) == "T:\\"
