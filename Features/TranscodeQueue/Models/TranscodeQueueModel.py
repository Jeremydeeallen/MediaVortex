from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


# directive: path-schema-migration | # see path.S8
@dataclass
class TranscodeQueueModel:
    """Single transcode-queue row; typed pair (StorageRootId, RelativePath) is the canonical identity."""

    Id: Optional[int] = None
    StorageRootId: Optional[int] = None
    RelativePath: str = ""
    FileName: str = ""
    Directory: str = ""
    SizeBytes: int = 0
    SizeMB: float = 0.0
    Priority: int = 0
    Status: str = "Pending"
    AssignedProfile: str = ""
    ProcessingMode: str = "Transcode"
    ClaimedBy: Optional[str] = None
    MediaFileId: Optional[int] = None
    DateAdded: Optional[datetime] = None
    DateStarted: Optional[datetime] = None
    TestVariantSetId: Optional[int] = None

    # directive: path-schema-migration | # see path.S8
    def __post_init__(self):
        if self.DateAdded is None:
            self.DateAdded = datetime.now(timezone.utc)

    @property
    # directive: path-schema-migration | # see path.S8
    def PathObj(self):
        """Path object for the typed pair; raises PathError on invalid state."""
        from Core.Path.Path import Path
        return Path(self.StorageRootId, self.RelativePath or "")

    @property
    # directive: path-schema-migration | # see path.S8
    def FilePath(self) -> str:
        """Canonical display string; computed from typed pair via PathStorageRoots singleton."""
        if self.StorageRootId is None:
            return ""
        from Core.Path.Path import Path
        from Core.Path.PathStorageRoots import GetPrefixMap
        return Path(self.StorageRootId, self.RelativePath or "").CanonicalDisplay(GetPrefixMap())

    @property
    def IsCompleted(self) -> bool:
        return self.Status == "Completed"

    @property
    def IsFailed(self) -> bool:
        return self.Status == "Failed"

    @property
    def IsRunning(self) -> bool:
        return self.Status == "Running"

    @property
    def IsPending(self) -> bool:
        return self.Status == "Pending"

    @property
    def IsCancelled(self) -> bool:
        return self.Status == "Cancelled"

    @property
    def DurationMinutes(self) -> Optional[float]:
        if self.DateStarted and self.IsCompleted:
            from Core.DateTimeHelpers import AsAwareUtc
            duration = datetime.now(timezone.utc) - AsAwareUtc(self.DateStarted)
            return duration.total_seconds() / 60.0
        return None

    @property
    def IsRemux(self) -> bool:
        return self.ProcessingMode in ("Quick", "Remux", "AudioFix")

    @property
    def IsSubtitleFix(self) -> bool:
        return self.ProcessingMode == "SubtitleFix"

    @property
    def IsTestMode(self) -> bool:
        return self.TestVariantSetId is not None

    @property
    def SizeGB(self) -> float:
        return self.SizeMB / 1024.0 if self.SizeMB > 0 else 0.0
