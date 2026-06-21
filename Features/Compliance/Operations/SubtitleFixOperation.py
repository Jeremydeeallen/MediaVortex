from typing import Optional
from Models.MediaFileModel import MediaFileModel
from Features.Profiles.EffectiveProfile import EffectiveProfile
from Features.Compliance.Models.OperationResult import OperationResult
from Features.Compliance.Models.SubtitleFixRulesModel import SubtitleFixRulesModel
from Features.Compliance.Operations.IComplianceOperation import IComplianceOperation


_MP4_CONTAINERS = {'mp4', 'mov', 'm4v'}


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C5
class SubtitleFixOperation(IComplianceOperation):
    """SubtitleFix operation predicate -- forced-subs in MP4 with non-mov_text format; Enabled=False short-circuits."""

    Name = "SubtitleFix"

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C5
    def Apply(self, Mf: MediaFileModel, Profile: EffectiveProfile, Rules: SubtitleFixRulesModel) -> OperationResult:
        """Apply the SubtitleFix predicate; respects Enabled + RequireForcedSubtitlesPresent + MovTextRequiredForMp4 knobs."""
        Reasons = []

        if not Rules.Enabled:
            Reasons.append({'Rule': 'Enabled', 'Operator': 'IS', 'Actual': False, 'Threshold': True, 'Outcome': 'skip'})
            return OperationResult(OperationName=self.Name, Applies=False, Reasons=Reasons)

        ContainerRaw = (Mf.ContainerFormat or '').lower()
        ContainerParts = {Tok.strip() for Tok in ContainerRaw.split(',') if Tok.strip()}
        IsMp4Family = bool(ContainerParts & _MP4_CONTAINERS)
        if Rules.MovTextRequiredForMp4 and not IsMp4Family:
            Reasons.append({'Rule': 'MovTextRequiredForMp4', 'Operator': 'container NOT IN mp4 family', 'Actual': sorted(ContainerParts), 'Threshold': sorted(_MP4_CONTAINERS), 'Outcome': 'skip'})
            return OperationResult(OperationName=self.Name, Applies=False, Reasons=Reasons)

        NonNative = self._ParseCsv(Rules.NonNativeSubtitleFormatsCsv)
        SubFormats = self._ParseCsv(Mf.SubtitleFormats or '')
        HasIncompatible = bool(SubFormats & NonNative)
        if not HasIncompatible:
            Reasons.append({'Rule': 'NonNativeSubtitleFormatsCsv', 'Operator': 'no overlap', 'Actual': sorted(SubFormats), 'Threshold': sorted(NonNative), 'Outcome': 'skip'})
            return OperationResult(OperationName=self.Name, Applies=False, Reasons=Reasons)

        if Rules.RequireForcedSubtitlesPresent:
            if Mf.HasForcedSubtitles is not True:
                Reasons.append({'Rule': 'RequireForcedSubtitlesPresent', 'Operator': '!= True', 'Actual': Mf.HasForcedSubtitles, 'Threshold': True, 'Outcome': 'skip'})
                return OperationResult(OperationName=self.Name, Applies=False, Reasons=Reasons)

        Reasons.append({'Rule': 'SubtitleFixApplies', 'Operator': 'all-conditions-met', 'Actual': sorted(SubFormats & NonNative), 'Threshold': 'incompatible-subs-in-mp4-family', 'Outcome': 'applies'})
        return OperationResult(OperationName=self.Name, Applies=True, Reasons=Reasons)

    @staticmethod
    def _ParseCsv(Csv: Optional[str]) -> set:
        if not Csv:
            return set()
        return {Tok.strip().lower() for Tok in Csv.split(',') if Tok.strip()}
