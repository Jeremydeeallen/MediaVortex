from unittest.mock import MagicMock
from Features.TranscodeJob.Worker.StuckJobMonitor import StuckJobMonitor


# directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C12
class TestStuckJobMonitor:
    """StuckJobMonitor contract tests: ctor wiring + start/stop active-flag transitions."""

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C12
    def test_ctor_stashes_deps(self):
        """Constructor stashes DatabaseManager + WorkerName references."""
        Db = MagicMock()
        Monitor = StuckJobMonitor(Db, "worker-test")
        assert Monitor.DatabaseManager is Db
        assert Monitor.WorkerName == "worker-test"
        assert Monitor.MonitoringActive is False
        assert Monitor.MonitoringThread is None

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C12
    def test_start_sets_active(self):
        """After Start() is called, MonitoringActive is True."""
        Db = MagicMock()
        Monitor = StuckJobMonitor(Db, "worker-test")
        Monitor.Start()
        try:
            assert Monitor.MonitoringActive is True
        finally:
            Monitor.Stop()

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C12
    def test_stop_clears_active(self):
        """After Stop(), MonitoringActive is False."""
        Db = MagicMock()
        Monitor = StuckJobMonitor(Db, "worker-test")
        Monitor.Start()
        Monitor.Stop()
        assert Monitor.MonitoringActive is False
