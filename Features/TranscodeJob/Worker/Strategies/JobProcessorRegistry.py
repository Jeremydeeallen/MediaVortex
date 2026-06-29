# directive: transcode-worker-unification | # see worker-loop.C3
from typing import Dict, Type
from Core.Database.DatabaseService import DatabaseService
from Features.TranscodeJob.Worker.Strategies.ITranscodeJobStrategy import ITranscodeJobStrategy


# directive: transcode-worker-unification | # see worker-loop.C3
class JobProcessorRegistry:

    # directive: transcode-worker-unification | # see worker-loop.C3
    def __init__(self, Db: DatabaseService = None):
        # see worker-loop.C3
        self.Db = Db or DatabaseService()
        self._StrategyClasses: Dict[str, Type[ITranscodeJobStrategy]] = {}

    # directive: transcode-worker-unification | # see worker-loop.C3
    def Register(self, ModeName: str, StrategyClass: Type[ITranscodeJobStrategy]) -> None:
        # see worker-loop.C3
        self._StrategyClasses[ModeName] = StrategyClass

    # directive: transcode-worker-unification | # see worker-loop.C3
    def Get(self, ModeName: str, QueueService=None) -> ITranscodeJobStrategy:
        # see worker-loop.C3
        Rows = self.Db.ExecuteQuery("SELECT Name FROM ProcessingModes WHERE Name = %s LIMIT 1", (ModeName,))
        if not Rows:
            raise KeyError(f"Unknown ProcessingMode: {ModeName!r}")
        if ModeName not in self._StrategyClasses:
            raise KeyError(f"No strategy registered for ProcessingMode: {ModeName!r}")
        return self._StrategyClasses[ModeName](QueueService=QueueService)

    # directive: transcode-worker-unification | # see worker-loop.C3
    def IsModeKnown(self, ModeName: str) -> bool:
        # see worker-loop.C3
        Rows = self.Db.ExecuteQuery("SELECT 1 FROM ProcessingModes WHERE Name = %s LIMIT 1", (ModeName,))
        return bool(Rows)
