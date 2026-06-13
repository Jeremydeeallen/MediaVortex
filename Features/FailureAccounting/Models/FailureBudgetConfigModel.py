from dataclasses import dataclass
from typing import Optional


# directive: failure-accounting | # see failure-accounting.C2
@dataclass(frozen=True)
# directive: failure-accounting | # see failure-accounting.C2
class FailureBudgetConfigModel:
    """Single-row config: how many consecutive encode failures a MediaFile may carry before the queue rejects it."""
    MaxEncodeFailures: int = 3
    ResetWindowDays: Optional[int] = None
