from typing import Optional
from Models.MediaFileModel import MediaFileModel
from Features.Compliance.Models.EffectiveProfile import EffectiveProfile
from Features.Compliance.Models.ComplianceDecision import ComplianceDecision
from Features.Compliance.Models.ComplianceRuleCache import ComplianceRuleCache
from Features.Compliance.Services.ComplianceGateChain import ComplianceGateChain
from Features.Compliance.Services.ComplianceRuleEngine import ComplianceRuleEngine
from Features.Compliance.Services.ComplianceBucketResolver import ComplianceBucketResolver


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C8
class ComplianceEvaluator:
    """Sole public entry for compliance evaluation -- DIP via constructor injection of GateChain + RuleEngine + BucketResolver."""

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C11
    def __init__(self, GateChain: ComplianceGateChain, RuleEngine: ComplianceRuleEngine, BucketResolver: ComplianceBucketResolver):
        self.GateChain = GateChain
        self.RuleEngine = RuleEngine
        self.BucketResolver = BucketResolver

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C13
    def Evaluate(self, Mf: MediaFileModel, Profile: Optional[EffectiveProfile], Cache: ComplianceRuleCache) -> ComplianceDecision:
        """Evaluate gates -> operations -> bucket; return immutable ComplianceDecision."""
        GateBlocked = self.GateChain.Apply(Mf, Profile, Cache.Gates)
        if GateBlocked is not None:
            return ComplianceDecision(IsCompliant=None, OperationsNeeded=frozenset(), WorkBucket=None, GateBlocked=GateBlocked, Reasons=[])

        Results = self.RuleEngine.Run(Mf, Profile, Cache)
        OperationsNeeded = frozenset(R.OperationName for R in Results if R.Applies)
        Reasons = [Reason for R in Results for Reason in R.Reasons]
        Bucket = self.BucketResolver.Resolve(OperationsNeeded)
        IsCompliant = (Bucket is None)
        return ComplianceDecision(IsCompliant=IsCompliant, OperationsNeeded=OperationsNeeded, WorkBucket=Bucket, GateBlocked=None, Reasons=Reasons)
