from typing import Optional
from Models.MediaFileModel import MediaFileModel
from Features.Profiles.EffectiveProfile import EffectiveProfile
from Features.Compliance.Models.ComplianceGatesModel import ComplianceGatesModel
from Features.Compliance.Gates.IComplianceGate import IComplianceGate


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C6
class AudioStreamGate(IComplianceGate):
    """Hard-block: probed file with no audio stream (HasExplicitEnglishAudio resolved + AudioCodec NULL + Resolution present)."""

    Name = "AudioStream"

    def IsEnabled(self, Gates: ComplianceGatesModel) -> bool:
        return Gates.RequireAudioStream

    def Blocks(self, Mf: MediaFileModel, Profile: Optional[EffectiveProfile]) -> bool:
        return (Mf.HasExplicitEnglishAudio is not None and not Mf.AudioCodec and bool(Mf.Resolution))
