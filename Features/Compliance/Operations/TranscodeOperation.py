from typing import Optional
from Models.MediaFileModel import MediaFileModel
from Core.Resolution.ResolutionTier import ResolutionTier
from Core.Resolution.ResolutionTierRegistry import ResolutionTierRegistry
from Features.Profiles.EffectiveProfile import EffectiveProfile
from Features.Compliance.Models.OperationResult import OperationResult
from Features.Compliance.Models.TranscodeRulesModel import TranscodeRulesModel
from Features.Compliance.Operations.IComplianceOperation import IComplianceOperation


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C2
class TranscodeOperation(IComplianceOperation):
    """Transcode operation predicate -- evaluates upscale guard + resolution + codec + savings rules. Tier comparisons use ResolutionTier.Rank (resolution-types.C5); the legacy _HeightOf dict is gone."""

    Name = "Transcode"

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C2
    def __init__(self, TierRegistry: Optional[ResolutionTierRegistry] = None):
        # directive: resolution-types | # see resolution-types.C5
        self._TierRegistry = TierRegistry

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C2
    def Apply(self, Mf: MediaFileModel, Profile: EffectiveProfile, Rules: TranscodeRulesModel) -> OperationResult:
        """Apply each TranscodeRule predicate; return Applies=True if any predicate triggers."""
        Reasons = []
        Applies = False

        # directive: resolution-types | # see resolution-types.C5
        SrcTier = self._ResolveTier(Mf.ResolutionCategory)
        TgtTier = Profile.TargetResolutionCategory if isinstance(Profile.TargetResolutionCategory, ResolutionTier) else None

        if Rules.PreventUpscale and SrcTier is not None and TgtTier is not None and SrcTier.Rank < TgtTier.Rank:
            Reasons.append({'Rule': 'PreventUpscale', 'Operator': '<', 'Actual': SrcTier.Name, 'Threshold': TgtTier.Name, 'Outcome': 'skip'})
            return OperationResult(OperationName=self.Name, Applies=False, Reasons=Reasons)

        if Rules.ResolutionExceedsProfileTarget and SrcTier is not None and TgtTier is not None and SrcTier.Rank > TgtTier.Rank:
            Reasons.append({'Rule': 'ResolutionExceedsProfileTarget', 'Operator': '>', 'Actual': SrcTier.Name, 'Threshold': TgtTier.Name, 'Outcome': 'applies'})
            Applies = True

        SrcCodec = (Mf.Codec or '').lower()
        AcceptableCodecs = self._ParseCsv(Rules.AcceptableVideoCodecsCsv)
        if SrcCodec and SrcCodec not in AcceptableCodecs:
            Reasons.append({'Rule': 'AcceptableVideoCodecsCsv', 'Operator': 'NOT IN', 'Actual': SrcCodec, 'Threshold': sorted(AcceptableCodecs), 'Outcome': 'applies'})
            Applies = True

        # directive: mv-trust-savings-and-clamp | # see mv-trust-savings-and-clamp.C1
        MvTrusted = bool(getattr(Mf, 'TranscodedByMediaVortex', False))
        EstSavings = self._EstimatedSavingsMB(Mf, Profile)
        if EstSavings is not None and EstSavings >= Rules.EstimatedSavingsMBThreshold and not MvTrusted:
            Reasons.append({'Rule': 'EstimatedSavingsMBThreshold', 'Operator': '>=', 'Actual': round(EstSavings, 1), 'Threshold': Rules.EstimatedSavingsMBThreshold, 'Outcome': 'applies'})
            Applies = True
        elif EstSavings is not None and EstSavings >= Rules.EstimatedSavingsMBThreshold and MvTrusted:
            Reasons.append({'Rule': 'EstimatedSavingsMBThreshold', 'Operator': 'skip-mv-trusted', 'Actual': round(EstSavings, 1), 'Threshold': Rules.EstimatedSavingsMBThreshold, 'Outcome': 'skip'})

        return OperationResult(OperationName=self.Name, Applies=Applies, Reasons=Reasons)

    # directive: resolution-types | # see resolution-types.C5
    def _ResolveTier(self, Category: Optional[str]) -> Optional[ResolutionTier]:
        """Lazily build a registry (per-operation-call) and translate the legacy category string into a typed Tier. None for unknown / missing."""
        if not Category:
            return None
        Reg = self._TierRegistry or ResolutionTierRegistry()
        if self._TierRegistry is None:
            self._TierRegistry = Reg
        return Reg.FromCategory(Category)

    @staticmethod
    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C2
    def _ParseCsv(Csv: Optional[str]) -> set:
        if not Csv:
            return set()
        return {Tok.strip().lower() for Tok in Csv.split(',') if Tok.strip()}

    @staticmethod
    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C2
    def _EstimatedSavingsMB(Mf: MediaFileModel, Profile: EffectiveProfile) -> Optional[float]:
        if not Profile.TargetVideoKbps:
            return None
        if Mf.DurationMinutes is None or Mf.DurationMinutes <= 0:
            return None
        Akbps = Profile.TargetAudioKbps if Profile.TargetAudioKbps else 0
        TargetSizeMB = ((Profile.TargetVideoKbps + Akbps) * Mf.DurationMinutes * 60.0) / (8 * 1024)
        return max(0.0, (Mf.SizeMB or 0.0) - TargetSizeMB)
