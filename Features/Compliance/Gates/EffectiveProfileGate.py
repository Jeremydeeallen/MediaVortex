from typing import Optional
from Models.MediaFileModel import MediaFileModel
from Features.Compliance.Models.EffectiveProfile import EffectiveProfile
from Features.Compliance.Models.ComplianceGatesModel import ComplianceGatesModel
from Features.Compliance.Gates.IComplianceGate import IComplianceGate


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C6
class EffectiveProfileGate(IComplianceGate):
    """Hard-block: profile cascade did not resolve (Profile is None or ProfileName empty)."""

    Name = "EffectiveProfile"

    def IsEnabled(self, Gates: ComplianceGatesModel) -> bool:
        return Gates.RequireEffectiveProfile

    def Blocks(self, Mf: MediaFileModel, Profile: Optional[EffectiveProfile]) -> bool:
        return Profile is None or not Profile.ProfileName
