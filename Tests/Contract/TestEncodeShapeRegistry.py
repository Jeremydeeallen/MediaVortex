# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C15
import pytest
from typing import Optional, Dict, Any
from Features.TranscodeJob.Emit.EncodeShape import EncodeShape
from Features.TranscodeJob.Emit.EncodeShapeRegistry import EncodeShapeRegistry
from Features.TranscodeJob.Emit.CommandSpec import CommandSpec


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C15
class StubShape(EncodeShape):
    """Stub shape carrying a tag string so retrieval can be asserted."""

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C15
    def __init__(self, Tag: str):
        """Stash tag identifier for retrieval assertions."""
        self.Tag = Tag

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C15
    def Build(self, MediaFile, Job, Context: Dict[str, Any]) -> Optional[CommandSpec]:
        """Return a CommandSpec whose Command is the stub tag."""
        return CommandSpec(Command=self.Tag, OutputPath='out.mp4')


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C15
class TestEncodeShapeRegistry:
    """Registry tests: injected strategy retrieval + KeyError on unknown."""

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C15
    def test_get_returns_injected_strategy(self):
        """Get returns the exact strategy instance the registry was constructed with."""
        Strategy = StubShape('Transcode')
        Registry = EncodeShapeRegistry({'Transcode': Strategy})
        assert Registry.Get('Transcode') is Strategy

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C15
    def test_get_unknown_raises_keyerror(self):
        """Get raises KeyError for a ProcessingMode not present in the registry."""
        Registry = EncodeShapeRegistry({})
        with pytest.raises(KeyError):
            Registry.Get('Foo')

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C15
    def test_supports_three_modes(self):
        """Registry retrieves all three Phase-2 modes (Transcode/Remux/SubtitleFix)."""
        T = StubShape('T')
        R = StubShape('R')
        S = StubShape('S')
        Registry = EncodeShapeRegistry({'Transcode': T, 'Remux': R, 'SubtitleFix': S})
        assert Registry.Get('Transcode') is T
        assert Registry.Get('Remux') is R
        assert Registry.Get('SubtitleFix') is S
