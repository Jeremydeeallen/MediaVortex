# directive: transcode-worker-unification | # see filereplacement.C4
from datetime import datetime, timezone
from typing import Optional

from Core.Logging.LoggingService import LoggingService
from Features.FileReplacement.PostFlightProcessors.ITranscodePostFlight import (
    ITranscodePostFlight, PostFlightResult,
)


# directive: transcode-worker-unification | # see filereplacement.C4
class TranscodePostFlight(ITranscodePostFlight):
    """Post-flight strategy for Mode='Transcode': sets TranscodedByMediaVortex=TRUE. # see remuxed-flag.C4"""

    # directive: transcode-worker-unification | # see filereplacement.C4
    def __init__(self, MediaFilesRepository=None):
        # see filereplacement.C4
        self._Repo = MediaFilesRepository

    # directive: transcode-worker-unification | # see filereplacement.C4
    def Execute(self, MediaFile, AttemptId: int, OutputPath: str) -> PostFlightResult:
        # see remuxed-flag.C4
        try:
            MediaFile.TranscodedByMediaVortex = True
            LoggingService.LogInfo(
                f"TranscodePostFlight: set TranscodedByMediaVortex=TRUE for MediaFile {MediaFile.Id}",
                "TranscodePostFlight", "Execute",
            )
            return PostFlightResult(Success=True)
        except Exception as Ex:
            LoggingService.LogException(
                f"TranscodePostFlight.Execute failed for AttemptId={AttemptId}",
                Ex, "TranscodePostFlight", "Execute",
            )
            return PostFlightResult(Success=False, ErrorMessage=str(Ex))
