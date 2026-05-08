from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class TranscodeQueueModel:
    """Represents a single transcoding job using TranscodeQueue table."""

    Id: Optional[int] = None
    FilePath: str = ""
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

    def __post_init__(self):
        if self.DateAdded is None:
            self.DateAdded = datetime.now(timezone.utc)

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
            duration = datetime.now(timezone.utc) - self.DateStarted
            return duration.total_seconds() / 60.0
        return None

    @property
    def IsRemux(self) -> bool:
        """Check if this is a remux (compatibility-only) job."""
        return self.ProcessingMode == "Remux"

    @property
    def IsSubtitleFix(self) -> bool:
        """Check if this is a subtitle fix job (ASS/SSA -> SRT conversion)."""
        return self.ProcessingMode == "SubtitleFix"

    @property
    def SizeGB(self) -> float:
        """Get file size in GB."""
        return self.SizeMB / 1024.0 if self.SizeMB > 0 else 0.0
