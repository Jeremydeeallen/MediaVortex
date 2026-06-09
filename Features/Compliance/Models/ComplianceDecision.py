from dataclasses import dataclass, field
from typing import FrozenSet, List, Optional


@dataclass(frozen=True)
class ComplianceDecision:
    """Immutable result of one ComplianceEvaluator.Evaluate call -- see compliance-solid-refactor.C13."""
    IsCompliant: Optional[bool]
    OperationsNeeded: FrozenSet[str]
    WorkBucket: Optional[str]
    GateBlocked: Optional[str]
    Reasons: List[dict] = field(default_factory=list)
