# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C11
import pytest
from typing import Optional, Dict, Any
from Features.TranscodeJob.Emit.EncodeShape import EncodeShape
from Features.TranscodeJob.Emit.CommandSpec import CommandSpec


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C11
class TestEncodeShape:
    """EncodeShape tests: abstractness + concrete-subclass override."""

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C11
    def test_cannot_instantiate_abstract(self):
        """Directly instantiating EncodeShape raises TypeError (abstract Build)."""
        with pytest.raises(TypeError):
            EncodeShape()

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C11
    def test_concrete_subclass_works(self):
        """A subclass overriding Build instantiates and returns the expected CommandSpec."""
        # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C11
        class FakeShape(EncodeShape):
            """Fake shape returning a fixed CommandSpec."""
            # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C11
            def Build(self, MediaFile, Job, Context: Dict[str, Any]) -> Optional[CommandSpec]:
                """Return a fixed CommandSpec for assertion."""
                return CommandSpec(Command='ffmpeg -i in out', OutputPath='out.mp4')

        Shape = FakeShape()
        Spec = Shape.Build(None, None, {})
        assert Spec is not None
        assert Spec.Command == 'ffmpeg -i in out'
        assert Spec.OutputPath == 'out.mp4'
