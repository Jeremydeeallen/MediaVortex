from abc import ABC, abstractmethod
from typing import List


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S9
class IAudioVerticalRemediation(ABC):
    """Abstract remediation: per-invariant action that converts a Detected list into Acted / NoOp / Error outcomes."""

    Name: str = ""

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S9
    @abstractmethod
    def Apply(self, RowIds: List) -> int:
        """Apply remediation to each offending row id; return the count of rows successfully remediated."""
