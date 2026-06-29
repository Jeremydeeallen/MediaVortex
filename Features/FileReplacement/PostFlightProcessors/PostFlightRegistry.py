# directive: transcode-worker-unification | # see filereplacement.C12
from typing import Dict, Type
from Features.FileReplacement.PostFlightProcessors.ITranscodePostFlight import ITranscodePostFlight


# directive: transcode-worker-unification | # see filereplacement.C12
class PostFlightRegistry:

    # directive: transcode-worker-unification | # see filereplacement.C12
    def __init__(self):
        # see filereplacement.C12
        self._StrategyClasses: Dict[str, Type[ITranscodePostFlight]] = {}

    # directive: transcode-worker-unification | # see filereplacement.C12
    def Register(self, ModeName: str, StrategyClass: Type[ITranscodePostFlight]) -> None:
        # see filereplacement.C12
        self._StrategyClasses[ModeName] = StrategyClass

    # directive: transcode-worker-unification | # see filereplacement.C12
    def Get(self, ModeName: str) -> ITranscodePostFlight:
        # see filereplacement.C12
        if ModeName not in self._StrategyClasses:
            raise KeyError(f"No post-flight registered for ProcessingMode: {ModeName!r}")
        return self._StrategyClasses[ModeName]()
