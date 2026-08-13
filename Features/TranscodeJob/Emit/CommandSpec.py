# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C1
from dataclasses import dataclass


@dataclass(frozen=True)
# directive: videoslotstrategy-persisted | # see perfect-solid-transcode-pipeline-phase2.C1
class CommandSpec:
    Command: str
    OutputPath: str
    VideoSlotStrategy: str = ''
