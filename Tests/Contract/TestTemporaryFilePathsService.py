from unittest.mock import MagicMock
from Features.TranscodeJob.Worker.TemporaryFilePathsService import TemporaryFilePathsService


# directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C10
class TestTemporaryFilePathsService:
    """TemporaryFilePathsService contract tests: ctor wiring + cleanup idempotency."""

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C10
    def test_ctor_stashes_deps(self):
        """TemporaryFilePathsService stores the injected DatabaseManager."""
        Db = MagicMock()
        Service = TemporaryFilePathsService(Db)
        assert Service.DatabaseManager is Db

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C10
    def test_cleanup_failed_attempt_idempotent(self):
        """Calling CleanupFailedAttempt twice with the same id raises no exception."""
        Db = MagicMock()
        Db.DatabaseService = MagicMock()
        Service = TemporaryFilePathsService(Db)
        Service.CleanupFailedAttempt(9999)
        Service.CleanupFailedAttempt(9999)
