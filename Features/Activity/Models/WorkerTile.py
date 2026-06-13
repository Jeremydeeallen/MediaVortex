from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
# directive: activity-dashboard-solid | # see activity-dashboard-solid.C4
class WorkerTile:
    """One worker tile on the Activity page. Two-axis: Status (operator-set) + HeartbeatAgeSec (derived connectivity). Decoupled per AC5."""
    WorkerName: str
    Status: str
    LastHeartbeat: Optional[datetime]
    HeartbeatAgeSec: Optional[int]
    TranscodeEnabled: bool = False
    RemuxEnabled: bool = False
    QualityTestEnabled: bool = False
    ScanEnabled: bool = False
    AcceptsInterlaced: bool = True
    nvenccapable: bool = False
    MaxConcurrentJobs: int = 1
