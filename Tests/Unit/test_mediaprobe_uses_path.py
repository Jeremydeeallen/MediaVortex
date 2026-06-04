# directive: mediaprobe-uses-path | # see path.S5
from unittest.mock import MagicMock, patch

import pytest

from Features.MediaProbe.MediaProbeBusinessService import MediaProbeBusinessService
from Core.Path import Path, Worker, PathError


# directive: mediaprobe-uses-path | # see path.S5
def _MakeService():
    """Build a MediaProbeBusinessService with mock Repository + FileManager so we can exercise _ResolveWorkerLocal in isolation."""
    MockRepo = MagicMock()
    MockFm = MagicMock()
    return MediaProbeBusinessService(RepositoryInstance=MockRepo, FileManagerInstance=MockFm)


# directive: mediaprobe-uses-path | # see path.S5
def _MakeMediaFile(StorageRootId=None, RelativePath=None, FilePath=None):
    """Build a MediaFile-like object with the attributes _ResolveWorkerLocal reads."""
    M = MagicMock()
    M.StorageRootId = StorageRootId
    M.RelativePath = RelativePath
    M.FilePath = FilePath
    return M


# directive: mediaprobe-uses-path | # see path.S3
def test_no_pathstorage_import_in_module():
    """C1: the module no longer imports anything from Core.PathStorage."""
    import Features.MediaProbe.MediaProbeBusinessService as Mod
    Src = open(Mod.__file__, encoding="utf-8").read()
    assert "Core.PathStorage" not in Src


# directive: mediaprobe-uses-path | # see path.S3
def test_get_worker_returns_same_instance():
    """C4: _GetWorker caches the Worker across calls."""
    S = _MakeService()
    MockWorker = MagicMock(spec=Worker)
    with patch.object(Worker, "FromWorkerContext", return_value=MockWorker) as Factory:
        W1 = S._GetWorker()
        W2 = S._GetWorker()
        assert W1 is W2
        assert Factory.call_count == 1


# directive: mediaprobe-uses-path | # see path.S5
def test_resolve_uses_typed_pair_when_populated():
    """C5: when StorageRootId + RelativePath are populated, Resolve goes through Path(sid, rel).Resolve(worker)."""
    S = _MakeService()
    MockWorker = MagicMock(spec=Worker)
    MockWorker.ResolveStorageRoot.return_value = "/mnt/media/"
    MockWorker.Platform = "linux"
    S._Worker = MockWorker
    Mf = _MakeMediaFile(StorageRootId=7, RelativePath="Show/file.mkv", FilePath="T:\\Show\\file.mkv")
    LocalPath, PathObj = S._ResolveWorkerLocal(Mf, "T:\\Show\\file.mkv")
    assert PathObj is not None
    assert PathObj.StorageRootId == 7
    assert PathObj.RelativePath == "Show/file.mkv"
    assert "/mnt/media/" in LocalPath
    assert "Show/file.mkv" in LocalPath


# directive: mediaprobe-uses-path | # see path.S5
def test_resolve_falls_back_to_legacy_string_when_storageroot_id_none():
    """C5: when StorageRootId is None, falls through to FromLegacyString."""
    S = _MakeService()
    MockWorker = MagicMock(spec=Worker)
    MockWorker.ResolveStorageRoot.return_value = "T:\\"
    MockWorker.Platform = "windows"
    S._Worker = MockWorker
    S._StorageRoots = [{"Id": 1, "CanonicalPrefix": "T:\\"}]
    Mf = _MakeMediaFile(StorageRootId=None, RelativePath=None, FilePath="T:\\Show\\file.mkv")
    LocalPath, PathObj = S._ResolveWorkerLocal(Mf, "T:\\Show\\file.mkv")
    assert PathObj is not None
    assert PathObj.StorageRootId == 1
    assert PathObj.RelativePath == "Show/file.mkv"


# directive: mediaprobe-uses-path | # see path.S5
def test_resolve_falls_back_to_legacy_when_relative_path_empty():
    """C5: when RelativePath is empty string, falls through to FromLegacyString."""
    S = _MakeService()
    MockWorker = MagicMock(spec=Worker)
    MockWorker.ResolveStorageRoot.return_value = "T:\\"
    MockWorker.Platform = "windows"
    S._Worker = MockWorker
    S._StorageRoots = [{"Id": 1, "CanonicalPrefix": "T:\\"}]
    Mf = _MakeMediaFile(StorageRootId=7, RelativePath="", FilePath="T:\\Show\\file.mkv")
    LocalPath, PathObj = S._ResolveWorkerLocal(Mf, "T:\\Show\\file.mkv")
    assert PathObj is not None
    assert PathObj.RelativePath == "Show/file.mkv"


# directive: mediaprobe-uses-path | # see path.S5
def test_resolve_falls_back_to_legacy_on_path_error():
    """C5: orphan StorageRoot raises PathError on typed-pair Resolve; falls through to FromLegacyString which uses a different storage root."""
    S = _MakeService()
    MockWorker = MagicMock(spec=Worker)
    MockWorker.ResolveStorageRoot.side_effect = [None, "T:\\"]
    MockWorker.Platform = "windows"
    S._Worker = MockWorker
    S._StorageRoots = [{"Id": 1, "CanonicalPrefix": "T:\\"}]
    Mf = _MakeMediaFile(StorageRootId=999, RelativePath="Show/file.mkv", FilePath="T:\\Show\\file.mkv")
    LocalPath, PathObj = S._ResolveWorkerLocal(Mf, "T:\\Show\\file.mkv")
    assert PathObj is not None
    assert PathObj.StorageRootId == 1


# directive: mediaprobe-uses-path | # see path.S5
def test_resolve_returns_none_path_when_both_attempts_fail():
    """C5 final-fallback: when typed pair fails AND FromLegacyString fails, returns (raw_fallback, None) for logging."""
    S = _MakeService()
    MockWorker = MagicMock(spec=Worker)
    MockWorker.ResolveStorageRoot.return_value = None
    MockWorker.Platform = "linux"
    S._Worker = MockWorker
    S._StorageRoots = [{"Id": 1, "CanonicalPrefix": "T:\\"}]
    Mf = _MakeMediaFile(StorageRootId=None, RelativePath=None, FilePath="unparseable-no-prefix-shape")
    LocalPath, PathObj = S._ResolveWorkerLocal(Mf, "unparseable-no-prefix-shape")
    assert PathObj is None
    assert LocalPath == "unparseable-no-prefix-shape"


# directive: mediaprobe-uses-path | # see path.S5
def test_resolve_returns_none_path_when_fallback_filepath_empty():
    """C5: when typed pair is unpopulated AND FallbackFilePath is empty, returns (raw_fallback, None)."""
    S = _MakeService()
    MockWorker = MagicMock(spec=Worker)
    S._Worker = MockWorker
    Mf = _MakeMediaFile(StorageRootId=None, RelativePath=None, FilePath="")
    LocalPath, PathObj = S._ResolveWorkerLocal(Mf, "")
    assert PathObj is None
    assert LocalPath == ""


# directive: mediaprobe-uses-path | # see path.S6
def test_storage_roots_cached_across_calls():
    """C4: _GetStorageRoots loads once and caches."""
    S = _MakeService()
    S._StorageRoots = None
    MockRows = [{"id": 1, "canonicalprefix": "T:\\"}, {"id": 2, "canonicalprefix": "M:\\"}]
    with patch("Core.Database.DatabaseService.DatabaseService") as Db:
        Db.return_value.ExecuteQuery.return_value = MockRows
        Roots1 = S._GetStorageRoots()
        Roots2 = S._GetStorageRoots()
        assert Roots1 is Roots2
        assert Db.return_value.ExecuteQuery.call_count == 1


# directive: mediaprobe-uses-path | # see path.S3
def test_constructor_initializes_lazy_state_to_none():
    """C3: __init__ initializes _Worker and _StorageRoots to None for lazy construction."""
    S = _MakeService()
    assert S._Worker is None
    assert S._StorageRoots is None
