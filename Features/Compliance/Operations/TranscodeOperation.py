from typing import Optional
from Models.MediaFileModel import MediaFileModel
from Features.Compliance.Models.EffectiveProfile import EffectiveProfile
from Features.Compliance.Models.OperationResult import OperationResult
from Features.Compliance.Models.TranscodeRulesModel import TranscodeRulesModel
from Features.Compliance.Operations.IComplianceOperation import IComplianceOperation


_RES_HEIGHTS = {'480p': 480, '720p': 720, '1080p': 1080, '2160p': 2160, '4k': 2160}


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C2
class TranscodeOperation(IComplianceOperation):
    """Transcode operation predicate -- evaluates upscale guard + resolution + codec + savings rules."""

    Name = "Transcode"

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C2
    def Apply(self, Mf: MediaFileModel, Profile: EffectiveProfile, Rules: TranscodeRulesModel) -> OperationResult:
        """Apply each TranscodeRule predicate; return Applies=True if any predicate triggers."""
        Reasons = []
        Applies = False

        SrcH = self._HeightOf(Mf.ResolutionCategory)
        TgtH = self._HeightOf(Profile.TargetResolutionCategory)

        if Rules.PreventUpscale and SrcH is not None and TgtH is not None and SrcH < TgtH:
            Reasons.append({'Rule': 'PreventUpscale', 'Operator': '<', 'Actual': SrcH, 'Threshold': TgtH, 'Outcome': 'skip'})
            return OperationResult(OperationName=self.Name, Applies=False, Reasons=Reasons)

        if Rules.ResolutionExceedsProfileTarget and SrcH is not None and TgtH is not None and SrcH > TgtH:
            Reasons.append({'Rule': 'ResolutionExceedsProfileTarget', 'Operator': '>', 'Actual': SrcH, 'Threshold': TgtH, 'Outcome': 'applies'})
            Applies = True

        SrcCodec = (Mf.Codec or '').lower()
        AcceptableCodecs = self._ParseCsv(Rules.AcceptableVideoCodecsCsv)
        if SrcCodec and SrcCodec not in AcceptableCodecs:
            Reasons.append({'Rule': 'AcceptableVideoCodecsCsv', 'Operator': 'NOT IN', 'Actual': SrcCodec, 'Threshold': sorted(AcceptableCodecs), 'Outcome': 'applies'})
            Applies = True

        EstSavings = self._EstimatedSavingsMB(Mf, Profile)
        if EstSavings is not None and EstSavings >= Rules.EstimatedSavingsMBThreshold:
            Reasons.append({'Rule': 'EstimatedSavingsMBThreshold', 'Operator': '>=', 'Actual': round(EstSavings, 1), 'Threshold': Rules.EstimatedSavingsMBThreshold, 'Outcome': 'applies'})
            Applies = True

        return OperationResult(OperationName=self.Name, Applies=Applies, Reasons=Reasons)

    @staticmethod
    def _HeightOf(Category: Optional[str]) -> Optional[int]:
        if not Category:
            return None
        return _RES_HEIGHTS.get(Category.lower())

    @staticmethod
    def _ParseCsv(Csv: Optional[str]) -> set:
        if not Csv:
            return set()
        return {Tok.strip().lower() for Tok in Csv.split(',') if Tok.strip()}

    @staticmethod
    def _EstimatedSavingsMB(Mf: MediaFileModel, Profile: EffectiveProfile) -> Optional[float]:
        if Profile.TargetVideoKbps is None or Profile.TargetAudioKbps is None:
            return None
        if Mf.DurationMinutes is None or Mf.DurationMinutes <= 0:
            return None
        TargetSizeMB = ((Profile.TargetVideoKbps + Profile.TargetAudioKbps) * Mf.DurationMinutes * 60.0) / (8 * 1024)
        return max(0.0, (Mf.SizeMB or 0.0) - TargetSizeMB)
