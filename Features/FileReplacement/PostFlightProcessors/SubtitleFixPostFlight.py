# directive: transcode-worker-unification | # see remuxed-flag.C4
from datetime import datetime, timezone

from Core.Logging.LoggingService import LoggingService
from Features.FileReplacement.PostFlightProcessors.ITranscodePostFlight import (
    ITranscodePostFlight, PostFlightResult,
)


# directive: transcode-worker-unification | # see remuxed-flag.C4
class SubtitleFixPostFlight(ITranscodePostFlight):
    """Post-flight strategy for Mode='SubtitleFix': sets RemuxedByMediaVortex=TRUE + date. # see remuxed-flag.C4"""

    # directive: transcode-worker-unification | # see remuxed-flag.C4
    def __init__(self, MediaFilesRepository=None):
        # see remuxed-flag.C4
        self._Repo = MediaFilesRepository

    # directive: transcode-worker-unification | # see remuxed-flag.C4
    def Execute(self, MediaFile, AttemptId: int, OutputPath: str) -> PostFlightResult:
        # see remuxed-flag.C4
        try:
            MediaFile.RemuxedByMediaVortex = True
            MediaFile.RemuxedByMediaVortexDate = datetime.now(timezone.utc)
            LoggingService.LogInfo(
                f"SubtitleFixPostFlight: set RemuxedByMediaVortex=TRUE for MediaFile {MediaFile.Id}",
                "SubtitleFixPostFlight", "Execute",
            )
            return PostFlightResult(Success=True)
        except Exception as Ex:
            LoggingService.LogException(
                f"SubtitleFixPostFlight.Execute failed for AttemptId={AttemptId}",
                Ex, "SubtitleFixPostFlight", "Execute",
            )
            return PostFlightResult(Success=False, ErrorMessage=str(Ex))
