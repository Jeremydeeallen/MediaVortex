import pytest
from Features.TranscodeJob.Worker.JobProcessor import JobProcessor
from Features.TranscodeJob.Worker.JobProcessorRegistry import JobProcessorRegistry
from Features.TranscodeJob.Worker.JobResult import JobResult


# directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C7
class StubProcessor(JobProcessor):
    """Stub JobProcessor for registry tests."""

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C7
    def __init__(self, Label: str):
        """Capture a label so test can identify which stub was returned."""
        self.Label = Label

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C7
    def Process(self, Job, MediaFile) -> JobResult:
        """Return a JobResult tagged with the stub's label."""
        return JobResult(Success=True, ErrorMessage=self.Label)


# directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C7
class TestJobProcessorRegistry:
    """JobProcessorRegistry tests: injection + KeyError + five-mode coverage."""

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C7
    def test_get_returns_injected_strategy(self):
        """Get('Transcode') returns the exact strategy injected for that mode."""
        Stub = StubProcessor('Transcode')
        Registry = JobProcessorRegistry({'Transcode': Stub})
        assert Registry.Get('Transcode') is Stub

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C7
    def test_get_unknown_raises_keyerror(self):
        """Empty registry raises KeyError on Get."""
        Registry = JobProcessorRegistry({})
        with pytest.raises(KeyError):
            Registry.Get('Unknown')

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C7
    def test_supports_five_modes(self):
        """All five processing modes are retrievable when injected."""
        Modes = ['Transcode', 'Remux', 'Quick', 'AudioFix', 'SubtitleFix']
        Strategies = {Mode: StubProcessor(Mode) for Mode in Modes}
        Registry = JobProcessorRegistry(Strategies)
        for Mode in Modes:
            Returned = Registry.Get(Mode)
            assert Returned is Strategies[Mode]
