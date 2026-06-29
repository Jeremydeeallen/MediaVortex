# directive: transcode-worker-unification | # see worker-loop.C3
from typing import Any, Dict, Optional
from Core.Logging.LoggingService import LoggingService
from Features.TranscodeJob.Worker.Strategies.ITranscodeJobStrategy import CommandSpec, ITranscodeJobStrategy


# directive: transcode-worker-unification | # see worker-loop.C3
class TranscodeJobStrategy(ITranscodeJobStrategy):

    # directive: transcode-worker-unification | # see worker-loop.C3
    def __init__(self, QueueService=None):
        # see worker-loop.C3
        self.QueueService = QueueService

    # directive: transcode-worker-unification | # see worker-loop.C3
    def BuildCommand(self, Job, MediaFile, Context: Dict[str, Any]) -> Optional[CommandSpec]:
        # see worker-loop.C3
        QueueService = Context.get('QueueService') or self.QueueService
        TranscodingSettings = QueueService.GetTranscodingSettings(Job, MediaFile)
        if not TranscodingSettings:
            return None
        TranscodingSettings['InputPath'] = Context.get('InputPath', '')
        CommandDict = QueueService.BuildTranscodeCommand(Job, MediaFile, TranscodingSettings)
        if not CommandDict:
            return None
        return CommandSpec(Command=CommandDict['Command'], OutputPath=CommandDict['OutputPath'])

    # directive: transcode-worker-unification | # see worker-loop.C3
    def HandleResult(self, Job, Result: Dict[str, Any], TranscodeAttemptId: int, ActiveJobId: int, OutputPath: str, QueueService=None) -> None:
        # see worker-loop.C3
        Qs = QueueService or self.QueueService
        Qs.HandleTranscodingResult(Job, Result, TranscodeAttemptId, ActiveJobId)
