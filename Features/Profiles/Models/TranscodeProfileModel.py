from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
# directive: compliance-symmetry
class TranscodeProfileModel:

    Id: Optional[int] = None
    ProfileName: str = ""
    Description: str = ""
    CreatedDate: Optional[datetime] = None
    LastModified: Optional[datetime] = None

    Codec: str = "libsvtav1"
    Preset: int = 6
    FilmGrain: int = 10
    YadifMode: int = 1
    YadifParity: int = 1
    YadifDeint: int = 1
    UseNvidiaHardware: int = 0
    SortOrder: int = 0

    Draft: bool = True
    Active: bool = True
    StreamCodecName: Optional[str] = None
    TargetResolutionCategory: Optional[str] = None
    TargetVideoKbps: Optional[int] = None
    AllowUpscale: bool = False
    AudioCodec: Optional[str] = None
    TargetAudioKbps: Optional[int] = None
    Container: Optional[str] = None

    def __post_init__(self):
        if self.CreatedDate is None:
            self.CreatedDate = datetime.now(timezone.utc)
        if self.LastModified is None:
            self.LastModified = datetime.now(timezone.utc)
