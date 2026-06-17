from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.AudioNormalization.SelfHealing.IAudioVerticalInvariant import IAudioVerticalInvariant


DETECT_SQL = (
    "SELECT Id FROM MediaFiles "
    "WHERE AdmissionDeferReason IN ('operator_review_pending', 'ungainable_all_streams') "
    "AND COALESCE(LoudnessMeasuredAt, '1970-01-01'::timestamp) < NOW() - INTERVAL '30 days'"
)


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
class StaleOperatorReview(IAudioVerticalInvariant):
    """Detects MediaFiles held for operator review for more than 30 days without resolution."""

    Name = "StaleOperatorReview"

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
    def Detect(self):
        """Return MediaFiles.Id list for stale review-queue entries."""
        try:
            Rows = DatabaseService().ExecuteQuery(DETECT_SQL)
            return [R['id'] for R in (Rows or [])]
        except Exception as Ex:
            LoggingService.LogException(
                "StaleOperatorReview.Detect failed",
                Ex, self.Name, "Detect",
            )
            return []
