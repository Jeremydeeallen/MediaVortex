from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Protocol, Tuple
import os
import re


# directive: path-class-implementation | # see path.C4
class PathError(Exception):
    """Raised by Path construction, parsing, and resolution failures."""


# directive: path-class-implementation | # see path.S3
class Worker(Protocol):
    """Structural protocol Path.Resolve consumes; concrete class lands in v2-substrate-buildout."""

    Name: str
    Platform: str

    # directive: path-class-implementation | # see path.S3
    def ResolveStorageRoot(self, StorageRootId: int) -> Optional[str]: ...


_DOTDOT_RX = re.compile(r"(?:^|/)\.\.(?:$|/)")
_DRIVE_PREFIX_RX = re.compile(r"^[A-Za-z]:")
_BACKSLASH_TO_FORWARD = str.maketrans("\\", "/")
_FORWARD_TO_BACKSLASH = str.maketrans("/", "\\")
_CONTROL_CHARS_RX = re.compile(r"[\x00-\x1f\x7f]")
_WIN32_NAMESPACE_RX = re.compile(r"^[\\/][\\/][?.][\\/]")
_UNC_PREFIX_RX = re.compile(r"^[\\/][\\/]")
_DOS_DEVICE_NAMES = frozenset({
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
})


@dataclass(frozen=True, slots=True)
# directive: path-performance-budget | # see path.C1
class Path:
    """Canonical typed path for MediaVortex v2; see Core/Path/path.feature.md."""

    StorageRootId: int
    RelativePath: str

    # directive: path-security-audit | # see path.C4
    def __post_init__(self):
        """Validate constructor inputs and normalize RelativePath per D9."""
        Sid = self.StorageRootId
        Rel = self.RelativePath
        if Sid is None or isinstance(Sid, bool) or not isinstance(Sid, int):
            raise PathError(f"StorageRootId must be int, got {type(Sid).__name__}: {Sid!r}")
        if Rel is None or not isinstance(Rel, str):
            raise PathError(f"RelativePath must be str, got {type(Rel).__name__}: {Rel!r}")
        if Rel == "":
            return
        if _CONTROL_CHARS_RX.search(Rel):
            raise PathError(f"RelativePath contains NUL or control character: {Rel!r}")
        if _WIN32_NAMESPACE_RX.match(Rel):
            raise PathError(f"RelativePath uses Win32 device namespace prefix: {Rel!r}")
        if _UNC_PREFIX_RX.match(Rel):
            raise PathError(f"RelativePath must not start with separator: {Rel!r}")
        if Rel[0] in ("/", "\\"):
            raise PathError(f"RelativePath must not start with separator: {Rel!r}")
        if _DRIVE_PREFIX_RX.match(Rel):
            raise PathError(f"RelativePath must not start with drive-letter prefix: {Rel!r}")
        Norm = Rel.translate(_BACKSLASH_TO_FORWARD)
        if _DOTDOT_RX.search(Norm):
            raise PathError(f"RelativePath must not contain '..' segments: {Rel!r}")
        if Norm != Rel:
            object.__setattr__(self, "RelativePath", Norm)

    @classmethod
    # directive: path-class-implementation | # see path.S1
    def FromPair(cls, StorageRootId: int, RelativePath: str) -> "Path":
        """Construct via explicit-named-args call site; equivalent to Path(...)."""
        return cls(StorageRootId, RelativePath)

    @classmethod
    # directive: path-class-implementation | # see path.S1
    def FromRow(cls, Row, Prefix: str = "") -> Optional["Path"]:
        """Read <Prefix>StorageRootId / <Prefix>RelativePath from a dict-like row; None if either NULL."""
        SidKey = f"{Prefix}StorageRootId"
        RelKey = f"{Prefix}RelativePath"
        if hasattr(Row, "get"):
            Sid = Row.get(SidKey)
            Rel = Row.get(RelKey)
        else:
            Sid = Row[SidKey] if SidKey in Row else None
            Rel = Row[RelKey] if RelKey in Row else None
        if Sid is None or Rel is None:
            return None
        return cls(Sid, Rel)

    @classmethod
    # directive: path-class-implementation | # see path.S6
    def FromLegacyString(cls, Canonical: str, StorageRoots: list) -> "Path":
        """Parse a v1-shape canonical string against pre-sorted StorageRoots; raise PathError on no match (D10)."""
        if not Canonical or not isinstance(Canonical, str):
            raise PathError(f"FromLegacyString: empty or non-str input: {Canonical!r}")
        Upper = Canonical.upper()
        for Sr in StorageRoots:
            Prefix = Sr.get("CanonicalPrefix") if hasattr(Sr, "get") else Sr["CanonicalPrefix"]
            Id = Sr.get("Id") if hasattr(Sr, "get") else Sr["Id"]
            if Prefix is None:
                continue
            if Upper.startswith(Prefix.upper()):
                Tail = Canonical[len(Prefix):]
                if Tail == "":
                    return cls(Id, "")
                Norm = Tail.translate(_BACKSLASH_TO_FORWARD)
                while Norm.startswith("/"):
                    Norm = Norm[1:]
                return cls(Id, Norm)
        raise PathError(f"FromLegacyString: no matching prefix for {Canonical!r}")

    @classmethod
    # directive: path-class-implementation | # see path.S2
    def FromJsonDict(cls, Payload: dict) -> "Path":
        """Inverse of ToJsonDict; raises PathError on shape mismatch."""
        if not isinstance(Payload, dict):
            raise PathError(f"FromJsonDict: payload not a dict: {type(Payload).__name__}")
        if "StorageRootId" not in Payload or "RelativePath" not in Payload:
            raise PathError(f"FromJsonDict: missing keys; have {sorted(Payload.keys())!r}")
        return cls(Payload["StorageRootId"], Payload["RelativePath"])

    # directive: path-class-implementation | # see path.S2
    def ToJsonDict(self) -> dict:
        """Serialize to {'StorageRootId': int, 'RelativePath': str}; round-trips through FromJsonDict (C7)."""
        return {"StorageRootId": self.StorageRootId, "RelativePath": self.RelativePath}

    # directive: path-class-implementation | # see path.S8
    def CanonicalDisplay(self, Prefixes: dict) -> str:
        """Render human display from a pre-loaded prefix map; orphan id renders as '[orphan #<id>] <rel>'."""
        if self.StorageRootId not in Prefixes:
            return f"[orphan #{self.StorageRootId}] {self.RelativePath}"
        Prefix = Prefixes[self.StorageRootId]
        Tail = self.RelativePath.translate(_FORWARD_TO_BACKSLASH)
        return Prefix + Tail

    # directive: path-class-implementation | # see path.S4
    def __repr__(self) -> str:
        """Stable shape '<Path #<id>:<rel>>'; no DB lookup (D7)."""
        return f"<Path #{self.StorageRootId}:{self.RelativePath}>"

    # directive: path-class-implementation | # see path.S4
    def __str__(self) -> str:
        """Same as __repr__ (D8); no implicit DB call on string coercion."""
        return self.__repr__()

    # directive: path-class-implementation | # see path.C12
    def ParentDir(self) -> "Path":
        """Parent within the same StorageRoot; raises PathError at root (C13)."""
        if self.RelativePath == "":
            raise PathError("ParentDir: at root, no parent")
        Idx = self.RelativePath.rfind("/")
        if Idx < 0:
            return Path(self.StorageRootId, "")
        return Path(self.StorageRootId, self.RelativePath[:Idx])

    # directive: path-class-implementation | # see path.C12
    def LastSegment(self) -> str:
        """Trailing segment (filename or terminal dir name); empty only when RelativePath is empty."""
        if self.RelativePath == "":
            return ""
        Idx = self.RelativePath.rfind("/")
        if Idx < 0:
            return self.RelativePath
        return self.RelativePath[Idx + 1:]

    # directive: path-class-implementation | # see path.C14
    def SplitExt(self) -> Tuple["Path", str]:
        """Return (Path-without-ext, '.ext'); extensionless input or root returns (self, '')."""
        Rel = self.RelativePath
        if Rel == "":
            return (self, "")
        SepIdx = Rel.rfind("/")
        DotIdx = Rel.rfind(".")
        if DotIdx < 0 or DotIdx <= SepIdx:
            return (self, "")
        if DotIdx == SepIdx + 1:
            return (self, "")
        return (Path(self.StorageRootId, Rel[:DotIdx]), Rel[DotIdx:])

    # directive: path-class-implementation | # see path.C12
    def Join(self, Child: str) -> "Path":
        """Append child segment with forward slash; raises PathError on '..' / absolute markers."""
        if not isinstance(Child, str):
            raise PathError(f"Join: child must be str, got {type(Child).__name__}")
        if Child == "":
            return self
        if Child[0] in ("/", "\\"):
            raise PathError(f"Join: child has leading separator: {Child!r}")
        if _DRIVE_PREFIX_RX.match(Child):
            raise PathError(f"Join: child has drive letter: {Child!r}")
        Norm = Child.translate(_BACKSLASH_TO_FORWARD)
        if _DOTDOT_RX.search(Norm):
            raise PathError(f"Join: child contains '..' segment: {Child!r}")
        if self.RelativePath == "":
            return Path(self.StorageRootId, Norm)
        return Path(self.StorageRootId, self.RelativePath + "/" + Norm)

    # directive: path-security-audit | # see path.C7
    def _RejectWindowsHazards(self) -> None:
        """Raise PathError if RelativePath contains a Windows-worker hazard (DOS name, trailing dot/space, mid-segment colon)."""
        if self.RelativePath == "":
            return
        for Seg in self.RelativePath.split("/"):
            if Seg == "":
                continue
            DotIdx = Seg.rfind(".")
            Stem = Seg[:DotIdx] if DotIdx > 0 else Seg
            if Stem.upper() in _DOS_DEVICE_NAMES:
                raise PathError(f"Resolve: segment matches Windows DOS device name: {Seg!r} (in {self.RelativePath!r})")
            if Seg.endswith(".") or Seg.endswith(" "):
                raise PathError(f"Resolve: segment has trailing dot or space (unsafe on Windows): {Seg!r}")
            if ":" in Seg:
                raise PathError(f"Resolve: segment contains colon (NTFS alternate data stream marker): {Seg!r}")

    # directive: path-security-audit | # see path.C8
    def Resolve(self, Worker) -> str:
        """Worker-local absolute path string; raises PathError when StorageRoot is orphaned (C9, D4) or platform hazards present (C7-C9)."""
        Prefix = Worker.ResolveStorageRoot(self.StorageRootId)
        if Prefix is None:
            raise PathError(
                f"Resolve: no active StorageRoot for Id={self.StorageRootId} on worker={getattr(Worker, 'Name', '?')!r}"
            )
        Platform = getattr(Worker, "Platform", "")
        if Platform == "windows":
            self._RejectWindowsHazards()
            Tail = self.RelativePath.translate(_FORWARD_TO_BACKSLASH)
            Sep = "\\"
        else:
            Tail = self.RelativePath
            Sep = "/"
        if Tail == "":
            return Prefix
        if Prefix.endswith("/") or Prefix.endswith("\\"):
            return Prefix + Tail
        return Prefix + Sep + Tail

