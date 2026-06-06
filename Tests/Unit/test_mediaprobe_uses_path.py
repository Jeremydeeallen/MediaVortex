# directive: path-class-perfection | # see path.C26
from unittest.mock import MagicMock, patch

from Features.MediaProbe.MediaProbeBusinessService import MediaProbeBusinessService
from Core.Path import Path, Worker, PathError


def _MakeService(worker=None):
    """Build a MediaProbeBusinessService with mock deps; default worker is a fresh MagicMock(Worker)."""
    MockRepo = MagicMock()
    MockFm = MagicMock()
    if worker is None:
        worker = MagicMock(spec=Worker)
    return MediaProbeBusinessService(RepositoryInstance=MockRepo, FileManagerInstance=MockFm, worker=worker)


def _MakeMediaFile(StorageRootId=None, RelativePath=None, FilePath=None):
    M = MagicMock()
    M.StorageRootId = StorageRootId
    M.RelativePath = RelativePath
    M.FilePath = FilePath
    return M


# directive: path-class-perfection | # see path.C26
def test_no_pathstorage_import_in_module():
    """Regression-guard: zero Core.PathStorage references."""
    import Features.MediaProbe.MediaProbeBusinessService as Mod
    Src = open(Mod.__file__, encoding="utf-8").read()
    assert "Core.PathStorage" not in Src


# directive: path-class-perfection | # see path.C26
def test_constructor_injects_worker():
    """C26: __init__ stores the injected worker; _GetWorker returns it."""
    MockWk = MagicMock(spec=Worker)
    S = _MakeService(worker=MockWk)
    assert S._Worker is MockWk
    assert S._GetWorker() is MockWk
    assert not hasattr(S, '_StorageRoots')


# directive: path-class-perfection | # see path.C26
def test_constructor_default_calls_worker_current():
    """C26: when no worker is passed, __init__ defaults to Worker.Current()."""
    MockWk = MagicMock(spec=Worker)
    with patch.object(Worker, "Current", return_value=MockWk) as Factory:
        S = MediaProbeBusinessService(RepositoryInstance=MagicMock(), FileManagerInstance=MagicMock())
        assert S._Worker is MockWk
        assert Factory.call_count == 1


# directive: path-class-perfection | # see path.C26
def test_resolve_uses_typed_pair_when_populated():
    """C5: when StorageRootId + RelativePath are populated, Resolve goes through Path(sid, rel).Resolve(worker)."""
    MockWk = MagicMock(spec=Worker)
    MockWk.ResolveStorageRoot.return_value = "/mnt/media/"
    MockWk.Platform = "linux"
    S = _MakeService(worker=MockWk)
    Mf = _MakeMediaFile(StorageRootId=7, RelativePath="Show/file.mkv", FilePath="T:\\Show\\file.mkv")
    LocalPath, PathObj = S._ResolveWorkerLocal(Mf, "T:\\Show\\file.mkv")
    assert PathObj is not None
    assert PathObj.StorageRootId == 7
    assert PathObj.RelativePath == "Show/file.mkv"
    assert "/mnt/media/" in LocalPath
    assert "Show/file.mkv" in LocalPath


# directive: path-class-perfection | # see path.C26
def test_resolve_falls_back_to_legacy_string_when_storageroot_id_none():
    """C5: when StorageRootId is None, falls through to FromLegacyString."""
    MockWk = MagicMock(spec=Worker)
    MockWk.ResolveStorageRoot.return_value = "T:\\"
    MockWk.Platform = "windows"
    S = _MakeService(worker=MockWk)
    with patch("Features.MediaProbe.MediaProbeBusinessService.MediaProbeBusinessService._GetStorageRoots",
               return_value=[{"Id": 1, "CanonicalPrefix": "T:\\"}]):
        Mf = _MakeMediaFile(StorageRootId=None, RelativePath=None, FilePath="T:\\Show\\file.mkv")
        LocalPath, PathObj = S._ResolveWorkerLocal(Mf, "T:\\Show\\file.mkv")
        assert PathObj is not None
        assert PathObj.StorageRootId == 1
        assert PathObj.RelativePath == "Show/file.mkv"


# directive: path-class-perfection | # see path.C26
def test_resolve_returns_none_path_when_fallback_filepath_empty():
    """C5: when typed pair is unpopulated AND FallbackFilePath is empty, returns (raw_fallback, None)."""
    MockWk = MagicMock(spec=Worker)
    S = _MakeService(worker=MockWk)
    Mf = _MakeMediaFile(StorageRootId=None, RelativePath=None, FilePath="")
    LocalPath, PathObj = S._ResolveWorkerLocal(Mf, "")
    assert PathObj is None
    assert LocalPath == ""
