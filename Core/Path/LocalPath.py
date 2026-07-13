import os
import platform
import re


_IS_WINDOWS = platform.system().lower() == 'windows'
_CANONICAL_DRIVE_RE = re.compile(r'^[A-Za-z]:[\\/]')


# directive: transcode-flow-canonical -- fail loud when a canonical drive-letter path lands in a local FS op on a non-Windows worker
def _AssertLocalShape(Value):
    if not Value or _IS_WINDOWS:
        return
    if _CANONICAL_DRIVE_RE.match(Value):
        raise ValueError(f"LocalPath op refused canonical drive-letter path on non-Windows worker: {Value!r}. Route through Path.FromLegacyString(...).Resolve(worker) first, or use the canonical-namespace helper (_CanonicalExists / _CanonicalGetSize).")


# directive: path-schema-migration | # see path.S3
def LocalBasename(Value):
    return os.path.basename(Value or "")


# directive: path-schema-migration | # see path.S3
def LocalDirname(Value):
    return os.path.dirname(Value or "")


# directive: path-schema-migration | # see path.S3
def LocalSplitExt(Value):
    return os.path.splitext(Value or "")


# directive: path-schema-migration | # see path.S3
def LocalJoin(Base, *Children):
    Cleaned = [str(C) for C in Children if C is not None and C != ""]
    return os.path.join(Base or "", *Cleaned)


# directive: transcode-flow-canonical
def LocalExists(Value):
    _AssertLocalShape(Value)
    return bool(Value) and os.path.exists(Value)


# directive: transcode-flow-canonical
def LocalIsFile(Value):
    _AssertLocalShape(Value)
    return bool(Value) and os.path.isfile(Value)


# directive: transcode-flow-canonical
def LocalIsDir(Value):
    _AssertLocalShape(Value)
    return bool(Value) and os.path.isdir(Value)


# directive: transcode-flow-canonical
def LocalGetSize(Value):
    _AssertLocalShape(Value)
    return os.path.getsize(Value)


# directive: transcode-flow-canonical
def LocalGetMTime(Value):
    _AssertLocalShape(Value)
    return os.path.getmtime(Value)


# directive: path-schema-migration | # see path.S3
def LocalNormCase(Value):
    return os.path.normcase(Value or "")


# directive: path-schema-migration | # see path.S3
def LocalSamePath(A, B):
    return os.path.normcase(A or "") == os.path.normcase(B or "")
