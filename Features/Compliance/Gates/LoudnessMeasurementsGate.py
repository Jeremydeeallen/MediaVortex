from typing import Optional
from Models.MediaFileModel import MediaFileModel
from Features.Compliance.Models.EffectiveProfile import EffectiveProfile
from Features.Compliance.Models.ComplianceGatesModel import ComplianceGatesModel
from Features.Compliance.Gates.IComplianceGate import IComplianceGate


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C6
class LoudnessMeasurementsGate(IComplianceGate):
    """Hard-block: file might run loudnorm (AudioComplete is not True) but the four ebur128 measurements are not all present -- per linear-loudnorm.feature.md C9."""

    Name = "LoudnessMeasurements"

    def IsEnabled(self, Gates: ComplianceGatesModel) -> bool:
        return Gates.RequireLoudnessMeasurements

    def Blocks(self, Mf: MediaFileModel, Profile: Optional[EffectiveProfile]) -> bool:
        if Mf.AudioComplete is True:
            return False
        return (Mf.SourceIntegratedLufs is None
                or Mf.SourceLoudnessRangeLU is None
                or Mf.SourceTruePeakDbtp is None
                or Mf.SourceIntegratedThresholdLufs is None)
