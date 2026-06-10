# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C9
from typing import Optional, Any
from Core.Logging.LoggingService import LoggingService


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C9
class MediaProbeAdapter:
    """Per-worker FFprobe adapter; injected FFprobePath rather than discovered live."""

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C9
    def __init__(self, FFprobePath: Optional[str] = None):
        """Stash FFprobePath; None defers discovery to the underlying FFmpegAnalysisService."""
        self.FFprobePath = FFprobePath

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C9
    def RunAnalysis(self, InputPath: str) -> Optional[Any]:
        """Return the FFmpegAnalysisService.AnalyzeMediaFile result for the given input path; None on failure."""
        try:
            from Services.FFmpegAnalysisService import FFmpegAnalysisService
            return FFmpegAnalysisService(FFprobePath=self.FFprobePath).AnalyzeMediaFile(InputPath)
        except Exception as Ex:
            LoggingService.LogException(f"RunAnalysis failed for {InputPath}", Ex, "MediaProbeAdapter", "RunAnalysis")
            return None
