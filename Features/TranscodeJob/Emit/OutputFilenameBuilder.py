# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C3
import os
import re
from typing import Optional


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C3
class OutputFilenameBuilder:
    """Single source of truth for `-mv.<container>.inprogress` output naming."""

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C3
    def GenerateOutputFileName(self, OriginalFileName: str, SourceResolution: str, TargetResolution: str, ContainerType: str = 'mp4', CrfValue: int = None) -> str:
        """Build `<basename>[-resolution]-mv.<ext>.inprogress` per worker-lifecycle.feature.md C6."""
        try:
            import ntpath as _ntpath
            OriginalFileName = _ntpath.basename(_ntpath.basename(OriginalFileName or ''))
            BaseName = os.path.splitext(OriginalFileName)[0]
            BaseName = self.CollapseMvSuffix(BaseName)

            if SourceResolution == TargetResolution:
                return f"{BaseName}-mv.{ContainerType}.inprogress"

            SourceResolutionStr = self.ExtractResolutionFromFilename(OriginalFileName)
            if not SourceResolutionStr:
                TargetResolutionStr = self.FormatResolutionForFilename(TargetResolution)
                return f"{BaseName}{TargetResolutionStr}-mv.{ContainerType}.inprogress"

            TargetResolutionStr = self.FormatResolutionForFilename(TargetResolution)
            NewBaseName = OriginalFileName.replace(SourceResolutionStr, TargetResolutionStr)
            NewBaseName = os.path.splitext(NewBaseName)[0]
            NewBaseName = self.CollapseMvSuffix(NewBaseName)

            return f"{NewBaseName}-mv.{ContainerType}.inprogress"

        except Exception:
            BaseName = os.path.splitext(OriginalFileName)[0]
            BaseName = self.CollapseMvSuffix(BaseName)
            return f"{BaseName}-mv.{ContainerType}.inprogress"

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C3
    def ExtractResolutionFromFilename(self, Filename: str) -> Optional[str]:
        """Extract resolution token (1080p, 720p, 4K, HD, ...) from filename or None."""
        try:
            ResolutionPatterns = [
                r'\b2160p\b',
                r'\b1080p\b',
                r'\b720p\b',
                r'\b480p\b',
                r'\b4K\b',
                r'\bHD\b',
                r'\bSD\b',
            ]
            for Pattern in ResolutionPatterns:
                Match = re.search(Pattern, Filename, re.IGNORECASE)
                if Match:
                    return Match.group(0)
            return None
        except Exception:
            return None

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C3
    def FormatResolutionForFilename(self, Resolution: str) -> str:
        """Canonical filename token: passthrough for known tiers; height+p for WxH."""
        try:
            if Resolution == '2160p' or Resolution == '4K':
                return '2160p'
            elif Resolution == '1080p':
                return '1080p'
            elif Resolution == '720p':
                return '720p'
            elif Resolution == '480p':
                return '480p'
            else:
                if 'x' in Resolution:
                    Height = Resolution.split('x')[1]
                    return f"{Height}p"
                else:
                    return Resolution
        except Exception:
            return Resolution

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C3
    def NormalizeFfmpegPath(self, Path: Optional[str]) -> str:
        """Strip surrounding whitespace and double-quotes from an ffmpeg-bound path string."""
        if not Path:
            return Path
        return Path.strip().strip('"')

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C3
    def CollapseMvSuffix(self, BaseName: str) -> str:
        """Greedy strip of trailing `-mv` segments so any `-mv...-mv` depth collapses to single `-mv` once re-suffixed."""
        while BaseName and BaseName.lower().endswith('-mv'):
            BaseName = BaseName[:-3]
        return BaseName
