# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C11
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from Features.TranscodeJob.Emit.CommandSpec import CommandSpec


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C11
class EncodeShape(ABC):
    """Strategy: build a CommandSpec from a (MediaFile, Job, Context) triple."""

    @abstractmethod
    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C11
    def Build(self, MediaFile, Job, Context: Dict[str, Any]) -> Optional[CommandSpec]:
        """Build the ffmpeg argv + resolved output path for this shape; None when the shape refuses."""
        raise NotImplementedError
