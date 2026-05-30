from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ContentSignalsModel:
    MotionFraction: Optional[float] = None
    SceneChangeRatePerMin: Optional[float] = None
    LumaVariance: Optional[float] = None
    ComputedAt: Optional[datetime] = None
