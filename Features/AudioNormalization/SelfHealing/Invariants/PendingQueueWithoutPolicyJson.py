from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.AudioNormalization.SelfHealing.IAudioVerticalInvariant import IAudioVerticalInvariant


DETECT_SQL = (
    "SELECT Id FROM TranscodeQueue "
    "WHERE Status = 'Pending' AND AudioPolicyJson IS NULL"
)


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
class PendingQueueWithoutPolicyJson(IAudioVerticalInvariant):
    """Detects TranscodeQueue Pending rows missing their AudioPolicyJson snapshot."""

    Name = "PendingQueueWithoutPolicyJson"

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
    def Detect(self):
        """Return TranscodeQueue.Id list for Pending rows where AudioPolicyJson is NULL."""
        try:
            Rows = DatabaseService().ExecuteQuery(DETECT_SQL)
            return [R['id'] for R in (Rows or [])]
        except Exception as Ex:
            LoggingService.LogException(
                "PendingQueueWithoutPolicyJson.Detect failed",
                Ex, self.Name, "Detect",
            )
            return []
