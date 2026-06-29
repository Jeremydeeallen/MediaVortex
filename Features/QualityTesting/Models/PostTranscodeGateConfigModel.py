from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class PostTranscodeGateConfigModel:
    """Single-row scalar config for the post-transcode disposition gate.

    Backed by `PostTranscodeGateConfig` table with `CHECK (Id = 1)`. Only one
    row exists. Adding a new tunable means adding a column, not a row.
    """
    Id: int = 1
    VmafAutoReplaceMinThreshold: float = 88.0
    VmafAutoReplaceMaxThreshold: float = 98.0
    WhenVmafUnavailable: str = "block"  # 'block' | 'bypass'
    QualityTestEnabled: bool = True  # operator master switch; FALSE = bypass VMAF for every successful transcode
    MaxRequeueAttempts: int = 3  # see perfect-solid-transcode-pipeline.C1 / C7
    WorkerHeartbeatWindowSec: int = 90  # see transcode-worker-unification.T25
    RetranscodeVmafThreshold: int = 80  # see transcode-worker-unification.T25
    LastUpdated: Optional[datetime] = None
