from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.AudioNormalization.LoudnessMeasurementValidator import LoudnessMeasurementValidator
from Features.AudioNormalization.Measurement.EbuR128MeasurementService import EbuR128MeasurementService


REASON_INVALID_LOUDNESS = 'invalid_loudness_measurement'
REASON_AWAITING_LOUDNESS = 'awaiting_loudness_measurement'
REASON_OPERATOR_REVIEW = 'operator_review_pending'


FIND_CANDIDATES_SQL = (
    "SELECT mf.Id, mf.FileName, mf.StorageRootId, mf.RelativePath, "
    "mf.SourceIntegratedLufs, mf.SourceLoudnessRangeLU, mf.SourceTruePeakDbtp, "
    "mf.SourceIntegratedThresholdLufs, mf.AdmissionDeferReason "
    "FROM MediaFiles mf "
    "WHERE mf.AdmissionDeferReason = %s "
    "ORDER BY mf.Id "
    "LIMIT %s"
)


CLEAR_DEFER_REASON_SQL = (
    "UPDATE MediaFiles SET AdmissionDeferReason = NULL WHERE Id = %s"
)


SET_REVIEW_SQL = (
    "UPDATE MediaFiles SET AdmissionDeferReason = %s WHERE Id = %s"
)


MARK_FOR_REMEASUREMENT_SQL = (
    "UPDATE MediaFiles SET AdmissionDeferReason = %s "
    "WHERE Id = %s AND (AdmissionDeferReason IS NULL OR AdmissionDeferReason <> %s)"
)


LOAD_BY_ID_SQL = (
    "SELECT Id, FileName, SourceIntegratedLufs, SourceLoudnessRangeLU, "
    "SourceTruePeakDbtp, SourceIntegratedThresholdLufs, AdmissionDeferReason "
    "FROM MediaFiles WHERE Id = %s"
)


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
class AudioRemeasurementService:
    """Re-runs ebur128 on files with invalid measurements; clears defer reason when result is valid."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    def __init__(self, MeasurementService=None, Validator=None):
        """Inject the measurement service + validator; default-construct when omitted."""
        self.Measurement = MeasurementService or EbuR128MeasurementService()
        self.Validator = Validator or LoudnessMeasurementValidator()

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    def MarkForRemeasurement(self, MediaFileId, Reason=REASON_INVALID_LOUDNESS):
        """Set AdmissionDeferReason so the next sweep picks the file up (idempotent)."""
        DatabaseService().ExecuteNonQuery(
            MARK_FOR_REMEASUREMENT_SQL, (Reason, MediaFileId, Reason)
        )

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    def FindCandidates(self, Limit=100, Reason=REASON_INVALID_LOUDNESS):
        """Return up to Limit MediaFiles rows with AdmissionDeferReason marked for re-measurement."""
        return DatabaseService().ExecuteQuery(FIND_CANDIDATES_SQL, (Reason, int(Limit)))

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    def Process(self, MediaFileId, LocalFilePath, AudioStreamIndex=0):
        """Run ebur128 against the file; persist; clear defer reason on valid result; return (Success, Reason)."""
        Success, Reason = self.Measurement.MeasureAndPersist(
            MediaFileId, LocalFilePath, AudioStreamIndex,
        )
        if not Success:
            LoggingService.LogWarning(
                f"AudioRemeasurement: measurement failed for MediaFileId={MediaFileId}: {Reason}",
                "AudioRemeasurementService", "Process",
            )
            return False, Reason

        Reloaded = DatabaseService().ExecuteQuery(LOAD_BY_ID_SQL, (MediaFileId,))
        if not Reloaded:
            LoggingService.LogWarning(
                f"AudioRemeasurement: MediaFileId={MediaFileId} disappeared during re-measurement",
                "AudioRemeasurementService", "Process",
            )
            return False, 'mediafile_gone'

        MfRow = Reloaded[0]
        if self.Validator.IsValid(MfRow):
            DatabaseService().ExecuteNonQuery(CLEAR_DEFER_REASON_SQL, (MediaFileId,))
            return True, None

        DatabaseService().ExecuteNonQuery(SET_REVIEW_SQL, (REASON_OPERATOR_REVIEW, MediaFileId))
        return True, 'routed_to_operator_review'

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    def CountPending(self, Reason=REASON_INVALID_LOUDNESS):
        """Return the number of files awaiting re-measurement."""
        Rows = DatabaseService().ExecuteQuery(
            "SELECT COUNT(*) AS Cnt FROM MediaFiles WHERE AdmissionDeferReason = %s",
            (Reason,),
        )
        return int(Rows[0]['cnt']) if Rows else 0
