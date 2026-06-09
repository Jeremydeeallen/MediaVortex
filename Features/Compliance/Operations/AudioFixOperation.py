from Models.MediaFileModel import MediaFileModel
from Features.Compliance.Models.EffectiveProfile import EffectiveProfile
from Features.Compliance.Models.OperationResult import OperationResult
from Features.Compliance.Models.AudioFixRulesModel import AudioFixRulesModel
from Features.Compliance.Operations.IComplianceOperation import IComplianceOperation


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C4
class AudioFixOperation(IComplianceOperation):
    """AudioFix operation predicate -- evaluates loudness-off-target rule against the LUFS target + tolerance."""

    Name = "AudioFix"

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C4
    def Apply(self, Mf: MediaFileModel, Profile: EffectiveProfile, Rules: AudioFixRulesModel) -> OperationResult:
        """Apply the loudness-off-target predicate; AudioComplete=True short-circuits to does-not-apply."""
        Reasons = []

        if Mf.AudioComplete is True:
            Reasons.append({'Rule': 'AudioComplete', 'Operator': 'IS', 'Actual': True, 'Threshold': True, 'Outcome': 'skip'})
            return OperationResult(OperationName=self.Name, Applies=False, Reasons=Reasons)

        if Rules.RequireLufsMeasured and Mf.SourceIntegratedLufs is None:
            Reasons.append({'Rule': 'RequireLufsMeasured', 'Operator': 'IS NULL', 'Actual': None, 'Threshold': 'measured', 'Outcome': 'skip'})
            return OperationResult(OperationName=self.Name, Applies=False, Reasons=Reasons)

        if Mf.SourceIntegratedLufs is None:
            return OperationResult(OperationName=self.Name, Applies=False, Reasons=Reasons)

        Delta = abs(float(Mf.SourceIntegratedLufs) - float(Rules.TargetLoudnessLufs))
        if Delta > Rules.ToleranceLufs:
            Reasons.append({'Rule': 'LoudnessOffTarget', 'Operator': '|actual-target|>', 'Actual': round(Delta, 2), 'Threshold': Rules.ToleranceLufs, 'Outcome': 'applies'})
            return OperationResult(OperationName=self.Name, Applies=True, Reasons=Reasons)

        Reasons.append({'Rule': 'LoudnessOffTarget', 'Operator': '|actual-target|<=', 'Actual': round(Delta, 2), 'Threshold': Rules.ToleranceLufs, 'Outcome': 'skip'})
        return OperationResult(OperationName=self.Name, Applies=False, Reasons=Reasons)
