# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C8
"""Verify VideoFilterBuilder yadif+scale composition (pure value computation)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.TranscodeJob.Emit.VideoFilterBuilder import VideoFilterBuilder


# directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C8
class TestVideoFilterBuilder(unittest.TestCase):
    """C8: VideoFilterBuilder composes yadif (when interlaced) + optional scale filter."""

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C8
    def test_yadif_applied_when_interlaced(self):
        """IsInterlaced=True prepends yadif=1:1:1."""
        Builder = VideoFilterBuilder()
        Result = Builder.Build(ProfileSettings={}, ScaleFilter=None, IsInterlaced=True)
        self.assertEqual(Result, 'yadif=1:1:1')

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C8
    def test_yadif_absent_when_progressive(self):
        """IsInterlaced=False does not emit yadif."""
        Builder = VideoFilterBuilder()
        Result = Builder.Build(ProfileSettings={}, ScaleFilter='scale=w=1280:h=-2', IsInterlaced=False)
        self.assertIsNotNone(Result)
        self.assertNotIn('yadif', Result)
        self.assertIn('scale=w=1280:h=-2', Result)

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C8
    def test_scale_appended_after_yadif(self):
        """When both interlaced + scale, yadif comes first then scale (comma-joined)."""
        Builder = VideoFilterBuilder()
        Result = Builder.Build(ProfileSettings={}, ScaleFilter='scale=w=1280:h=-2', IsInterlaced=True)
        self.assertEqual(Result, 'yadif=1:1:1,scale=w=1280:h=-2')

    # directive: perfect-solid-transcode-pipeline-phase2 | # see perfect-solid-transcode-pipeline-phase2.C8
    def test_none_returned_when_no_filters_needed(self):
        """Progressive + no scale -> None (no -vf flag will be emitted)."""
        Builder = VideoFilterBuilder()
        Result = Builder.Build(ProfileSettings={}, ScaleFilter=None, IsInterlaced=False)
        self.assertIsNone(Result)


if __name__ == '__main__':
    unittest.main()
