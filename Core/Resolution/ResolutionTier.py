from dataclasses import dataclass


@dataclass(frozen=True)
# directive: resolution-types | # see resolution-types.C2
class ResolutionTier:
    """Single tier in the resolution-tier table. Loaded from DB by ResolutionTierRegistry (data-driven per resolution-types.C13). No hardcoded thresholds in code."""
    Name: str
    MinLongEdge: int
    CanonicalWidth: int
    CanonicalHeight: int
    Rank: int
