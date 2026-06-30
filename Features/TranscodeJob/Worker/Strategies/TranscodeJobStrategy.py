# directive: transcode-worker-unification | # see worker-loop.C3
import sys
from typing import Any, Dict, Optional
from Core.Logging.LoggingService import LoggingService
from Features.AudioNormalization.Services.PreEncodeAudioPipeline import PreEncodeAudioPipeline
from Features.TranscodeJob.Worker.Strategies.ITranscodeJobStrategy import CommandSpec, ITranscodeJobStrategy


# directive: audio-dialog-boost-real | # see audio-normalization.C14
class TranscodeJobStrategy(ITranscodeJobStrategy):

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def __init__(self, QueueService=None, PreEncodeAudio=None):
        self.QueueService = QueueService
        self.PreEncodeAudio = PreEncodeAudio
        self._LastScratchDir = None

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def BuildCommand(self, Job, MediaFile, Context: Dict[str, Any]) -> Optional[CommandSpec]:
        QueueService = Context.get('QueueService') or self.QueueService
        TranscodingSettings = QueueService.GetTranscodingSettings(Job, MediaFile)
        if not TranscodingSettings:
            return None
        InputPath = Context.get('InputPath', '')
        TranscodingSettings['InputPath'] = InputPath
        PreResult = self._RunPreEncodeAudio(InputPath, Job, Context)
        if PreResult:
            TranscodingSettings['DemucsPremixPath'] = PreResult.get('DemucsPremixPath')
            TranscodingSettings['VocalsRmsDbfs'] = PreResult.get('VocalsRmsDbfs')
            self._LastScratchDir = PreResult.get('ScratchDir')
        CommandDict = QueueService.BuildTranscodeCommand(Job, MediaFile, TranscodingSettings)
        if not CommandDict:
            return None
        return CommandSpec(Command=CommandDict['Command'], OutputPath=CommandDict['OutputPath'])

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def HandleResult(self, Job, Result: Dict[str, Any], TranscodeAttemptId: int, ActiveJobId: int, OutputPath: str, QueueService=None) -> None:
        Qs = QueueService or self.QueueService
        Qs.HandleTranscodingResult(Job, Result, TranscodeAttemptId, ActiveJobId)
        if self.PreEncodeAudio and self._LastScratchDir:
            self.PreEncodeAudio.Cleanup(self._LastScratchDir)
            self._LastScratchDir = None

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def _RunPreEncodeAudio(self, InputPath, Job, Context):
        if not InputPath:
            return None
        Pipeline = self.PreEncodeAudio or self._BuildDefaultPipeline(Context)
        if Pipeline is None:
            return None
        try:
            return Pipeline.Run(InputPath, getattr(Job, 'Id', 'unknown'))
        except Exception as Ex:
            LoggingService.LogException(
                f"PreEncodeAudio.Run raised; Dialog Boost will be skipped for {InputPath}",
                Ex, "TranscodeJobStrategy", "_RunPreEncodeAudio",
            )
            return None

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def _BuildDefaultPipeline(self, Context):
        FfmpegPath = Context.get('FFmpegPath')
        if not FfmpegPath:
            return None
        self.PreEncodeAudio = PreEncodeAudioPipeline(FfmpegPath=FfmpegPath, PythonExe=sys.executable)
        return self.PreEncodeAudio
