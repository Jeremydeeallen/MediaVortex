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
    LastUpdated: Optional[datetime] = None
