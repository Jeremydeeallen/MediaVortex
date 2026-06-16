from dataclasses import dataclass
from typing import Any, Optional, Tuple

from Core.Resolution.ResolutionTier import ResolutionTier
from Core.Resolution.ResolutionTierRegistry import ResolutionTierRegistry


@dataclass(frozen=True)
# directive: resolution-types | # see resolution-types.C1
class Resolution:
    """Typed source/target resolution. Width + Height are exact pixels; Tier is the bucket; AspectRatio is Width/Height. After construction no field is a raw string -- string parsing only happens in FromAny. Tier comes from a Registry (data-driven; resolution-types.C13)."""
    Width: int
    Height: int
    Tier: ResolutionTier
    AspectRatio: float

    @classmethod
    # directive: resolution-types | # see resolution-types.C1
    def FromAny(cls, Value: Any, Registry: Optional[ResolutionTierRegistry] = None) -> Optional['Resolution']:
        """Sole string parser for resolution inputs. Accepts: 'WIDTHxHEIGHT' (e.g. '1916x1040'); canonical category ('480p'/'720p'/'1080p'/'2160p'/'4k'); a (Width, Height) tuple/list; an existing Resolution (passthrough); None/'' (returns None). Never raises. Registry defaults to a fresh ResolutionTierRegistry; tests inject a mock."""
        if Value is None:
            return None
        if isinstance(Value, Resolution):
            return Value
        Reg = Registry or ResolutionTierRegistry()
        if isinstance(Value, (tuple, list)) and len(Value) == 2:
            return cls._FromDims(int(Value[0]), int(Value[1]), Reg)
        if not isinstance(Value, str):
            return None
        S = Value.strip().lower()
        if not S:
            return None
        Dims = _ParseWxH(S)
        if Dims is not None:
            return cls._FromDims(Dims[0], Dims[1], Reg)
        TierFromCategory = Reg.FromCategory(S)
        if TierFromCategory is not None:
            return cls._FromCategoryTier(TierFromCategory)
        return None

    @classmethod
    # directive: resolution-types | # see resolution-types.C1
    def _FromDims(cls, Width: int, Height: int, Registry: ResolutionTierRegistry) -> Optional['Resolution']:
        if Width <= 0 or Height <= 0:
            return None
        Tier = Registry.FromDims(Width, Height)
        Aspect = float(Width) / float(Height)
        return cls(Width=Width, Height=Height, Tier=Tier, AspectRatio=round(Aspect, 3))

    @classmethod
    # directive: resolution-types | # see resolution-types.C1
    def _FromCategoryTier(cls, Tier: ResolutionTier) -> 'Resolution':
        W, H = Tier.CanonicalWidth, Tier.CanonicalHeight
        return cls(Width=W, Height=H, Tier=Tier, AspectRatio=round(float(W) / float(H), 3))


# directive: resolution-types | # see resolution-types.C1
def _ParseWxH(S: str) -> Optional[Tuple[int, int]]:
    """Parse 'WIDTHxHEIGHT' (e.g. '1916x1040', '1920X1080'); return None on shape mismatch."""
    if 'x' not in S:
        return None
    Parts = S.split('x')
    if len(Parts) != 2:
        return None
    try:
        return (int(Parts[0]), int(Parts[1]))
    except ValueError:
        return None
