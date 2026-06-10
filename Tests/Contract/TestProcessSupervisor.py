from unittest.mock import MagicMock, patch
from Features.TranscodeJob.Worker.ProcessSupervisor import ProcessSupervisor


# directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C13
class TestProcessSupervisor:
    """ProcessSupervisor contract tests: ctor wiring + StopAllActive smoke."""

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C13
    def test_ctor_stashes_deps(self):
        """Constructor stashes DatabaseManager + ActiveJobs reference."""
        Db = MagicMock()
        ActiveJobs = []
        Supervisor = ProcessSupervisor(Db, ActiveJobs)
        assert Supervisor.DatabaseManager is Db
        assert Supervisor.ActiveJobs is ActiveJobs

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C13
    def test_stop_all_active_returns_dict(self):
        """With no active video-transcoding jobs, StopAllActive returns a Success dict."""
        Db = MagicMock()
        Supervisor = ProcessSupervisor(Db, [])
        FakeVideoService = MagicMock()
        FakeVideoService.GetActiveJobs.return_value = []
        with patch('Features.TranscodeJob.VideoTranscodingService.VideoTranscodingService',
                   return_value=FakeVideoService):
            Result = Supervisor.StopAllActive()
        assert isinstance(Result, dict)
        assert Result.get("Success") is True
        assert Result.get("StoppedCount") == 0
