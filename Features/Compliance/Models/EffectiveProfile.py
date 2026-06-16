from dataclasses import dataclass
from typing import Optional

from Core.Resolution.ResolutionTier import ResolutionTier


@dataclass(frozen=True)
# directive: resolution-types | # see resolution-types.C6
class EffectiveProfile:
    """Resolved profile + thresholds the operations evaluate against -- caller does the cascade + ProfileThresholds lookup. TargetResolutionCategory is now a typed ResolutionTier (resolution-types.C6) -- no more string heterogeneity."""
    ProfileName: str
    TargetVideoKbps: Optional[int] = None
    TargetAudioKbps: Optional[int] = None
    TargetResolutionCategory: Optional[ResolutionTier] = None
