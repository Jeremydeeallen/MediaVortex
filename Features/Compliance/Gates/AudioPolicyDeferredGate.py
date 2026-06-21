from typing import Optional

from Models.MediaFileModel import MediaFileModel
from Features.Profiles.EffectiveProfile import EffectiveProfile
from Features.Compliance.Models.ComplianceGatesModel import ComplianceGatesModel
from Features.Compliance.Gates.IComplianceGate import IComplianceGate


# directive: audio-vertical-compliance-and-activity | # see audio-normalization.C6
class AudioPolicyDeferredGate(IComplianceGate):
    """Hard-block: AdmissionDeferReason set by the audio-normalization vertical (invalid measurement, ungainable, operator review pending, awaiting speech enrichment)."""

    Name = "AudioPolicyDeferred"

    # directive: audio-vertical-compliance-and-activity | # see audio-normalization.C6
    def IsEnabled(self, Gates: ComplianceGatesModel) -> bool:
        """Read ComplianceGates.BlockOnAudioPolicyDeferred; operator can disable per db-is-authority."""
        return getattr(Gates, 'BlockOnAudioPolicyDeferred', True)

    # directive: audio-vertical-compliance-and-activity | # see audio-normalization.C6
    def Blocks(self, Mf: MediaFileModel, Profile: Optional[EffectiveProfile]) -> bool:
        """True when MediaFiles.AdmissionDeferReason is set; vertical owns the disposition."""
        Reason = getattr(Mf, 'AdmissionDeferReason', None)
        return Reason is not None and str(Reason).strip() != ''
