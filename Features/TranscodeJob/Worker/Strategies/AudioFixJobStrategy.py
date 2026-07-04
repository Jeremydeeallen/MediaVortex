# directive: transcode-worker-unification | # see worker-loop.C3
from typing import Any, Dict, Optional
from Core.Logging.LoggingService import LoggingService
from Features.TranscodeJob.Worker.Strategies.ITranscodeJobStrategy import CommandSpec, ITranscodeJobStrategy


# directive: transcode-worker-unification | # see worker-loop.C3
class AudioFixJobStrategy(ITranscodeJobStrategy):

    # directive: transcode-worker-unification | # see worker-loop.C3
    def __init__(self, QueueService=None):
        # see worker-loop.C3
        self.QueueService = QueueService

    # directive: transcode-flow-canonical | # see transcode.ST5
    def BuildCommand(self, Job, MediaFile, Context: Dict[str, Any]) -> Optional[CommandSpec]:
        QueueService = Context.get('QueueService') or self.QueueService
        _Spec = QueueService.CommandComposer.Build(MediaFile, Job, Context=Context)
        if not _Spec:
            return None
        return CommandSpec(Command=_Spec.Command, OutputPath=_Spec.OutputPath)

    # directive: transcode-worker-unification | # see worker-loop.C3
    def HandleResult(self, Job, Result: Dict[str, Any], TranscodeAttemptId: int, ActiveJobId: int, OutputPath: str, QueueService=None) -> None:
        # see worker-loop.C3
        Qs = QueueService or self.QueueService
        Qs.HandleRemuxResult(Job, Result, TranscodeAttemptId, ActiveJobId, OutputPath)

    # directive: transcode-flow-canonical | # see transcode.ST5
    def DefaultProfileName(self, Job) -> str:
        return 'AudioFix'
