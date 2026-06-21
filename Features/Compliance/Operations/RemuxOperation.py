from typing import Optional
from Models.MediaFileModel import MediaFileModel
from Features.Profiles.EffectiveProfile import EffectiveProfile
from Features.Compliance.Models.OperationResult import OperationResult
from Features.Compliance.Models.RemuxRulesModel import RemuxRulesModel
from Features.Compliance.Operations.IComplianceOperation import IComplianceOperation


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C3
class RemuxOperation(IComplianceOperation):
    """Remux operation predicate -- evaluates container + audio-codec + normalization rules."""

    Name = "Remux"

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C3
    def Apply(self, Mf: MediaFileModel, Profile: EffectiveProfile, Rules: RemuxRulesModel) -> OperationResult:
        """Apply each RemuxRule predicate; return Applies=True if any predicate triggers."""
        Reasons = []
        Applies = False

        AcceptableContainers = self._ParseCsv(Rules.AcceptableContainersCsv)
        ContainerRaw = (Mf.ContainerFormat or '').lower()
        ContainerParts = {Tok.strip() for Tok in ContainerRaw.split(',') if Tok.strip()}
        if ContainerParts and not (ContainerParts & AcceptableContainers):
            Reasons.append({'Rule': 'AcceptableContainersCsv', 'Operator': 'NOT IN', 'Actual': sorted(ContainerParts), 'Threshold': sorted(AcceptableContainers), 'Outcome': 'applies'})
            Applies = True

        AcceptableAudio = self._ParseCsv(Rules.AcceptableAudioCodecsMp4Csv)
        AudioCodec = (Mf.AudioCodec or '').lower()
        if AudioCodec and AudioCodec not in AcceptableAudio:
            Reasons.append({'Rule': 'AcceptableAudioCodecsMp4Csv', 'Operator': 'NOT IN', 'Actual': AudioCodec, 'Threshold': sorted(AcceptableAudio), 'Outcome': 'applies'})
            Applies = True

        if Rules.RequireAudioNormalized and Mf.AudioComplete is not True:
            Reasons.append({'Rule': 'RequireAudioNormalized', 'Operator': '!= True', 'Actual': Mf.AudioComplete, 'Threshold': True, 'Outcome': 'applies'})
            Applies = True

        return OperationResult(OperationName=self.Name, Applies=Applies, Reasons=Reasons)

    @staticmethod
    def _ParseCsv(Csv: Optional[str]) -> set:
        if not Csv:
            return set()
        return {Tok.strip().lower() for Tok in Csv.split(',') if Tok.strip()}
