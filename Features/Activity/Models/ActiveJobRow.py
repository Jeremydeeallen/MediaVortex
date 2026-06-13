from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
# directive: activity-dashboard-solid | # see activity-dashboard-solid.C3
class ActiveJobRow:
    """One row in the Active Jobs panel. Sourced from ActiveJobs JOIN Workers (display name only) JOIN TranscodeAttempts on AttemptId. Worker.Status does NOT filter visibility. see activity-dashboard.ST4"""
    AttemptId: int
    MediaFileId: Optional[int]
    FileName: str
    WorkerName: Optional[str]
    ProfileName: Optional[str]
    SizeMB: Optional[float]
    ProgressPercent: Optional[int]
    SmoothedFPS: Optional[float]
    SmoothedSpeed: Optional[float]
    EtaSeconds: Optional[int]
    ServiceName: Optional[str] = None
    ClaimedAt: Optional[datetime] = None
    IsStale: bool = False
    Reasons: list = field(default_factory=list)
