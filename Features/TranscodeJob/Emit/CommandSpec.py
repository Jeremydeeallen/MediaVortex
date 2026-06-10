# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C1
from dataclasses import dataclass


@dataclass(frozen=True)
# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C1
class CommandSpec:
    """Frozen value object: (ffmpeg argv string, resolved output path)."""
    Command: str
    OutputPath: str
