from typing import Dict, Any, Optional
from Core.Logging.LoggingService import LoggingService


# directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C8
class EncodeExecutor:
    """Single-responsibility service for running an ffmpeg encode + reporting progress."""

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C8
    def __init__(self, DatabaseManager, VideoTranscoding, MaxCpuThreads: Optional[int] = None):
        """Inject the DB + the existing VideoTranscodingService that owns the subprocess + monitoring loop."""
        self.DatabaseManager = DatabaseManager
        self.VideoTranscoding = VideoTranscoding
        self.MaxCpuThreads = MaxCpuThreads

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C8
    def Execute(self, Job, TranscodeCommand: str, TranscodeAttemptId: int, MediaFile=None, ActiveJobId: Optional[int] = None) -> Dict[str, Any]:
        """Run the ffmpeg subprocess, report progress, return the execution result dict."""
        try:
            TotalFramesFromMediaFile = MediaFile.TotalFrames if MediaFile and MediaFile.TotalFrames else 0

            if TotalFramesFromMediaFile == 0:
                TotalFramesFromMediaFile = self._GetTotalFramesWithFallback(Job, MediaFile)

            self.DatabaseManager.SaveTranscodeProgress(
                TranscodeAttemptId=TranscodeAttemptId,
                CurrentPhase="Transcoding",
                ProgressPercent=0.0,
                CurrentFrame=0,
                CurrentFPS=0.0,
                CurrentBitrate="0kbits/s",
                CurrentTime="00:00:00",
                CurrentSpeed="0x",
                ETA="Unknown",
                TotalFrames=TotalFramesFromMediaFile,
                AverageFPS=0.0
            )

            # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C8
            def ProgressCallback(ProgressData: Dict[str, Any]):
                """Per-frame progress callback closure; captures TranscodeAttemptId + TotalFramesFromMediaFile."""
                try:
                    self.DatabaseManager.SaveTranscodeProgress(
                        TranscodeAttemptId=TranscodeAttemptId,
                        CurrentPhase=ProgressData.get('CurrentPhase', 'Transcoding'),
                        ProgressPercent=ProgressData.get('ProgressPercent', 0.0),
                        CurrentFrame=ProgressData.get('CurrentFrame', 0),
                        CurrentFPS=ProgressData.get('CurrentFPS', 0.0),
                        CurrentBitrate=f"{ProgressData.get('CurrentBitrate', 0)}kbits/s",
                        CurrentTime=ProgressData.get('CurrentTime', '00:00:00'),
                        CurrentSpeed=ProgressData.get('CurrentSpeed', '0x'),
                        ETA=ProgressData.get('ETA', 'Unknown'),
                        TotalFrames=ProgressData.get('TotalFrames', TotalFramesFromMediaFile),
                        AverageFPS=ProgressData.get('AverageFPS', 0.0)
                    )
                except Exception as e:
                    LoggingService.LogException("Exception in progress callback", e, "EncodeExecutor", "Execute")

            TranscodeResult = self.VideoTranscoding.TranscodeVideo(TranscodeAttemptId, TranscodeCommand, ProgressCallback, TotalFramesFromMediaFile, ActiveJobId, self.DatabaseManager, MaxCpuThreads=self.MaxCpuThreads)

            return TranscodeResult

        except Exception as e:
            LoggingService.LogException("Exception executing transcoding", e, "EncodeExecutor", "Execute")
            return {
                "Success": False,
                "ErrorMessage": f"Exception during transcoding: {str(e)}"
            }

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C8
    def UpdateProgress(self, TranscodeAttemptId: int, CurrentPhase: str, ProgressPercent: float = 0.0, ProgressMessage: str = '') -> None:
        """Write a TranscodeProgress row update; resilient -- failures logged but never raised."""
        try:
            LoggingService.LogInfo(f"Updating progress: {CurrentPhase} ({ProgressPercent}%) - {ProgressMessage}",
                                 "EncodeExecutor", "UpdateProgress")

            self.DatabaseManager.SaveTranscodeProgress(
                TranscodeAttemptId=TranscodeAttemptId,
                CurrentPhase=CurrentPhase,
                ProgressPercent=ProgressPercent,
                CurrentFrame=0,
                CurrentFPS=0.0,
                CurrentBitrate="0kbits/s",
                CurrentTime="00:00:00",
                CurrentSpeed="0x",
                ETA="Unknown",
                TotalFrames=0,
                AverageFPS=0.0
            )

        except Exception as e:
            LoggingService.LogException("Exception updating transcoding progress", e,
                                      "EncodeExecutor", "UpdateProgress")

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C8
    def _GetTotalFramesWithFallback(self, Job, MediaFile=None) -> int:
        """Ffprobe fallback for TotalFrames when MediaFile.TotalFrames is empty; returns 0 on failure."""
        try:
            LoggingService.LogInfo(f"MediaFile.TotalFrames is empty for {Job.FilePath}, attempting ffprobe fallback",
                                 "EncodeExecutor", "_GetTotalFramesWithFallback")

            from Services.FFmpegAnalysisService import FFmpegAnalysisService

            AnalysisService = FFmpegAnalysisService()
            AnalysisResult = AnalysisService.AnalyzeMediaFile(Job.FilePath)

            if AnalysisResult.Success and AnalysisResult.TotalFrames and AnalysisResult.TotalFrames > 0:
                LoggingService.LogInfo(f"Successfully extracted TotalFrames via ffprobe: {AnalysisResult.TotalFrames} frames",
                                     "EncodeExecutor", "_GetTotalFramesWithFallback")

                if MediaFile:
                    MediaFile.TotalFrames = AnalysisResult.TotalFrames
                    self.DatabaseManager.SaveMediaFile(MediaFile)
                    LoggingService.LogInfo(f"Updated MediaFile.TotalFrames to {AnalysisResult.TotalFrames} for future transcodes",
                                         "EncodeExecutor", "_GetTotalFramesWithFallback")

                return AnalysisResult.TotalFrames
            else:
                LoggingService.LogWarning(f"Both MediaFile.TotalFrames and ffprobe failed to extract TotalFrames for {Job.FilePath}. " +
                                        f"MediaFile.TotalFrames: {MediaFile.TotalFrames if MediaFile else 'N/A'}, " +
                                        f"FFprobe result: {AnalysisResult.TotalFrames if AnalysisResult else 'Failed'}",
                                        "EncodeExecutor", "_GetTotalFramesWithFallback")
                return 0

        except Exception as e:
            LoggingService.LogException("Exception getting TotalFrames with fallback", e, "EncodeExecutor", "_GetTotalFramesWithFallback")
            return 0
