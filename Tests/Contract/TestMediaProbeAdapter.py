# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C9
from unittest.mock import patch
from Features.TranscodeJob.Emit.MediaProbeAdapter import MediaProbeAdapter


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C9
class TestMediaProbeAdapter:
    """Adapter tests: ctor stash + exception isolation."""

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C9
    def test_ctor_stashes_ffprobepath(self):
        """Ctor stores the injected FFprobePath verbatim on the instance."""
        Adapter = MediaProbeAdapter('C:\\ffprobe.exe')
        assert Adapter.FFprobePath == 'C:\\ffprobe.exe'

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C9
    def test_run_analysis_returns_none_on_exception(self):
        """RunAnalysis swallows inner exceptions and returns None instead of propagating."""
        with patch('Services.FFmpegAnalysisService.FFmpegAnalysisService') as MockSvc:
            MockSvc.side_effect = RuntimeError("boom")
            Adapter = MediaProbeAdapter('C:\\ffprobe.exe')
            Result = Adapter.RunAnalysis('C:\\input.mkv')
            assert Result is None
