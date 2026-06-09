from typing import Optional
from Models.MediaFileModel import MediaFileModel
from Features.Compliance.Models.EffectiveProfile import EffectiveProfile
from Features.Compliance.Models.ComplianceGatesModel import ComplianceGatesModel
from Features.Compliance.Gates.IComplianceGate import IComplianceGate


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C6
class ProfileThresholdsGate(IComplianceGate):
    """Hard-block: no matching ProfileThresholds row for (Profile, ResolutionCategory) -- caller must look up thresholds; missing => Profile lacks TargetVideoKbps/TargetAudioKbps."""

    Name = "ProfileThresholds"

    def IsEnabled(self, Gates: ComplianceGatesModel) -> bool:
        return Gates.RequireProfileThresholds

    def Blocks(self, Mf: MediaFileModel, Profile: Optional[EffectiveProfile]) -> bool:
        if Profile is None:
            return True
        return Profile.TargetVideoKbps is None or Profile.TargetAudioKbps is None
