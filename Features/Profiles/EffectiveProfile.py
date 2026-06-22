from dataclasses import dataclass
from typing import Optional

from Core.Resolution.ResolutionTier import ResolutionTier


@dataclass(frozen=True)
# directive: compliance-symmetry
class EffectiveProfile:
    """Resolved profile + compliance bar fields the verticals evaluate against. Carries both the per-source-resolution encoder targets (TargetVideoKbps/TargetAudioKbps from ProfileThresholds) and the per-profile compliance bar (StreamCodecName, AllowUpscale, AudioCodec, Container)."""
    ProfileName: str
    TargetVideoKbps: Optional[int] = None
    TargetAudioKbps: Optional[int] = None
    TargetResolutionCategory: Optional[ResolutionTier] = None
    StreamCodecName: Optional[str] = None
    AllowUpscale: bool = False
    AudioCodec: Optional[str] = None
    Container: Optional[str] = None
