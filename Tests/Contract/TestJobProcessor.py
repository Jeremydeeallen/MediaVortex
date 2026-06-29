import pytest
from Features.TranscodeJob.Worker.JobProcessor import JobProcessor
from Features.TranscodeJob.Worker.JobResult import JobResult


# directive: transcode-worker-unification | # see worker-loop.C2
class TestJobProcessor:
    """JobProcessor tests: constructor contract + subclass override."""

    # directive: transcode-worker-unification | # see worker-loop.C2
    def test_requires_queue_service_and_registry(self):
        """JobProcessor() with no args raises TypeError (required positional args)."""
        with pytest.raises(TypeError):
            JobProcessor()

    # directive: transcode-worker-unification | # see worker-loop.C2
    def test_concrete_subclass_can_override_process(self):
        """A subclass overriding Process instantiates and returns the expected JobResult."""
        # directive: transcode-worker-unification | # see worker-loop.C2
        class FakeProc(JobProcessor):
            # directive: transcode-worker-unification | # see worker-loop.C2
            def __init__(self):
                pass
            # directive: transcode-worker-unification | # see worker-loop.C2
            def Process(self, Job, MediaFile=None) -> JobResult:
                return JobResult(Success=True, AttemptId=1)

        Proc = FakeProc()
        Result = Proc.Process(None, None)
        assert Result.Success is True
        assert Result.AttemptId == 1
        assert Result.ErrorMessage is None
