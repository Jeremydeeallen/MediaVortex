from dataclasses import dataclass, field
from typing import Dict, List

from Features.Activity.Models.ActiveJobRow import ActiveJobRow
from Features.Activity.Models.WorkerTile import WorkerTile


@dataclass(frozen=True)
# directive: activity-dashboard-solid | # see activity-dashboard-solid.C1
class DashboardSnapshot:
    """Single payload for the Activity dashboard. One round-trip per poll."""
    Workers: List[WorkerTile] = field(default_factory=list)
    ActiveJobs: List[ActiveJobRow] = field(default_factory=list)
    QueueCounts: Dict[str, int] = field(default_factory=dict)
    BadgeState: Dict[str, int] = field(default_factory=dict)
    StaleProgressThresholdSec: int = 15
    HeartbeatStaleThresholdSec: int = 300
