from datetime import datetime, timezone

from Core.Logging.LoggingService import LoggingService


# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
class ComplianceFailureRecorder:
    """Records compliance-gate refusal as a disposition override on a TranscodeAttempt (extracted from PostTranscodeDispositionService.RecordComplianceGateFailure)."""

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
    def __init__(self, DatabaseService, AttemptCleanupService):
        """Inject DatabaseService + cleanup service (DIP)."""
        self.DatabaseService = DatabaseService
        self.AttemptCleanupService = AttemptCleanupService

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
    def Record(self, TranscodeAttemptId: int, CascadeReason: str) -> None:
        """Mark attempt NoReplace/ComplianceGateFailed + ErrorMessage; idempotent; triggers TFP cleanup."""
        self._WriteErrorMessage(TranscodeAttemptId, CascadeReason)
        self._WriteDispositionOverride(TranscodeAttemptId)
        self.AttemptCleanupService.Cleanup(TranscodeAttemptId)
        LoggingService.LogInfo(
            f"Disposition overridden for TranscodeAttempt {TranscodeAttemptId}: NoReplace (Reason=ComplianceGateFailed, CascadeReason={CascadeReason})",
            "ComplianceFailureRecorder", "Record",
        )

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
    def _WriteErrorMessage(self, TranscodeAttemptId: int, CascadeReason: str) -> None:
        """UPDATE TranscodeAttempts.ErrorMessage with the cascade reason."""
        try:
            self.DatabaseService.ExecuteNonQuery(
                "UPDATE TranscodeAttempts SET ErrorMessage = %s WHERE Id = %s",
                (f'ComplianceGateFailed: {CascadeReason}', TranscodeAttemptId),
            )
        except Exception as Ex:
            LoggingService.LogException(
                f"_WriteErrorMessage failed for attempt {TranscodeAttemptId}",
                Ex, "ComplianceFailureRecorder", "_WriteErrorMessage",
            )

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
    def _WriteDispositionOverride(self, TranscodeAttemptId: int) -> None:
        """UPDATE TranscodeAttempts.Disposition='NoReplace', Reason='ComplianceGateFailed'."""
        try:
            self.DatabaseService.ExecuteNonQuery(
                "UPDATE TranscodeAttempts SET Disposition = %s, DispositionReason = %s, DispositionDecidedAt = %s WHERE Id = %s",
                ('NoReplace', 'ComplianceGateFailed', datetime.now(timezone.utc), TranscodeAttemptId),
            )
        except Exception as Ex:
            LoggingService.LogException(
                f"_WriteDispositionOverride failed for attempt {TranscodeAttemptId}",
                Ex, "ComplianceFailureRecorder", "_WriteDispositionOverride",
            )
