# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C10
import os


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C10
class SystemCapabilityProbe:
    """Probes runtime-host capabilities (CPU thread count, etc.)."""

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C10
    def GetMaxCpuThreads(self) -> int:
        """Return os.cpu_count() or 1 when unavailable."""
        Count = os.cpu_count()
        return Count if Count and Count > 0 else 1
