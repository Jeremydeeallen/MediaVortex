from dataclasses import dataclass
from typing import Optional


@dataclass
class ContentClassificationRuleModel:
    Id: int
    Priority: int
    RuleName: str
    IsActive: bool
    AssignProfileName: str
    BitrateKbpsMin: Optional[int] = None
    BitrateKbpsMax: Optional[int] = None
    ResolutionCategory: Optional[str] = None
    CodecIn: Optional[str] = None
    MotionFractionMin: Optional[float] = None
    MotionFractionMax: Optional[float] = None
    SceneChangeRateMin: Optional[float] = None
    SceneChangeRateMax: Optional[float] = None
    LumaVarianceMin: Optional[float] = None
    LumaVarianceMax: Optional[float] = None
    FolderPathPattern: Optional[str] = None
    Description: Optional[str] = None
