from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ComplianceGatesModel:
    """Single-row scalar config for the 8 compliance gates -- see compliance-solid-refactor.C6."""
    Id: int = 1
    RequireExplicitEnglishAudio: bool = True
    BlockOnAudioCorruptSuspect: bool = True
    RequireAudioStream: bool = True
    RequireLoudnessMeasurements: bool = True
    RequireProbeMetadata: bool = True
    RequireEffectiveProfile: bool = True
    RequireResolutionCategory: bool = True
    RequireProfileThresholds: bool = True
    BlockOnAudioPolicyDeferred: bool = True
    LastUpdated: Optional[datetime] = None
