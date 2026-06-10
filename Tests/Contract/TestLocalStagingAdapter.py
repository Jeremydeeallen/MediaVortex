from unittest.mock import MagicMock
from Features.TranscodeJob.Worker.LocalStagingAdapter import LocalStagingAdapter


# directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C11
class TestLocalStagingAdapter:
    """LocalStagingAdapter contract tests: ctor wiring + inactive-path passthrough."""

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C11
    def test_ctor_stashes_deps(self):
        """LocalStagingAdapter stores the injected DatabaseManager + WorkerName."""
        Db = MagicMock()
        Adapter = LocalStagingAdapter(Db, 'worker-larry-1')
        assert Adapter.DatabaseManager is Db
        assert Adapter.WorkerName == 'worker-larry-1'

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C11
    def test_get_local_staging_paths_returns_none_when_inactive(self):
        """When LocalScratchDir is empty for the worker, GetLocalStagingPathsIfActive returns (None, None)."""
        Db = MagicMock()
        Db.DatabaseService = MagicMock()
        Db.DatabaseService.ExecuteQuery.return_value = [{'localscratchdir': ''}]
        Adapter = LocalStagingAdapter(Db, 'worker-larry-1')
        Result = Adapter.GetLocalStagingPathsIfActive('/some/source.mkv', '/some/output.mp4')
        assert Result == (None, None)
