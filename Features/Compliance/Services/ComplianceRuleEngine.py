from typing import List, Tuple
from Models.MediaFileModel import MediaFileModel
from Features.Compliance.Models.EffectiveProfile import EffectiveProfile
from Features.Compliance.Models.OperationResult import OperationResult
from Features.Compliance.Models.ComplianceRuleCache import ComplianceRuleCache
from Features.Compliance.Operations.IComplianceOperation import IComplianceOperation


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C8
class ComplianceRuleEngine:
    """Runs each registered IComplianceOperation against the MediaFile + Profile; collects OperationResults."""

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C8
    def __init__(self, Operations: List[IComplianceOperation]):
        self.Operations = Operations

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C8
    def Run(self, Mf: MediaFileModel, Profile: EffectiveProfile, Cache: ComplianceRuleCache) -> List[OperationResult]:
        """Apply every operation; return the list of OperationResults (order matches registration)."""
        Results: List[OperationResult] = []
        for Op in self.Operations:
            Rules = Cache.GetForOperation(Op.Name)
            if Rules is None:
                continue
            Results.append(Op.Apply(Mf, Profile, Rules))
        return Results
