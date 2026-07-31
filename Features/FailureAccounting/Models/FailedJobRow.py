from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# directive: failure-accounting | # see failure-accounting.C7
@dataclass(frozen=True)
# directive: failure-accounting | # see failure-accounting.C7
class FailedJobRow:
    """One row on the /FailedJobs surface -- enough for sort + display without joining at render time."""
    MediaFileId: int
    FileName: str
    FilePath: str
    FailureCount: int
    LastErrorMessage: Optional[str]
    LastAttemptDate: Optional[datetime]
    AssignedProfile: Optional[str]
    LastWorkerName: Optional[str]
    SizeMB: Optional[float] = field(default=None)
    LastFailureResetAt: Optional[datetime] = field(default=None)
    # directive: audio-preencode-progress -- pickup-to-delivery clock time for this MediaFile's failure window (MAX(AttemptDate) - MIN(AttemptDate) across the counted failures), formatted hh:mm:ss (HHH:MM:SS at >= 100 hours). None when < 2 attempts to span.
    Duration: Optional[str] = field(default=None)
