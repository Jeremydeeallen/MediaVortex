# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C2
from typing import Dict, Any, Optional

from Core.Logging.LoggingService import LoggingService
from Core.Resolution.Resolution import Resolution
from Core.Resolution.ResolutionTierRegistry import ResolutionTierRegistry
from Core.Resolution.ScalePolicy import WidthAnchoredScalePolicy


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C2
class ResolutionCalculator:
    """Pure value-computation for resolution math (target, scale filter, dims). CalculateScaleFilter is now a thin facade over WidthAnchoredScalePolicy (resolution-types.C4)."""

    # directive: resolution-types | # see resolution-types.C4
    def __init__(self, Registry: Optional[ResolutionTierRegistry] = None, Policy: Optional[WidthAnchoredScalePolicy] = None):
        self._Registry = Registry
        self._Policy = Policy or WidthAnchoredScalePolicy()

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C2
    def CalculateTargetResolution(self, ProfileSettings: Dict[str, Any], SourceResolution: str) -> str:
        """Return ProfileSettings.TargetResolution when set, else SourceResolution."""
        Target = ProfileSettings.get('TargetResolution')
        return Target if Target else SourceResolution

    # directive: resolution-types | # see resolution-types.C4
    def CalculateScaleFilter(self, SourceResolution: str, TargetResolution: str, MediaFile, ProfileSettings: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Backward-compat facade. Prefers MediaFile.Resolution (exact pixels) over the category SourceResolution so off-canonical letterbox sources (e.g. 1916x1040) classify as their true tier. Delegates the decision to WidthAnchoredScalePolicy."""
        try:
            Reg = self._RegistryRef()
            if Reg is None:
                return None
            SourceInput = self._BestSourceInput(MediaFile, SourceResolution)
            SourceRes = Resolution.FromAny(SourceInput, Registry=Reg)
            TargetTier = Reg.FromCategory(TargetResolution)
            Decision = self._Policy.Decide(SourceRes, TargetTier)
            return Decision.AsFfmpegArg() if Decision is not None else None
        except Exception as Ex:
            LoggingService.LogException(
                "Exception calculating scale filter", Ex, "CalculateScaleFilter", "ResolutionCalculator"
            )
            return None

    # directive: resolution-types | # see resolution-types.C4
    def _RegistryRef(self) -> Optional[ResolutionTierRegistry]:
        if self._Registry is None:
            self._Registry = ResolutionTierRegistry()
        return self._Registry

    @staticmethod
    # directive: resolution-types | # see resolution-types.C4
    def _BestSourceInput(MediaFile, SourceResolution: str):
        """Prefer MediaFile.Resolution (raw WxH) over the legacy category string when available -- exact pixels classify off-canonical sources correctly (e.g. 1916x1040 -> T1080p)."""
        if MediaFile is not None:
            ExactPixels = getattr(MediaFile, 'Resolution', None)
            if isinstance(ExactPixels, str) and 'x' in ExactPixels:
                return ExactPixels
        return SourceResolution

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C2
    def ExtractHeightFromResolution(self, Resolution: str) -> int:
        """Parse height from 'NNNNp' or 'WxH' string; default 720 on parse failure."""
        try:
            if Resolution.endswith('p'):
                return int(Resolution[:-1])
            if 'x' in Resolution:
                return int(Resolution.split('x')[1])
            return int(Resolution)
        except (ValueError, IndexError):
            return 720

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C2
    def GetSourceDimensions(self, MediaFile) -> tuple:
        """Return (Width, Height) from MediaFile.Resolution; safe default (1920,1080)."""
        try:
            if not MediaFile or not getattr(MediaFile, 'Resolution', None):
                return (1920, 1080)
            Resolution = MediaFile.Resolution
            if 'x' in Resolution:
                try:
                    Width, Height = Resolution.split('x')
                    return (int(Width), int(Height))
                except (ValueError, IndexError):
                    pass
            if Resolution in ('2160p', '4K'):
                return (3840, 2160)
            if Resolution == '1080p':
                return (1920, 1080)
            if Resolution == '720p':
                return (1280, 720)
            if Resolution == '480p':
                return (854, 480)
            Height = self.ExtractHeightFromResolution(Resolution)
            return (self.CalculateWidthFromHeight(Height), Height)
        except Exception:
            return (1920, 1080)

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C2
    def CalculateWidthFromHeight(self, Height: int, AspectRatio: Optional[float] = None) -> int:
        """Compute even-codec-legal width for a given height; canonical tiers when no aspect given."""
        try:
            if AspectRatio:
                Width = int(Height * AspectRatio)
                return Width - (Width % 2)
            if Height == 2160:
                return 3840
            if Height == 1080:
                return 1920
            if Height == 720:
                return 1280
            if Height == 480:
                return 854
            return int(Height * 16 / 9)
        except Exception:
            return 1280
