from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class TranscodeQueueModel:
    """Represents a single transcoding job using TranscodeQueue table."""

    Id: Optional[int] = None
    StorageRootId: Optional[int] = None
    RelativePath: str = ""
    FilePath: str = ""  # Legacy column; populated via Resolve at construction. Dropped in Phase F.
    FileName: str = ""
    Directory: str = ""
    SizeBytes: int = 0
    SizeMB: float = 0.0
    Priority: int = 0
    Status: str = "Pending"  # Pending, Running, Completed, Failed, Cancelled
    AssignedProfile: str = ""  # Profile assigned for transcoding
    ProcessingMode: str = "Transcode"  # "Transcode" or "Remux"
    ClaimedBy: Optional[str] = None  # Worker hostname that claimed this job
    MediaFileId: Optional[int] = None  # FK to MediaFiles.Id
    DateAdded: Optional[datetime] = None
    DateStarted: Optional[datetime] = None
    TestVariantSetId: Optional[int] = None  # FK to TestVariantSets.Id; NULL = normal production transcode

    def __post_init__(self):
        if self.DateAdded is None:
            self.DateAdded = datetime.now(timezone.utc)
        if not self.FilePath and self.StorageRootId is not None and self.RelativePath:
            try:
                from Core.PathStorage import CanonicalFor
                self.FilePath = CanonicalFor(self.StorageRootId, self.RelativePath)
                if not self.FileName:
                    import os as _os
                    self.FileName = _os.path.basename(self.FilePath)
                if not self.Directory:
                    import os as _os
                    self.Directory = _os.path.dirname(self.FilePath)
            except Exception:
                pass

    @property
    def IsCompleted(self) -> bool:
        """Check if job is completed successfully."""
        return self.Status == "Completed"

    @property
    def IsFailed(self) -> bool:
        """Check if job has failed."""
        return self.Status == "Failed"

    @property
    def IsRunning(self) -> bool:
        """Check if job is currently running."""
        return self.Status == "Running"

    @property
    def IsPending(self) -> bool:
        """Check if job is pending execution."""
        return self.Status == "Pending"

    @property
    def IsCancelled(self) -> bool:
        """Check if job is cancelled."""
        return self.Status == "Cancelled"

    @property
    def DurationMinutes(self) -> Optional[float]:
        """Calculate job duration in minutes."""
        if self.DateStarted and self.IsCompleted:
            from Core.DateTimeHelpers import AsAwareUtc
            duration = datetime.now(timezone.utc) - AsAwareUtc(self.DateStarted)
            return duration.total_seconds() / 60.0
        return None

    @property
    def IsRemux(self) -> bool:
        """Check if this is a remux-class job.

        The post-2026-05-17 routing model collapses Remux + AudioFix into a
        single 'Quick' mode (see media-tabs-and-loudness.feature.md C15-C17,
        revised). Legacy 'Remux' and 'AudioFix' rows still dispatch through
        the same code path for in-flight backward compatibility.
        """
        return self.ProcessingMode in ("Quick", "Remux", "AudioFix")

    @property
    def IsSubtitleFix(self) -> bool:
        """Check if this is a subtitle fix job (ASS/SSA -> SRT conversion)."""
        return self.ProcessingMode == "SubtitleFix"

    @property
    def IsTestMode(self) -> bool:
        """Check if this row should run as a multi-variant test (does not replace source)."""
        return self.TestVariantSetId is not None

    @property
    def SizeGB(self) -> float:
        """Get file size in GB."""
        return self.SizeMB / 1024.0 if self.SizeMB > 0 else 0.0
