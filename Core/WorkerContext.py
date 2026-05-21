"""Process-level singleton for per-worker configuration.

Set once at process startup (WorkerService, WebService).
Read anywhere via WorkerContext.Current(). Returns None if not initialized,
allowing callers to fall back to SystemSettings gracefully.
"""

from typing import Optional


class WorkerContext:
    _Instance = None

    def __init__(self, WorkerName: str, Platform: str, FFmpegPath: str,
                 FFprobePath: str, ShareMappings: dict, PathTranslation):
        self.WorkerName = WorkerName
        self.Platform = Platform
        self.FFmpegPath = FFmpegPath
        self.FFprobePath = FFprobePath
        self.ShareMappings = ShareMappings
        self.PathTranslation = PathTranslation

    @classmethod
    def Initialize(cls, WorkerName: str, Platform: str, FFmpegPath: str = None,
                   FFprobePath: str = None, ShareMappings: dict = None):
        """Set once at process startup. Raises if called twice."""
        if cls._Instance is not None:
            raise RuntimeError("WorkerContext already initialized")
        Translation = None
        if ShareMappings:
            from Core.Services.PathTranslationService import PathTranslationService
            Translation = PathTranslationService(MountMap=ShareMappings)
        cls._Instance = cls(WorkerName, Platform, FFmpegPath, FFprobePath,
                            ShareMappings or {}, Translation)
        return cls._Instance

    @classmethod
    def Current(cls) -> Optional['WorkerContext']:
        """Return the current context or None if not initialized."""
        return cls._Instance

    @classmethod
    def Reset(cls):
        """For testing only."""
        cls._Instance = None
