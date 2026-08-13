# directive: transcode-worker-unification | # see worker-loop.C3
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


# directive: videoslotstrategy-persisted | # see worker-loop.C2
class CommandSpec:
    def __init__(self, Command, OutputPath, VideoSlotStrategy=''):
        self.Command = Command
        self.OutputPath = OutputPath
        self.VideoSlotStrategy = VideoSlotStrategy


# directive: transcode-worker-unification | # see worker-loop.C3
class ITranscodeJobStrategy(ABC):

    @abstractmethod
    # directive: transcode-worker-unification | # see worker-loop.C3
    def BuildCommand(self, Job, MediaFile, Context: Dict[str, Any]) -> CommandSpec:
        # see worker-loop.C3
        raise NotImplementedError

    @abstractmethod
    # directive: transcode-worker-unification | # see worker-loop.C3
    def HandleResult(self, Job, Result: Dict[str, Any], TranscodeAttemptId: int, ActiveJobId: int, OutputPath: str) -> None:
        # see worker-loop.C3
        raise NotImplementedError

