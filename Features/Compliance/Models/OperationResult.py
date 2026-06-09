from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class OperationResult:
    """One operation's verdict: Applies + structured Reasons trace -- see compliance-solid-refactor.C13."""
    OperationName: str
    Applies: bool
    Reasons: List[dict] = field(default_factory=list)
