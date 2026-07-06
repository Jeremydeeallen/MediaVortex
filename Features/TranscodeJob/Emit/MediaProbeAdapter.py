# directive: transcode-flow-canonical
import json
from typing import Optional, Any, Dict
from Core.Logging.LoggingService import LoggingService


# directive: transcode-flow-canonical
class MediaProbeError(RuntimeError):
    pass


# directive: transcode-flow-canonical
class MediaProbeAdapter:
    """Per-worker FFprobe adapter; injected FFprobePath rather than discovered live."""

    # directive: transcode-flow-canonical
    def __init__(self, FFprobePath: Optional[str] = None):
        self.FFprobePath = FFprobePath

    # directive: transcode-flow-canonical
    def RunAnalysis(self, InputPath: str) -> Optional[Any]:
        try:
            from Services.FFmpegAnalysisService import FFmpegAnalysisService
            return FFmpegAnalysisService(FFprobePath=self.FFprobePath).AnalyzeMediaFile(InputPath)
        except Exception as Ex:
            LoggingService.LogException(f"RunAnalysis failed for {InputPath}", Ex, "MediaProbeAdapter", "RunAnalysis")
            return None

    # directive: transcode-flow-canonical
    def ProbeStreams(self, InputPath: str) -> Dict[str, Any]:
        from Services.FFmpegService import FFmpegService
        Result = FFmpegService(FFprobePath=self.FFprobePath).ExecuteFFprobe(InputPath)
        if not Result.get('Success'):
            raise MediaProbeError(f"ffprobe failed for {InputPath}: {Result.get('ErrorMessage')}")
        try:
            return json.loads(Result['Output'])
        except json.JSONDecodeError as Ex:
            raise MediaProbeError(f"ffprobe JSON parse failed for {InputPath}: {Ex}") from Ex
