import threading
from typing import Optional


class WorkerContextNotBoundError(RuntimeError):
    pass


_ThreadLocal = threading.local()
_Template: Optional['WorkerContext'] = None


# directive: transcode-flow-canonical
class WorkerContext:
    # directive: transcode-flow-canonical
    def __init__(self, WorkerName: str, Platform: str, FFmpegPath: Optional[str] = None,
                 FFprobePath: Optional[str] = None):
        self.WorkerName = WorkerName
        self.Platform = Platform
        self.FFmpegPath = FFmpegPath
        self.FFprobePath = FFprobePath

    @classmethod
    # directive: transcode-flow-canonical
    def Initialize(cls, WorkerName: str, Platform: str, FFmpegPath: Optional[str] = None,
                   FFprobePath: Optional[str] = None) -> 'WorkerContext':
        global _Template
        if _Template is not None:
            raise RuntimeError("WorkerContext already initialized")
        Ctx = cls(WorkerName, Platform, FFmpegPath, FFprobePath)
        _Template = Ctx
        _ThreadLocal.Context = Ctx
        return Ctx

    @classmethod
    # directive: transcode-flow-canonical
    def Bind(cls, Context: Optional['WorkerContext'] = None) -> 'WorkerContext':
        Ctx = Context if Context is not None else _Template
        if Ctx is None:
            raise WorkerContextNotBoundError(
                "WorkerContext.Bind: no explicit Context and no process Template initialized. "
                "Call WorkerContext.Initialize(...) at process boot or pass Context= explicitly."
            )
        _ThreadLocal.Context = Ctx
        return Ctx

    @classmethod
    # directive: transcode-flow-canonical
    def Current(cls) -> 'WorkerContext':
        Ctx = getattr(_ThreadLocal, 'Context', None)
        if Ctx is None:
            raise WorkerContextNotBoundError(
                "WorkerContext.Current called on unbound thread. "
                "Call WorkerContext.Bind() at thread entry."
            )
        return Ctx

    @classmethod
    # directive: transcode-flow-canonical
    def TryCurrent(cls) -> Optional['WorkerContext']:
        return getattr(_ThreadLocal, 'Context', None)

    @classmethod
    # directive: transcode-flow-canonical
    def Reset(cls):
        global _Template
        _Template = None
        try:
            del _ThreadLocal.Context
        except AttributeError:
            pass
