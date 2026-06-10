# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C2
from typing import Dict, Any, Optional

from Core.Logging.LoggingService import LoggingService


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C2
class ResolutionCalculator:
    """Pure value-computation for resolution math (target, scale filter, dims)."""

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C2
    def CalculateTargetResolution(self, ProfileSettings: Dict[str, Any], SourceResolution: str) -> str:
        """Return ProfileSettings.TargetResolution when set, else SourceResolution."""
        Target = ProfileSettings.get('TargetResolution')
        return Target if Target else SourceResolution

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C2
    def CalculateScaleFilter(self, SourceResolution: str, TargetResolution: str, MediaFile, ProfileSettings: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Emit width-anchored scale=w=<TierWidth>:h=-2 (letterbox-safe; codec-legal even height)."""
        try:
            if SourceResolution == TargetResolution:
                return None
            from Services.ResolutionService import ResolutionService
            ResolutionServiceInstance = ResolutionService()
            StandardizedTarget = ResolutionServiceInstance.StandardizeResolution(TargetResolution)
            TargetHeight = self.ExtractHeightFromResolution(StandardizedTarget)
            StandardTargetHeight = ResolutionServiceInstance.GetStandardHeight(TargetHeight)
            TierWidth = {2160: 3840, 1080: 1920, 720: 1280, 480: 854}.get(StandardTargetHeight)
            if TierWidth is None:
                return None
            return f"scale=w={TierWidth}:h=-2"
        except Exception as e:
            LoggingService.LogException(
                "Exception calculating scale filter", e, "CalculateScaleFilter", "ResolutionCalculator"
            )
            return None

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
