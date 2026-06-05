from typing import Optional


# directive: path-perfect-implementation | # see workercontext.C2
class WorkerContext:
    _Instance = None

    # directive: path-perfect-implementation | # see workercontext.C2
    def __init__(self, WorkerName: str, Platform: str, FFmpegPath: str,
                 FFprobePath: str):
        self.WorkerName = WorkerName
        self.Platform = Platform
        self.FFmpegPath = FFmpegPath
        self.FFprobePath = FFprobePath

    @classmethod
    # directive: path-perfect-implementation | # see workercontext.C2
    def Initialize(cls, WorkerName: str, Platform: str, FFmpegPath: str = None,
                   FFprobePath: str = None):
        if cls._Instance is not None:
            raise RuntimeError("WorkerContext already initialized")
        cls._Instance = cls(WorkerName, Platform, FFmpegPath, FFprobePath)
        return cls._Instance

    @classmethod
    # directive: path-perfect-implementation | # see workercontext.C2
    def Current(cls) -> Optional['WorkerContext']:
        return cls._Instance

    @classmethod
    # directive: path-perfect-implementation | # see workercontext.C2
    def Reset(cls):
        cls._Instance = None
