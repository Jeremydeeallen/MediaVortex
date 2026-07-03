# directive: transcode-worker-unification | # see worker-loop.C3
from typing import Any, Dict, Optional
from Features.TranscodeJob.Worker.Strategies.ITranscodeJobStrategy import CommandSpec, ITranscodeJobStrategy


# directive: audio-dialog-boost-real | # see audio-normalization.C14
class TranscodeJobStrategy(ITranscodeJobStrategy):

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def __init__(self, QueueService=None):
        self.QueueService = QueueService

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def BuildCommand(self, Job, MediaFile, Context: Dict[str, Any]) -> Optional[CommandSpec]:
        QueueService = Context.get('QueueService') or self.QueueService
        TranscodingSettings = QueueService.GetTranscodingSettings(Job, MediaFile)
        if not TranscodingSettings:
            return None
        TranscodingSettings['InputPath'] = Context.get('InputPath', '')
        for Key in ('DemucsPremixPath', 'VocalsRmsDbfs', 'PremixMeasuredI', 'PremixMeasuredLra', 'PremixMeasuredTp', 'PremixMeasuredThresh'):
            TranscodingSettings[Key] = Context.get(Key)
        CommandDict = QueueService.BuildTranscodeCommand(Job, MediaFile, TranscodingSettings)
        if not CommandDict:
            return None
        return CommandSpec(Command=CommandDict['Command'], OutputPath=CommandDict['OutputPath'])

    # directive: audio-dialog-boost-real | # see audio-normalization.C14
    def HandleResult(self, Job, Result: Dict[str, Any], TranscodeAttemptId: int, ActiveJobId: int, OutputPath: str, QueueService=None) -> None:
        Qs = QueueService or self.QueueService
        Qs.HandleTranscodingResult(Job, Result, TranscodeAttemptId, ActiveJobId)

    # directive: transcode-flow-canonical | # see transcode.ST5
    def DefaultProfileName(self, Job) -> str:
        return getattr(Job, 'AssignedProfile', None) or 'Transcode'
