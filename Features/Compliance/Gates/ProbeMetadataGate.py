from typing import Optional
from Models.MediaFileModel import MediaFileModel
from Features.Compliance.Models.EffectiveProfile import EffectiveProfile
from Features.Compliance.Models.ComplianceGatesModel import ComplianceGatesModel
from Features.Compliance.Gates.IComplianceGate import IComplianceGate


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C6
class ProbeMetadataGate(IComplianceGate):
    """Hard-block: probe metadata missing (Codec or Resolution NULL) -- evaluator cannot reason about content."""

    Name = "ProbeMetadata"

    def IsEnabled(self, Gates: ComplianceGatesModel) -> bool:
        return Gates.RequireProbeMetadata

    def Blocks(self, Mf: MediaFileModel, Profile: Optional[EffectiveProfile]) -> bool:
        return (not Mf.Codec) or (not Mf.Resolution)
