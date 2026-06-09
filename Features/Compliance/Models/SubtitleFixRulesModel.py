from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class SubtitleFixRulesModel:
    """Single-row scalar config for the SubtitleFix compliance operation -- see compliance-solid-refactor.C5."""
    Id: int = 1
    Enabled: bool = False
    MovTextRequiredForMp4: bool = True
    NonNativeSubtitleFormatsCsv: str = "ass,ssa,vobsub"
    RequireForcedSubtitlesPresent: bool = True
    LastUpdated: Optional[datetime] = None
