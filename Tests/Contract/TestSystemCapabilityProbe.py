# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C10
from unittest.mock import patch
from Features.TranscodeJob.Emit.SystemCapabilityProbe import SystemCapabilityProbe


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C10
class TestSystemCapabilityProbe:
    """Probe tests: positive int + None-handling."""

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C10
    def test_returns_positive_int(self):
        """GetMaxCpuThreads returns an int >= 1 on a normal host."""
        Probe = SystemCapabilityProbe()
        Count = Probe.GetMaxCpuThreads()
        assert isinstance(Count, int)
        assert Count >= 1

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C10
    def test_handles_none_cpu_count(self):
        """When os.cpu_count() returns None, GetMaxCpuThreads falls back to 1."""
        with patch('Features.TranscodeJob.Emit.SystemCapabilityProbe.os.cpu_count', return_value=None):
            Probe = SystemCapabilityProbe()
            assert Probe.GetMaxCpuThreads() == 1
