from typing import Optional
from Models.MediaFileModel import MediaFileModel
from Features.Compliance.Models.EffectiveProfile import EffectiveProfile
from Features.Compliance.Models.ComplianceGatesModel import ComplianceGatesModel
from Features.Compliance.Gates.IComplianceGate import IComplianceGate


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C6
class EnglishAudioGate(IComplianceGate):
    """Hard-block: file has no explicit English audio stream -- existing audio-language safety guard."""

    Name = "EnglishAudio"

    def IsEnabled(self, Gates: ComplianceGatesModel) -> bool:
        return Gates.RequireExplicitEnglishAudio

    def Blocks(self, Mf: MediaFileModel, Profile: Optional[EffectiveProfile]) -> bool:
        return Mf.HasExplicitEnglishAudio is False
