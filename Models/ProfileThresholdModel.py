from dataclasses import dataclass
from typing import Optional


@dataclass
class ProfileThresholdModel:
    """Represents resolution-specific thresholds for a transcoding profile."""
    
    Id: Optional[int] = None
    ProfileId: int = 0
    Resolution: str = ""
    Under30MinMB: int = 0
    Under65MinMB: int = 0
    Over65MinMB: int = 0
    VideoBitrateKbps: int = 0
    AudioBitrateKbps: int = 0
    FallbackVideoBitrateKbps: int = 0
    FallbackAudioBitrateKbps: int = 0
    TranscodeDownTo: str = ""
    Quality: Optional[int] = None
    Grain: bool = False
    KeepSource: bool = False
    # Note: Codec field removed - now stored at profile level in TranscodeProfileModel
