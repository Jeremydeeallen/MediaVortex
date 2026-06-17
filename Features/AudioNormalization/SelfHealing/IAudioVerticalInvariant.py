from abc import ABC, abstractmethod
from typing import List


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S9
class IAudioVerticalInvariant(ABC):
    """Abstract invariant: each impl detects a single kind of DB-state discrepancy; one impl per concern (OCP)."""

    Name: str = ""

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S9
    @abstractmethod
    def Detect(self) -> List:
        """Return the list of offending row ids (MediaFileId / TranscodeQueue.Id / TranscodeAttempts.Id) per invariant kind."""
