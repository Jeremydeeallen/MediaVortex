from Core.Logging.LoggingService import LoggingService


# directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
class AttemptCleanupService:
    """Deletes TemporaryFilePaths rows for terminal-disposition TranscodeAttempts (extracted from PostTranscodeDispositionService)."""

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
    def __init__(self, DatabaseService):
        """Inject the DatabaseService (DIP)."""
        self.DatabaseService = DatabaseService

    # directive: perfect-solid-transcode-pipeline | # see perfect-solid-transcode-pipeline.C8
    def Cleanup(self, TranscodeAttemptId: int) -> None:
        """Delete TFP row for the given attempt; idempotent; failures logged but never raised."""
        try:
            self.DatabaseService.ExecuteNonQuery(
                "DELETE FROM TemporaryFilePaths WHERE TranscodeAttemptId = %s",
                (TranscodeAttemptId,),
            )
        except Exception as Ex:
            LoggingService.LogException(
                f"Cleanup failed for attempt {TranscodeAttemptId}",
                Ex, "AttemptCleanupService", "Cleanup",
            )
