from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class RemuxRulesModel:
    """Single-row scalar config for the Remux compliance operation -- see compliance-solid-refactor.C3."""
    Id: int = 1
    AcceptableContainersCsv: str = "mp4,mov,m4v"
    AcceptableAudioCodecsMp4Csv: str = "aac,ac3,eac3,mp3"
    RequireAudioNormalized: bool = True
    LastUpdated: Optional[datetime] = None
