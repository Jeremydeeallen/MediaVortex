from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class AudioFixRulesModel:
    """Single-row scalar config for the AudioFix compliance operation -- see compliance-solid-refactor.C4."""
    Id: int = 1
    TargetLoudnessLufs: int = -23
    ToleranceLufs: float = 1.0
    RequireLufsMeasured: bool = True
    LastUpdated: Optional[datetime] = None
