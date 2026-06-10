# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C1

import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.TranscodeJob.Emit.CommandSpec import CommandSpec


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C1
class TestCommandSpec:
    """Frozen-dataclass contract: instantiation, immutability, structural equality."""

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C1
    def test_instantiation_exposes_command_and_output_path(self):
        """CommandSpec stores Command and OutputPath as named attributes."""
        Spec = CommandSpec(Command='ffmpeg -i in.mkv out.mp4', OutputPath='C:/out.mp4')
        assert Spec.Command == 'ffmpeg -i in.mkv out.mp4'
        assert Spec.OutputPath == 'C:/out.mp4'

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C1
    def test_immutable_assignment_raises_frozen_instance_error(self):
        """Frozen dataclass raises FrozenInstanceError on field set."""
        Spec = CommandSpec(Command='cmd', OutputPath='path')
        with pytest.raises(FrozenInstanceError):
            Spec.Command = 'mutated'

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C1
    def test_equality_for_equivalent_instances(self):
        """Two CommandSpec values with identical fields compare equal."""
        SpecA = CommandSpec(Command='same', OutputPath='same')
        SpecB = CommandSpec(Command='same', OutputPath='same')
        assert SpecA == SpecB
