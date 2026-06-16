from Core.Database.DatabaseService import DatabaseService


REASON_OPERATOR_REVIEW_PENDING = 'operator_review_pending'
REASON_UNGAINABLE_ALL_STREAMS = 'ungainable_all_streams'

REVIEW_REASONS = (REASON_OPERATOR_REVIEW_PENDING, REASON_UNGAINABLE_ALL_STREAMS)


SET_REVIEW_REASON_SQL = (
    "UPDATE MediaFiles SET AdmissionDeferReason = %s WHERE Id = %s"
)


CLEAR_REVIEW_REASON_SQL = (
    "UPDATE MediaFiles SET AdmissionDeferReason = NULL WHERE Id = %s"
)


LIST_REVIEW_QUEUE_SQL = (
    "SELECT Id, FileName, AdmissionDeferReason, "
    "SourceIntegratedLufs, SourceLoudnessRangeLU, SourceTruePeakDbtp, "
    "AudioCodec, AudioChannels, AudioLanguages "
    "FROM MediaFiles "
    "WHERE AdmissionDeferReason = ANY(%s) "
    "ORDER BY Id"
)


COUNT_REVIEW_QUEUE_SQL = (
    "SELECT COUNT(*) AS Cnt FROM MediaFiles WHERE AdmissionDeferReason = ANY(%s)"
)


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C6
class AudioOperatorReviewService:
    """Operator-review queue backed by MediaFiles.AdmissionDeferReason; no boot-time cache per db-is-authority."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C6
    def AddToReviewQueue(self, MediaFileId, Reason=REASON_OPERATOR_REVIEW_PENDING):
        """Mark a MediaFile for operator review by writing AdmissionDeferReason."""
        if Reason not in REVIEW_REASONS:
            raise ValueError(f"Reason must be one of {REVIEW_REASONS}; got {Reason!r}")
        DatabaseService().ExecuteNonQuery(SET_REVIEW_REASON_SQL, (Reason, MediaFileId))

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C6
    def ListReviewQueue(self):
        """Return every MediaFile currently held for operator review."""
        return DatabaseService().ExecuteQuery(LIST_REVIEW_QUEUE_SQL, (list(REVIEW_REASONS),))

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C6
    def CountReviewQueue(self):
        """Return the number of MediaFiles currently held for operator review."""
        Rows = DatabaseService().ExecuteQuery(COUNT_REVIEW_QUEUE_SQL, (list(REVIEW_REASONS),))
        return int(Rows[0]['cnt']) if Rows else 0

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C6
    def ResolveReview(self, MediaFileId):
        """Clear AdmissionDeferReason so the file becomes admittable again on the next gate pass."""
        DatabaseService().ExecuteNonQuery(CLEAR_REVIEW_REASON_SQL, (MediaFileId,))
