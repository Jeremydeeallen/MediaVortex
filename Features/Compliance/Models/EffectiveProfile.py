from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class EffectiveProfile:
    """Resolved profile + thresholds the operations evaluate against -- caller does the cascade + ProfileThresholds lookup."""
    ProfileName: str
    TargetVideoKbps: Optional[int] = None
    TargetAudioKbps: Optional[int] = None
    TargetResolutionCategory: Optional[str] = None
