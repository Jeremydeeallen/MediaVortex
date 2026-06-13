from dataclasses import dataclass, field
from typing import FrozenSet, List, Optional


# directive: compliance-writeback-invariant | # see compliance.C7
class ContradictoryDecisionError(ValueError):
    """Grep-able typed signal that a ComplianceDecision violated the C3 bucket-precedence rule at construction. see compliance.C7"""


_LEGAL_OPERATIONS = frozenset({'Transcode', 'Remux', 'AudioFix', 'SubtitleFix'})


@dataclass(frozen=True)
# directive: compliance-writeback-invariant | # see compliance.C7
class ComplianceDecision:
    """Immutable result of one ComplianceEvaluator.Evaluate call -- see compliance-solid-refactor.C13 + compliance.C7."""
    IsCompliant: Optional[bool]
    OperationsNeeded: FrozenSet[str]
    WorkBucket: Optional[str]
    GateBlocked: Optional[str]
    Reasons: List[dict] = field(default_factory=list)

    # directive: compliance-writeback-invariant | # see compliance.C7
    def __post_init__(self):
        Unknown = set(self.OperationsNeeded) - _LEGAL_OPERATIONS
        if Unknown:
            raise ContradictoryDecisionError(f"ComplianceDecision.OperationsNeeded contains unknown operation(s) {sorted(Unknown)}; legal vocabulary={sorted(_LEGAL_OPERATIONS)}; tuple=({self.IsCompliant!r},{set(self.OperationsNeeded)!r},{self.WorkBucket!r},{self.GateBlocked!r})")
        CompliantClean = (self.IsCompliant is True) and (self.WorkBucket is None) and (not self.OperationsNeeded)
        NonCompliantBucketed = (self.IsCompliant is False) and (self.WorkBucket is not None) and bool(self.OperationsNeeded)
        GateBlockedNone = (self.IsCompliant is None) and (self.GateBlocked is not None) and (self.WorkBucket is None) and (not self.OperationsNeeded)
        if not (CompliantClean or NonCompliantBucketed or GateBlockedNone):
            raise ContradictoryDecisionError(f"ComplianceDecision violates C7 three-way disjunction: tuple=(IsCompliant={self.IsCompliant!r}, OperationsNeeded={set(self.OperationsNeeded)!r}, WorkBucket={self.WorkBucket!r}, GateBlocked={self.GateBlocked!r}); legal shapes are (True,empty,None,None) or (False,non-empty,non-None,None) or (None,empty,None,non-None)")
