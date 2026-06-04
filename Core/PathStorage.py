"""Path storage canonical layer.

The single Resolve function used by all I/O code in Phase 4+. Takes
(StorageRootId, RelativePath, WorkerName) and returns the worker-local
absolute path. No drive-letter parsing, no regex, no string substitutions
against legacy WorkerShareMappings.

This file is the < 50 LOC contract from path-storage.feature.md criterion 4.
Keep it small. Resolve and Parse are the entire surface.
"""

import os
import posixpath
import ntpath
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


# directive: paths-canonical-completion  # see path-storage.C4
def LastSegment(PathValue):
    """Trailing path segment (filename) for any shape: UNC, Windows-drive, POSIX."""
    if not PathValue:
        return ""
    Idx = max(PathValue.rfind('/'), PathValue.rfind('\\'))
    return PathValue[Idx + 1:] if Idx >= 0 else PathValue


# directive: paths-canonical-completion  # see path-storage.C4
def ParentDir(PathValue):
    """Everything before the last separator; shape-preserving. Empty if no separator."""
    if not PathValue:
        return ""
    Idx = max(PathValue.rfind('/'), PathValue.rfind('\\'))
    return PathValue[:Idx] if Idx >= 0 else ""


# directive: paths-canonical-completion  # see path-storage.C4
def Join(BasePath, ChildSegment):
    """Append child segment to base path; preserves base's separator shape (defaults to '/')."""
    if not BasePath:
        return ChildSegment or ""
    if not ChildSegment:
        return BasePath
    LastFwd = BasePath.rfind('/')
    LastBack = BasePath.rfind('\\')
    if LastFwd < 0 and LastBack < 0:
        Sep = '\\' if (len(BasePath) >= 2 and BasePath[1] == ':') else '/'
    elif LastFwd > LastBack:
        Sep = '/'
    else:
        Sep = '\\'
    return BasePath.rstrip('/\\') + Sep + ChildSegment.lstrip('/\\')


# directive: paths-canonical-completion  # see path-storage.C4
def SplitExt(PathValue):
    """Return (root, ext) where ext starts with '.'. Shape-preserving on root."""
    if not PathValue:
        return ("", "")
    SepIdx = max(PathValue.rfind('/'), PathValue.rfind('\\'))
    DotIdx = PathValue.rfind('.')
    if DotIdx <= SepIdx or DotIdx < 0:
        return (PathValue, "")
    return (PathValue[:DotIdx], PathValue[DotIdx:])


# directive: paths-canonical-completion  # see path-storage.C4
def ToLocal(CanonicalPath, WorkerName, Db=None):
    """Parse canonical path -> resolve to worker-local absolute path string."""
    if not CanonicalPath:
        return ""
    StorageRoots = LoadStorageRoots(Db)
    StorageRootId, RelativePath = Parse(CanonicalPath, StorageRoots)
    if StorageRootId is None:
        return CanonicalPath
    return Resolve(StorageRootId, RelativePath, WorkerName, Db)


# directive: paths-canonical-completion  # see path-storage.C4
def Exists(CanonicalPath, WorkerName, Db=None):
    """True iff the canonical path resolves to an existing local path on WorkerName."""
    Local = ToLocal(CanonicalPath, WorkerName, Db)
    return os.path.exists(Local) if Local else False


# directive: paths-canonical-completion  # see path-storage.C4
def IsFile(CanonicalPath, WorkerName, Db=None):
    """True iff the canonical path resolves to an existing local file on WorkerName."""
    Local = ToLocal(CanonicalPath, WorkerName, Db)
    return os.path.isfile(Local) if Local else False


# directive: paths-canonical-completion  # see path-storage.C4
def IsDir(CanonicalPath, WorkerName, Db=None):
    """True iff the canonical path resolves to an existing local directory on WorkerName."""
    Local = ToLocal(CanonicalPath, WorkerName, Db)
    return os.path.isdir(Local) if Local else False


# directive: paths-canonical-completion  # see path-storage.C4
def GetSize(CanonicalPath, WorkerName, Db=None):
    """File size in bytes; raises FileNotFoundError if missing."""
    Local = ToLocal(CanonicalPath, WorkerName, Db)
    return os.path.getsize(Local)


# directive: paths-canonical-completion  # see path-storage.C4
def GetMTime(CanonicalPath, WorkerName, Db=None):
    """Modification time as POSIX timestamp; raises FileNotFoundError if missing."""
    Local = ToLocal(CanonicalPath, WorkerName, Db)
    return os.path.getmtime(Local)


# directive: paths-canonical-completion  # see path-storage.C4
def LocalExists(LocalPath):
    """True iff the local-machine path exists. Caller asserts path is local, not canonical."""
    return os.path.exists(LocalPath) if LocalPath else False


# directive: paths-canonical-completion  # see path-storage.C4
def LocalIsFile(LocalPath):
    """True iff the local-machine path is an existing file."""
    return os.path.isfile(LocalPath) if LocalPath else False


# directive: paths-canonical-completion  # see path-storage.C4
def LocalIsDir(LocalPath):
    """True iff the local-machine path is an existing directory."""
    return os.path.isdir(LocalPath) if LocalPath else False


# directive: paths-canonical-completion  # see path-storage.C4
def LocalGetSize(LocalPath):
    """File size of a local-machine path; raises FileNotFoundError if missing."""
    return os.path.getsize(LocalPath)


# directive: paths-canonical-completion  # see path-storage.C4
def LocalGetMTime(LocalPath):
    """Modification time of a local-machine path; raises FileNotFoundError if missing."""
    return os.path.getmtime(LocalPath)


_WIN_DRIVE_RX = re.compile(r'^[A-Za-z]:')


# directive: paths-normalize-completion  # see path-storage.C4
def _PickPathFlavor(PathValue):
    """Return ntpath for UNC/Windows-drive/backslash-only inputs, posixpath otherwise."""
    if not PathValue:
        return posixpath
    if PathValue.startswith('\\\\') or PathValue.startswith('//'):
        return ntpath
    if _WIN_DRIVE_RX.match(PathValue):
        return ntpath
    if '\\' in PathValue and '/' not in PathValue:
        return ntpath
    return posixpath


# directive: paths-normalize-completion  # see path-storage.C4
def Normalize(PathValue):
    """Shape-preserving normalization: collapses //, .., .; keeps UNC \\\\server\\share root; does not lowercase."""
    if not PathValue:
        return PathValue or ""
    Flavor = _PickPathFlavor(PathValue)
    return Flavor.normpath(PathValue)


# directive: paths-normalize-completion  # see path-storage.C4
def PathsEqual(A, B, case_insensitive=None):
    """Path equality after Normalize; case sensitivity auto-detects from shape (UNC/Windows-drive => True, POSIX => False) unless overridden."""
    NormA = Normalize(A or "")
    NormB = Normalize(B or "")
    if case_insensitive is None:
        Flavor = _PickPathFlavor(A or B or "")
        case_insensitive = (Flavor is ntpath)
    if case_insensitive:
        return NormA.lower() == NormB.lower()
    return NormA == NormB
