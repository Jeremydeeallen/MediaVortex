from dataclasses import dataclass, field
from typing import Any, Dict, List

from Features.Activity.Models.ActiveJobRow import ActiveJobRow
from Features.Activity.Models.WorkerTile import WorkerTile


@dataclass(frozen=True)
# directive: worker-runtime-state | # see activity.C5
class DashboardSnapshot:
    """Single payload for the Activity dashboard. One round-trip per poll."""
    Workers: List[WorkerTile] = field(default_factory=list)
    ActiveJobs: List[ActiveJobRow] = field(default_factory=list)
    ActiveScans: List[Dict[str, Any]] = field(default_factory=list)
    QueueCounts: Dict[str, int] = field(default_factory=dict)
    BadgeState: Dict[str, int] = field(default_factory=dict)
    HungAttempts: List[Dict[str, Any]] = field(default_factory=list)
    StaleProgressThresholdSec: int = 15
    HeartbeatStaleThresholdSec: int = 300
