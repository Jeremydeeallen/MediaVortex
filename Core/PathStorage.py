"""Path storage canonical layer.

The single Resolve function used by all I/O code in Phase 4+. Takes
(StorageRootId, RelativePath, WorkerName) and returns the worker-local
absolute path. No drive-letter parsing, no regex, no string substitutions
against legacy WorkerShareMappings.

This file is the < 50 LOC contract from path-storage.feature.md criterion 4.
Keep it small. Resolve and Parse are the entire surface.
"""

import os
import re
from typing import Optional


class PathStorageError(RuntimeError):
    pass


def Resolve(StorageRootId: int, RelativePath: str, WorkerName: str, Db=None) -> str:
    """Return the worker-local absolute path for (StorageRootId, RelativePath)
    on the named worker. Reads StorageRootResolutions; raises PathStorageError
    if no active resolution exists for (StorageRootId, WorkerName)."""
    if Db is None:
        from Core.Database.DatabaseService import DatabaseService
        Db = DatabaseService()
    Rows = Db.ExecuteQuery(
        "SELECT AbsolutePath FROM StorageRootResolutions "
        "WHERE StorageRootId = %s AND WorkerName = %s AND IsActive = TRUE LIMIT 1",
        (StorageRootId, WorkerName),
    )
    if not Rows:
        raise PathStorageError(
            f"No active StorageRootResolutions row for "
            f"(StorageRootId={StorageRootId}, WorkerName={WorkerName!r})"
        )
    AbsolutePath = Rows[0]['AbsolutePath']
    Rel = (RelativePath or '').lstrip('/').lstrip('\\').replace('\\', '/')
    return os.path.join(AbsolutePath, Rel)


_DRIVE_PREFIX_RX = re.compile(r'^[A-Za-z]:[\\/]')


def Parse(CanonicalPath: str, StorageRoots: list) -> tuple:
    """Given a canonical (Windows-shaped) path like 'T:\\Show\\file.mkv' and the
    StorageRoots list [{'Id', 'Name', 'Prefix'}, ...] sorted by Prefix length
    descending, return (storage_root_id, relative_path). Returns (None, None)
    if no prefix matches."""
    if not CanonicalPath:
        return (None, None)
    Upper = CanonicalPath.upper()
    for Sr in StorageRoots:
        PrefUpper = Sr['Prefix'].upper()
        if Upper.startswith(PrefUpper):
            Rel = CanonicalPath[len(Sr['Prefix']):].replace('\\', '/').lstrip('/')
            return (Sr['Id'], Rel)
    return (None, None)


_STORAGE_ROOTS_CACHE = None


def LoadStorageRoots(Db=None, ForceReload: bool = False) -> list:
    """Convenience: load StorageRoots from DB sorted by prefix length DESC so
    Parse picks the longest match first. Cached at process scope (3-5 rows,
    rarely change). Pass ForceReload=True after schema changes."""
    global _STORAGE_ROOTS_CACHE
    if _STORAGE_ROOTS_CACHE is not None and not ForceReload:
        return _STORAGE_ROOTS_CACHE
    if Db is None:
        from Core.Database.DatabaseService import DatabaseService
        Db = DatabaseService()
    Rows = Db.ExecuteQuery(
        "SELECT Id, Name, CanonicalPrefix AS Prefix FROM StorageRoots "
        "ORDER BY length(CanonicalPrefix) DESC"
    )
    _STORAGE_ROOTS_CACHE = [{'Id': R['Id'], 'Name': R['Name'], 'Prefix': R['Prefix']} for R in Rows]
    return _STORAGE_ROOTS_CACHE


_PREFIX_BY_ID_CACHE = {}


def CanonicalFor(StorageRootId: int, RelativePath: str, Db=None) -> str:
    """Return the canonical Windows-shaped path (StorageRoots.CanonicalPrefix +
    RelativePath, joined with backslashes). For display in operator-facing
    surfaces (UI tables, logs, error messages). Cached per-process by
    StorageRootId. Workers should call Resolve for actual I/O, not this."""
    if StorageRootId is None or RelativePath is None:
        return ''
    if StorageRootId not in _PREFIX_BY_ID_CACHE:
        if Db is None:
            from Core.Database.DatabaseService import DatabaseService
            Db = DatabaseService()
        Rows = Db.ExecuteQuery(
            "SELECT CanonicalPrefix FROM StorageRoots WHERE Id = %s LIMIT 1",
            (StorageRootId,),
        )
        if not Rows:
            raise PathStorageError(f"StorageRoot Id={StorageRootId} not found")
        _PREFIX_BY_ID_CACHE[StorageRootId] = Rows[0]['CanonicalPrefix']
    Prefix = _PREFIX_BY_ID_CACHE[StorageRootId]
    Rel = (RelativePath or '').replace('/', '\\').lstrip('\\')
    return Prefix + Rel
