from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class QueueAdmissionConfigModel:
    """Single-row scalar config for the queue-admission gate.

    Backed by `QueueAdmissionConfig` table with `CHECK (Id = 1)` -- only one
    row exists. Adding a new tunable means adding a column, not a row.
    """
    Id: int = 1
    MinTranscodeSavingsMB: int = 150
    MissingEstimatePolicy: str = "admit"
    MinAudioBitrateKbpsMono: int = 64
    MinAudioBitrateKbpsStereo: int = 96
    MinAudioBitrateKbpsSurround: int = 128
    LastUpdated: Optional[datetime] = None
