from typing import Optional
from Models.MediaFileModel import MediaFileModel
from Features.Profiles.EffectiveProfile import EffectiveProfile
from Features.Compliance.Models.ComplianceGatesModel import ComplianceGatesModel
from Features.Compliance.Gates.IComplianceGate import IComplianceGate


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C6
class ResolutionCategoryGate(IComplianceGate):
    """Hard-block: ResolutionCategory cache missing on the MediaFiles row -- needed for ProfileThresholds lookup."""

    Name = "ResolutionCategory"

    def IsEnabled(self, Gates: ComplianceGatesModel) -> bool:
        return Gates.RequireResolutionCategory

    def Blocks(self, Mf: MediaFileModel, Profile: Optional[EffectiveProfile]) -> bool:
        return not Mf.ResolutionCategory
