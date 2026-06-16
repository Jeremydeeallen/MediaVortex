from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from Core.Resolution.Resolution import Resolution
from Core.Resolution.ResolutionTier import ResolutionTier


@dataclass(frozen=True)
# directive: resolution-types | # see resolution-types.C3
class ScaleFilter:
    """FFmpeg width-anchored scale arg. HeightExpr='-2' lets FFmpeg compute an even codec-legal height from source aspect (aspect-preserving)."""
    Width: int
    HeightExpr: str = '-2'

    # directive: resolution-types | # see resolution-types.C3
    def AsFfmpegArg(self) -> str:
        return 'scale=w=' + str(self.Width) + ':h=' + self.HeightExpr


# directive: resolution-types | # see resolution-types.C3
class IScalePolicy(ABC):
    """Decision: does a source need scaling to reach a target tier? Sole producer of scale-filter values."""

    @abstractmethod
    # directive: resolution-types | # see resolution-types.C3
    def Decide(self, Source: Resolution, TargetTier: ResolutionTier) -> Optional[ScaleFilter]:
        """Return None when no downscale is needed; ScaleFilter otherwise."""
        raise NotImplementedError


# directive: resolution-types | # see resolution-types.C3
class WidthAnchoredScalePolicy(IScalePolicy):
    """Width-anchored aspect-preserving policy. Same-tier or upscale -> None; else scale to TargetTier.CanonicalWidth with h='-2'. Robust to off-canonical pixels (1916x1040 vs 1920x1080 are both T1080p)."""

    # directive: resolution-types | # see resolution-types.C3
    def Decide(self, Source: Resolution, TargetTier: ResolutionTier) -> Optional[ScaleFilter]:
        if Source is None or TargetTier is None:
            return None
        if Source.Tier.Rank <= TargetTier.Rank:
            return None
        return ScaleFilter(Width=TargetTier.CanonicalWidth, HeightExpr='-2')
