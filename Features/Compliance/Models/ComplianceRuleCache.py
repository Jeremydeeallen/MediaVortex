from dataclasses import dataclass
from typing import Optional, Any
from Features.Compliance.Models.ComplianceGatesModel import ComplianceGatesModel
from Features.Compliance.Models.TranscodeRulesModel import TranscodeRulesModel
from Features.Compliance.Models.RemuxRulesModel import RemuxRulesModel
from Features.Compliance.Models.AudioFixRulesModel import AudioFixRulesModel
from Features.Compliance.Models.SubtitleFixRulesModel import SubtitleFixRulesModel


@dataclass(frozen=True)
class ComplianceRuleCache:
    """Snapshot of every rule table -- built ONCE per bulk recompute call, passed to each Evaluate -- see compliance-solid-refactor.C12."""
    Gates: ComplianceGatesModel
    TranscodeRules: TranscodeRulesModel
    RemuxRules: RemuxRulesModel
    AudioFixRules: AudioFixRulesModel
    SubtitleFixRules: SubtitleFixRulesModel

    def GetForOperation(self, OperationName: str) -> Optional[Any]:
        """Map operation name to its rules model; returns None for unknown operation names."""
        if OperationName == 'Transcode':
            return self.TranscodeRules
        if OperationName == 'Remux':
            return self.RemuxRules
        if OperationName == 'AudioFix':
            return self.AudioFixRules
        if OperationName == 'SubtitleFix':
            return self.SubtitleFixRules
        return None
