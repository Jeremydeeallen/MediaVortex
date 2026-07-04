from abc import ABC, abstractmethod
from typing import Any, Dict


class IEncoderArgsStrategy(ABC):
    """ABC: per-codec ffmpeg argv emission for software encoders. VideoSlot delegates to concrete strategy on Codec key."""

    @abstractmethod
    def AddCodecParameters(self, CommandParts: list, CodecParameters: list, ProfileSettings: Dict[str, Any]) -> None:
        ...

    def AddFilmGrainParameter(self, CommandParts: list, CodecParameters: list, ProfileSettings: Dict[str, Any]) -> None:
        """Default no-op. Software encoders override to emit -svtav1-params film-grain=N."""
        return None
