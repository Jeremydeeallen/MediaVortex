from dataclasses import dataclass
from typing import Any, Optional


# directive: audio-pipeline-fail-loud
@dataclass(frozen=True)
class Accept:
    Plan: Any
    PolicyName: str


# directive: audio-pipeline-fail-loud
@dataclass(frozen=True)
class Reject:
    Reason: str
    PolicyName: str


# directive: audio-pipeline-fail-loud
class AudioPolicyUnresolvedError(Exception):

    # directive: audio-pipeline-fail-loud
    def __init__(self, PolicyName: str, Reason: str, TrackIndex: Optional[int] = None):
        self.PolicyName = PolicyName
        self.Reason = Reason
        self.TrackIndex = TrackIndex
        super().__init__(f"{PolicyName}: {Reason} (track={TrackIndex})")
