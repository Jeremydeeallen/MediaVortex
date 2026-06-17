from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.AudioNormalization.SelfHealing.IAudioVerticalInvariant import IAudioVerticalInvariant


DETECT_SQL = (
    "SELECT mf.Id FROM MediaFiles mf "
    "WHERE mf.AdmissionDeferReason = 'invalid_loudness_measurement' "
    "AND mf.LoudnessMeasuredAt < NOW() - INTERVAL '24 hours'"
)


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
class InvalidMeasurementWithoutRemeasure(IAudioVerticalInvariant):
    """Detects MediaFiles marked invalid_loudness_measurement aged > 24h without a recent re-measurement attempt."""

    Name = "InvalidMeasurementWithoutRemeasure"

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
    def Detect(self):
        """Return MediaFiles.Id list for invalid measurements that should have been re-measured by now."""
        try:
            Rows = DatabaseService().ExecuteQuery(DETECT_SQL)
            return [R['id'] for R in (Rows or [])]
        except Exception as Ex:
            LoggingService.LogException(
                "InvalidMeasurementWithoutRemeasure.Detect failed",
                Ex, self.Name, "Detect",
            )
            return []
