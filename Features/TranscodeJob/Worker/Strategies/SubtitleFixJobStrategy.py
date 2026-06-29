# directive: transcode-worker-unification | # see worker-loop.C3
from typing import Any, Dict, Optional
from Core.Path.LocalPath import LocalDirname
from Core.Logging.LoggingService import LoggingService
from Features.TranscodeJob.Worker.Strategies.ITranscodeJobStrategy import CommandSpec, ITranscodeJobStrategy


# directive: transcode-worker-unification | # see worker-loop.C3
class SubtitleFixJobStrategy(ITranscodeJobStrategy):

    # directive: transcode-worker-unification | # see worker-loop.C3
    def __init__(self, QueueService=None):
        # see worker-loop.C3
        self.QueueService = QueueService

    # directive: transcode-worker-unification | # see worker-loop.C3
    def BuildCommand(self, Job, MediaFile, Context: Dict[str, Any]) -> Optional[CommandSpec]:
        # see worker-loop.C3
        QueueService = Context.get('QueueService') or self.QueueService
        InputPath = Context.get('InputPath', '')
        _Spec = QueueService.EncodeShapeRegistry.Get('SubtitleFix').Build(
            MediaFile, Job,
            Context={
                'InputPath': InputPath,
                'FFmpegPath': Context.get('FFmpegPath', ''),
                'FFprobePath': Context.get('FFprobePath', ''),
                'OutputDirectory': LocalDirname(InputPath) if InputPath else '',
            },
        )
        if not _Spec:
            return None
        return CommandSpec(Command=_Spec.Command, OutputPath=_Spec.OutputPath)

    # directive: transcode-worker-unification | # see worker-loop.C3
    def HandleResult(self, Job, Result: Dict[str, Any], TranscodeAttemptId: int, ActiveJobId: int, OutputPath: str, QueueService=None) -> None:
        # see worker-loop.C3
        Qs = QueueService or self.QueueService
        Qs.HandleRemuxResult(Job, Result, TranscodeAttemptId, ActiveJobId, OutputPath)
