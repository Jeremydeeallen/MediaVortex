from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.AudioNormalization.SelfHealing.IAudioVerticalInvariant import IAudioVerticalInvariant


DETECT_SQL = (
    "SELECT ta.Id, ta.MediaFileId "
    "FROM TranscodeAttempts ta "
    "WHERE ta.Success = TRUE "
    "AND ta.CompletedDate IS NOT NULL "
    "AND ta.CompletedDate > NOW() - INTERVAL '30 days' "
    "AND ta.AudioTracksEmittedJson IS NULL "
    "AND ta.FileReplaced = TRUE"
)


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
class SuccessfulAttemptWithoutTracksEmitted(IAudioVerticalInvariant):
    """Detects successful + replaced attempts in the last 30 days whose AudioTracksEmittedJson is still NULL."""

    Name = "SuccessfulAttemptWithoutTracksEmitted"

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
    def Detect(self):
        """Return (TranscodeAttempts.Id, MediaFileId) pairs for attempts that need re-probing."""
        try:
            Rows = DatabaseService().ExecuteQuery(DETECT_SQL)
            return [(R['id'], R['mediafileid']) for R in (Rows or [])]
        except Exception as Ex:
            LoggingService.LogException(
                "SuccessfulAttemptWithoutTracksEmitted.Detect failed",
                Ex, self.Name, "Detect",
            )
            return []
