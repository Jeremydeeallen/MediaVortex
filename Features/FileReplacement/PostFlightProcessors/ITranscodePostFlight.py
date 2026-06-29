# directive: transcode-worker-unification | # see filereplacement.C12
from abc import ABC, abstractmethod


# directive: transcode-worker-unification | # see filereplacement.C12
class PostFlightResult:

    # directive: transcode-worker-unification | # see filereplacement.C12
    def __init__(self, Success: bool, ErrorMessage: str = None):
        # see filereplacement.C12
        self.Success = Success
        self.ErrorMessage = ErrorMessage


# directive: transcode-worker-unification | # see filereplacement.C12
class ITranscodePostFlight(ABC):

    @abstractmethod
    # directive: transcode-worker-unification | # see filereplacement.C12
    def Execute(self, MediaFile, AttemptId: int, OutputPath: str) -> PostFlightResult:
        # see filereplacement.C12
        raise NotImplementedError
