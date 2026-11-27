# directive: target-policy-1a-tables | # see policy.S1 -- one MediaFileTargets row as a value; Optional only where NULL is a value (no ICQ, no ceiling, held-frame thresholds unseeded until target-policy-verification)
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
# directive: target-policy-1a-tables | # see policy.S1
class Target:
    MediaFileId: int
    StorageRootId: int
    Tier: int
    TierOrigin: str
    ContentClass: str
    ClassOrigin: str
    FrameRateClass: str
    SourceResolution: str
    TargetResolution: str
    TargetKbps: int
    IcqQ: Optional[int]
    QualityLabel: str
    QualityTestRequired: bool
    VmafMin: float
    VmafMax: Optional[float]
    HeldFrameDetectionThreshold: Optional[float]
    HeldFrameP25Min: Optional[float]
    HeldFrameMeanMin: Optional[float]
    LiveActionP10Min: Optional[float]
    AudioPolicyId: int
    OutputContainer: str
    AcceptableContainersCsv: str
    AcceptableAudioCodecsCsv: str
    CeilingMultiplier: float
    ReviewBeforeReplace: bool


@dataclass(frozen=True)
# directive: target-policy-1a-tables | # see policy.C4 -- the first missing input's name; consumers write NULL + this reason, never a default
class Undecided:
    MediaFileId: int
    Reason: str
