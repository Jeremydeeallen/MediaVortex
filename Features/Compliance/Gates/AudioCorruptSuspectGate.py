from typing import Optional
from Models.MediaFileModel import MediaFileModel
from Features.Compliance.Models.EffectiveProfile import EffectiveProfile
from Features.Compliance.Models.ComplianceGatesModel import ComplianceGatesModel
from Features.Compliance.Gates.IComplianceGate import IComplianceGate


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C6
class AudioCorruptSuspectGate(IComplianceGate):
    """Hard-block: AudioCompletionService flagged this row as suspect (no_audio_stream / incompatible_codec_unsupported)."""

    Name = "AudioCorruptSuspect"

    def IsEnabled(self, Gates: ComplianceGatesModel) -> bool:
        return Gates.BlockOnAudioCorruptSuspect

    def Blocks(self, Mf: MediaFileModel, Profile: Optional[EffectiveProfile]) -> bool:
        return Mf.AudioCorruptSuspect is True
