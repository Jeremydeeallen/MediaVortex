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


def LoadStorageRoots(Db=None) -> list:
    """Convenience: load StorageRoots from DB sorted by prefix length DESC so
    Parse picks the longest match first. Cached at process scope is fine but
    not necessary here -- 3-5 rows."""
    if Db is None:
        from Core.Database.DatabaseService import DatabaseService
        Db = DatabaseService()
    Rows = Db.ExecuteQuery(
        "SELECT Id, Name, CanonicalPrefix AS Prefix FROM StorageRoots "
        "ORDER BY length(CanonicalPrefix) DESC"
    )
    return [{'Id': R['Id'], 'Name': R['Name'], 'Prefix': R['Prefix']} for R in Rows]
