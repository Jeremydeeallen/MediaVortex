# directive: path-worker-class | # see path.S3
import sys
from pathlib import Path as PyPath

import pytest

sys.path.append(str(PyPath(__file__).parent.parent.parent))

from Core.Database.DatabaseService import DatabaseService
from Core.Path.Worker import Worker
from Core.Path.Path import Path, PathError


@pytest.fixture(scope="module")
# directive: path-worker-class | # see path.S3
def Db():
    """Module-scoped DatabaseService for live-DB contract tests."""
    return DatabaseService()


@pytest.fixture(scope="module")
# directive: path-worker-class | # see path.S3
def WorkerName(Db):
    """Pick a real WorkerName from StorageRootResolutions; skip module if none configured."""
    Rows = Db.ExecuteQuery(
        "SELECT DISTINCT WorkerName FROM StorageRootResolutions WHERE IsActive = TRUE LIMIT 1"
    )
    if not Rows:
        pytest.skip("No active StorageRootResolutions rows; cannot run live Worker contract test")
    Row = Rows[0]
    return Row["WorkerName" if "WorkerName" in Row else "workername"]


# directive: path-worker-class | # see path.S3
def test_resolve_storage_root_against_live_db(Db, WorkerName):
    """C9: Worker.ResolveStorageRoot returns the same AbsolutePath as a direct query on StorageRootResolutions."""
    Rows = Db.ExecuteQuery(
        "SELECT StorageRootId, AbsolutePath FROM StorageRootResolutions WHERE WorkerName = %s AND IsActive = TRUE",
        (WorkerName,),
    )
    assert len(Rows) > 0
    W = Worker(Name=WorkerName, Platform="windows", Db=Db)
    for Row in Rows:
        Sid = Row["StorageRootId" if "StorageRootId" in Row else "storagerootid"]
        Abs = Row["AbsolutePath" if "AbsolutePath" in Row else "absolutepath"]
        assert W.ResolveStorageRoot(Sid) == Abs


# directive: path-worker-class | # see path.S3
def test_resolve_storage_root_unknown_id_returns_none(Db, WorkerName):
    """C5: unknown StorageRootId yields None from the live DB."""
    W = Worker(Name=WorkerName, Platform="windows", Db=Db)
    assert W.ResolveStorageRoot(9_999_999_999) is None


# directive: path-worker-class | # see path.C12
def test_end_to_end_path_resolve_with_live_worker(Db, WorkerName):
    """C12: Path(...).Resolve(Worker(...)) produces a real absolute path against the live DB."""
    Rows = Db.ExecuteQuery(
        "SELECT StorageRootId, AbsolutePath FROM StorageRootResolutions WHERE WorkerName = %s AND IsActive = TRUE LIMIT 1",
        (WorkerName,),
    )
    assert len(Rows) == 1
    Sid = Rows[0]["StorageRootId" if "StorageRootId" in Rows[0] else "storagerootid"]
    Abs = Rows[0]["AbsolutePath" if "AbsolutePath" in Rows[0] else "absolutepath"]
    W = Worker(Name=WorkerName, Platform="windows", Db=Db)
    P = Path(Sid, "Show/Season 1/file.mkv")
    Result = P.Resolve(W)
    assert Result.startswith(Abs)
    assert "file.mkv" in Result


# directive: path-worker-class | # see path.S3
def test_from_worker_context_constructs_usable_worker(Db):
    """C7: FromWorkerContext yields a Worker with non-empty Name and Platform."""
    W = Worker.FromWorkerContext(Db=Db)
    assert isinstance(W.Name, str) and len(W.Name) > 0
    assert isinstance(W.Platform, str) and len(W.Platform) > 0
