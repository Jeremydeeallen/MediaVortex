import pytest
from Features.TranscodeJob.Worker.JobProcessor import JobProcessor
from Features.TranscodeJob.Worker.JobResult import JobResult


# directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C2
class TestJobProcessor:
    """JobProcessor tests: abstractness + concrete-subclass override."""

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C2
    def test_cannot_instantiate_abstract(self):
        """Directly instantiating JobProcessor raises TypeError (abstract Process)."""
        with pytest.raises(TypeError):
            JobProcessor()

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C2
    def test_concrete_subclass_works(self):
        """A subclass overriding Process instantiates and returns the expected JobResult."""
        # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C2
        class FakeProc(JobProcessor):
            """Fake processor returning a fixed JobResult."""
            # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C2
            def Process(self, Job, MediaFile) -> JobResult:
                """Return a fixed JobResult for assertion."""
                return JobResult(Success=True, AttemptId=1)

        Proc = FakeProc()
        Result = Proc.Process(None, None)
        assert Result.Success is True
        assert Result.AttemptId == 1
        assert Result.ErrorMessage is None
