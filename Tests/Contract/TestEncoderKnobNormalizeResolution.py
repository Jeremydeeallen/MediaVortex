import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.Profiles.TierLadderRepository import TierLadderRepository


# directive: resolution-types, profile-row-lookup | # see resolution-types.C4, profile-tier-ladder.C9
class TestEncoderKnobNormalizeResolution(unittest.TestCase):
    """Live-registry classification at the ProfileThresholds-lookup boundary. Closes the upstream bucketing bug that made cinematic letterbox 1916x1040 resolve to '720p' (no-downscale) and silently drop the scale filter."""

    # directive: resolution-types | # see resolution-types.C4
    def setUp(self):
        self.Normalize = TierLadderRepository.NormalizeResolution

    # directive: resolution-types | # see resolution-types.C4
    def test_cinematic_letterbox_1916x1040_is_1080p(self):
        """MIB-II regression: 1916x1040 must bucket to '1080p', not '720p'."""
        self.assertEqual(self.Normalize('1916x1040'), '1080p')

    # directive: resolution-types | # see resolution-types.C4
    def test_ultra_wide_1920x800_is_1080p(self):
        self.assertEqual(self.Normalize('1920x800'), '1080p')

    # directive: resolution-types | # see resolution-types.C4
    def test_letterbox_4k_3840x1600_is_2160p(self):
        self.assertEqual(self.Normalize('3840x1600'), '2160p')

    # directive: resolution-types | # see resolution-types.C4
    def test_broadcast_720p_crop_1280x718_is_720p(self):
        self.assertEqual(self.Normalize('1280x718'), '720p')

    # directive: resolution-types | # see resolution-types.C4
    def test_canonical_dimensions_round_trip(self):
        self.assertEqual(self.Normalize('854x480'), '480p')
        self.assertEqual(self.Normalize('1280x720'), '720p')
        self.assertEqual(self.Normalize('1920x1080'), '1080p')
        self.assertEqual(self.Normalize('3840x2160'), '2160p')

    # directive: resolution-types | # see resolution-types.C4
    def test_portrait_fullhd_classifies_by_max_edge(self):
        self.assertEqual(self.Normalize('1080x1920'), '1080p')

    # directive: resolution-types | # see resolution-types.C4
    def test_passthrough_non_wxh_strings(self):
        self.assertEqual(self.Normalize('1080p'), '1080p')
        self.assertEqual(self.Normalize(''), '')

    # directive: resolution-types | # see resolution-types.C4
    def test_malformed_input_returns_input(self):
        self.assertEqual(self.Normalize('abcxdef'), 'abcxdef')


if __name__ == '__main__':
    unittest.main()
