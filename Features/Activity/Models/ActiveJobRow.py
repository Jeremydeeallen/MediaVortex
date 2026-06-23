from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
# directive: worker-runtime-state | # see activity.C2
class ActiveJobRow:
    """One row in the Active Jobs panel. see activity-dashboard.ST3"""
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
    ProcessingMode: Optional[str] = None
    SourceResolutionCategory: Optional[str] = None
    TargetResolutionCategory: Optional[str] = None
    SourceCodec: Optional[str] = None
    TargetCodec: Optional[str] = None
    EstimatedSavingsBytes: Optional[int] = None
