from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class TranscodeRulesModel:
    """Single-row scalar config for the Transcode compliance operation -- see compliance-solid-refactor.C2."""
    Id: int = 1
    ResolutionExceedsProfileTarget: bool = True
    AcceptableVideoCodecsCsv: str = "h264,hevc,av1"
    EstimatedSavingsMBThreshold: int = 150
    PreventUpscale: bool = True
    LastUpdated: Optional[datetime] = None
