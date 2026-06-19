from Core.Database.DatabaseService import DatabaseService


REASON_OPERATOR_REVIEW_PENDING = 'operator_review_pending'
REASON_UNGAINABLE_ALL_STREAMS = 'ungainable_all_streams'
REASON_INVALID_LOUDNESS_MEASUREMENT = 'invalid_loudness_measurement'
REASON_LOUDNESS_MEASUREMENTS = 'LoudnessMeasurements'
REASON_AWAITING_SPEECH_ENRICHMENT = 'awaiting_speech_enrichment'

WRITABLE_REVIEW_REASONS = (REASON_OPERATOR_REVIEW_PENDING, REASON_UNGAINABLE_ALL_STREAMS)
REVIEW_REASONS = (
    REASON_OPERATOR_REVIEW_PENDING,
    REASON_UNGAINABLE_ALL_STREAMS,
    REASON_INVALID_LOUDNESS_MEASUREMENT,
    REASON_LOUDNESS_MEASUREMENTS,
    REASON_AWAITING_SPEECH_ENRICHMENT,
)


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
        if Reason not in WRITABLE_REVIEW_REASONS:
            raise ValueError(f"Reason must be one of {WRITABLE_REVIEW_REASONS}; got {Reason!r}")
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

    # directive: audio-review-queue-grouping | # see audio-normalization.C6
    def GroupedSummary(self):
        """Return per-reason groups with counts, work-bucket breakdown chips, and up-to-5 preview samples."""
        Db = DatabaseService()
        Groups = Db.ExecuteQuery(
            "SELECT AdmissionDeferReason AS reason, "
            "COUNT(*)::int AS total, "
            "COUNT(*) FILTER (WHERE WorkBucket = 'AudioFixOnly')::int AS audio_only, "
            "COUNT(*) FILTER (WHERE 'Transcode' = ANY(string_to_array(COALESCE(OperationsNeededCsv, ''), ',')))::int AS needs_transcode, "
            "COUNT(*) FILTER (WHERE 'Remux' = ANY(string_to_array(COALESCE(OperationsNeededCsv, ''), ',')))::int AS needs_remux, "
            "COUNT(*) FILTER (WHERE WorkBucket IS NULL)::int AS no_bucket "
            "FROM MediaFiles "
            "WHERE AdmissionDeferReason = ANY(%s) "
            "GROUP BY AdmissionDeferReason "
            "ORDER BY total DESC",
            (list(REVIEW_REASONS),),
        )
        Out = []
        for G in (Groups or []):
            Samples = Db.ExecuteQuery(
                "SELECT Id, FileName, SourceIntegratedLufs, SourceTruePeakDbtp, WorkBucket "
                "FROM MediaFiles WHERE AdmissionDeferReason = %s "
                "ORDER BY Id LIMIT 5",
                (G['reason'],),
            )
            Out.append({
                'AdmissionDeferReason': G['reason'],
                'Total': int(G['total']),
                'AudioOnly': int(G['audio_only']),
                'NeedsTranscode': int(G['needs_transcode']),
                'NeedsRemux': int(G['needs_remux']),
                'NoBucket': int(G['no_bucket']),
                'Samples': Samples or [],
            })
        return Out

    # directive: audio-review-queue-grouping | # see audio-normalization.C6
    def BulkClearByReason(self, Reason):
        """Clear AdmissionDeferReason for every MediaFile carrying the given reason; return cleared count + ids."""
        if Reason not in REVIEW_REASONS:
            raise ValueError(f"Reason must be one of {REVIEW_REASONS}; got {Reason!r}")
        Db = DatabaseService()
        Ids = [R['id'] for R in (Db.ExecuteQuery(
            "SELECT Id FROM MediaFiles WHERE AdmissionDeferReason = %s", (Reason,),
        ) or [])]
        if not Ids:
            return {'Cleared': 0, 'Ids': []}
        Db.ExecuteNonQuery(
            "UPDATE MediaFiles SET AdmissionDeferReason = NULL WHERE AdmissionDeferReason = %s",
            (Reason,),
        )
        return {'Cleared': len(Ids), 'Ids': Ids}
