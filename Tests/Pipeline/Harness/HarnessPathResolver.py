from __future__ import annotations

from typing import Optional

from Core.Database.DatabaseService import DatabaseService
from Core.Path.LocalPath import LocalExists
from Core.Path.Path import Path, PathError
from Core.Path.Worker import Worker


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def DefaultTestWorkerName() -> str:
    """DB-backed worker identity fallback for harness use (R4 replacement for env var); see pipeline-test-harness.feature.md S1."""
    from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
    Value = SystemSettingsRepository().GetSystemSetting('DefaultTestWorkerName')
    return Value or 'I9-2024'


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def BuildHarnessWorker(Db: Optional[DatabaseService] = None) -> Worker:
    """Build a Worker honoring WorkerContext when present; otherwise look up platform for the SystemSettings fallback worker name."""
    from Core.WorkerContext import WorkerContext
    if Db is None:
        Db = DatabaseService()
    Ctx = WorkerContext.TryCurrent()
    if Ctx and Ctx.WorkerName:
        return Worker(Ctx.WorkerName, Ctx.Platform or 'windows', Db)
    WorkerName = DefaultTestWorkerName()
    Rows = Db.ExecuteQuery("SELECT Platform FROM Workers WHERE WorkerName = %s", (WorkerName,))
    Platform = (Rows[0].get('Platform') or Rows[0].get('platform') or 'windows') if Rows else 'windows'
    return Worker(WorkerName, Platform, Db)


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def ResolveLocalPath(W: Worker, StorageRootId: Optional[int], RelativePath: str) -> Optional[str]:
    """Translate typed (StorageRootId, RelativePath) to this worker's local mount; None if unresolvable."""
    if StorageRootId is None or not RelativePath:
        return None
    try:
        return Path(StorageRootId, RelativePath).Resolve(W)
    except PathError:
        return None


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def ResolveLocalPathForMediaFile(MediaFileId: int, Db: Optional[DatabaseService] = None) -> Optional[str]:
    """Look up (StorageRootId, RelativePath) for MediaFileId then resolve via the harness Worker."""
    if Db is None:
        Db = DatabaseService()
    Rows = Db.ExecuteQuery("SELECT StorageRootId, RelativePath FROM MediaFiles WHERE Id = %s", (MediaFileId,))
    if not Rows:
        return None
    R = Rows[0]
    Sid = R.get('StorageRootId') if 'StorageRootId' in R else R.get('storagerootid')
    Rel = R.get('RelativePath') if 'RelativePath' in R else R.get('relativepath')
    return ResolveLocalPath(BuildHarnessWorker(Db), Sid, Rel or '')


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def LocalExistsForMediaFile(MediaFileId: int, Db: Optional[DatabaseService] = None) -> bool:
    """Convenience: resolve a MediaFileId's local path and check existence."""
    Local = ResolveLocalPathForMediaFile(MediaFileId, Db)
    return bool(Local and LocalExists(Local))
