from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class CrfBitrateEstimateModel:
    """One row of the (Codec, Resolution, Crf) -> EstimatedKbps lookup.

    Used by the marginal-savings gate to estimate output size when a profile
    is CRF-only (VideoBitrateKbps=0). Operator can edit on the /settings page;
    edits stamp Source='OperatorOverride'.
    """
    Id: Optional[int] = None
    Codec: str = ""
    Resolution: str = ""
    Crf: int = 0
    EstimatedKbps: int = 0
    LastUpdated: Optional[datetime] = None
    Source: Optional[str] = None
