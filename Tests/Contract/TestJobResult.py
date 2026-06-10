import pytest
from dataclasses import FrozenInstanceError
from Features.TranscodeJob.Worker.JobResult import JobResult


# directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C1
class TestJobResult:
    """JobResult tests: defaults + immutability + equality."""

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C1
    def test_instantiation_with_required_only(self):
        """JobResult with only Success has None AttemptId and ErrorMessage."""
        Result = JobResult(Success=True)
        assert Result.Success is True
        assert Result.AttemptId is None
        assert Result.ErrorMessage is None

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C1
    def test_immutability_raises(self):
        """Assignment to any field raises FrozenInstanceError."""
        Result = JobResult(Success=True, AttemptId=42)
        with pytest.raises(FrozenInstanceError):
            Result.Success = False
        with pytest.raises(FrozenInstanceError):
            Result.AttemptId = 99
        with pytest.raises(FrozenInstanceError):
            Result.ErrorMessage = 'boom'

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C1
    def test_equality(self):
        """Two JobResult instances with the same args are equal."""
        A = JobResult(Success=True, AttemptId=7, ErrorMessage=None)
        B = JobResult(Success=True, AttemptId=7, ErrorMessage=None)
        assert A == B
