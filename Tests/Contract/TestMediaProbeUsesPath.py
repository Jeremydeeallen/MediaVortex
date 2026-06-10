# directive: mediaprobe-uses-path | # see path.S5
import os
import sys
from pathlib import Path as PyPath

import pytest

sys.path.append(str(PyPath(__file__).parent.parent.parent))

from Core.Database.DatabaseService import DatabaseService
from Core.Path import Path, Worker
from Features.MediaProbe.MediaProbeBusinessService import MediaProbeBusinessService


@pytest.fixture(scope="module")
# directive: mediaprobe-uses-path | # see path.S5
def Db():
    """Module-scoped DatabaseService for the live-DB smoke."""
    return DatabaseService()


@pytest.fixture(scope="module")
# directive: mediaprobe-uses-path | # see path.S5
def ProbableMediaFile(Db):
    """Find a MediaFile with typed-pair populated whose Resolve-able path exists on disk; skip if none available on this host."""
    Worker_ = Worker.Current(Db=Db)
    Rows = Db.ExecuteQuery(
        "SELECT Id, StorageRootId, RelativePath FROM MediaFiles "
        "WHERE StorageRootId IS NOT NULL AND RelativePath IS NOT NULL "
        "ORDER BY Id LIMIT 200"
    )
    for Row in Rows:
        Sid = Row["StorageRootId" if "StorageRootId" in Row else "storagerootid"]
        Rel = Row["RelativePath" if "RelativePath" in Row else "relativepath"]
        try:
            P = Path(Sid, Rel)
            if P.Exists(Worker_):
                return Row
        except Exception:
            continue
    pytest.skip("No on-disk-existing MediaFile candidate found on this host for live smoke")


# directive: mediaprobe-uses-path | # see path.C12
def test_resolve_worker_local_against_live_row(ProbableMediaFile):
    """C12: _ResolveWorkerLocal on a real MediaFile returns a Path that resolves and exists on disk."""
    Svc = MediaProbeBusinessService()
    Row = ProbableMediaFile
    Mf = type("Mf", (), {})()
    Mf.StorageRootId = Row["StorageRootId" if "StorageRootId" in Row else "storagerootid"]
    Mf.RelativePath = Row["RelativePath" if "RelativePath" in Row else "relativepath"]
    from Core.Path.PathFs import Exists as _PathFsExists
    LocalPath, PathObj = Svc._ResolveWorkerLocal(Mf, "")
    assert PathObj is not None
    assert _PathFsExists(PathObj, Svc._GetWorker())
    assert isinstance(LocalPath, str) and len(LocalPath) > 0
