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
