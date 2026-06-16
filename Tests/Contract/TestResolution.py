import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Core.Resolution.Resolution import Resolution
from Core.Resolution.ResolutionTier import ResolutionTier
from Core.Resolution.ResolutionTierRegistry import ResolutionTierRegistry


# directive: resolution-types | # see resolution-types.C1
def _MockRegistry():
    Repo = MagicMock()
    Repo.GetAll.return_value = [
        ResolutionTier('T480p',  600,  854,  480,  1),
        ResolutionTier('T720p',  1100, 1280, 720,  2),
        ResolutionTier('T1080p', 1700, 1920, 1080, 3),
        ResolutionTier('T2160p', 3000, 3840, 2160, 4),
    ]
    return ResolutionTierRegistry(Repo)


# directive: resolution-types | # see resolution-types.C1
class TestResolutionFromAny(unittest.TestCase):
    """C1 boundary parsing -- the SOLE string parser."""

    # directive: resolution-types | # see resolution-types.C1
    def setUp(self):
        self.Reg = _MockRegistry()

    # directive: resolution-types | # see resolution-types.C1
    def test_canonical_1080p_pixels(self):
        R = Resolution.FromAny('1920x1080', Registry=self.Reg)
        self.assertEqual(R.Width, 1920)
        self.assertEqual(R.Height, 1080)
        self.assertEqual(R.Tier.Name, 'T1080p')
        self.assertAlmostEqual(R.AspectRatio, 1.778, places=2)

    # directive: resolution-types | # see resolution-types.C1
    def test_cinematic_letterbox_1916x1040(self):
        """MIB-II regression: cinematic 1.85:1 must bucket to T1080p."""
        R = Resolution.FromAny('1916x1040', Registry=self.Reg)
        self.assertEqual(R.Width, 1916)
        self.assertEqual(R.Height, 1040)
        self.assertEqual(R.Tier.Name, 'T1080p')
        self.assertAlmostEqual(R.AspectRatio, 1.842, places=2)

    # directive: resolution-types | # see resolution-types.C1
    def test_ultra_wide_1920x800(self):
        R = Resolution.FromAny('1920x800', Registry=self.Reg)
        self.assertEqual(R.Tier.Name, 'T1080p')

    # directive: resolution-types | # see resolution-types.C1
    def test_anamorphic_853x480(self):
        R = Resolution.FromAny('853x480', Registry=self.Reg)
        self.assertEqual(R.Tier.Name, 'T480p')

    # directive: resolution-types | # see resolution-types.C1
    def test_portrait_fullhd(self):
        R = Resolution.FromAny('1080x1920', Registry=self.Reg)
        self.assertEqual(R.Tier.Name, 'T1080p')

    # directive: resolution-types | # see resolution-types.C1
    def test_canonical_category_string(self):
        R = Resolution.FromAny('720p', Registry=self.Reg)
        self.assertEqual(R.Tier.Name, 'T720p')
        self.assertEqual(R.Width, 1280)
        self.assertEqual(R.Height, 720)

    # directive: resolution-types | # see resolution-types.C1
    def test_tuple_passthrough(self):
        R = Resolution.FromAny((1280, 720), Registry=self.Reg)
        self.assertEqual(R.Tier.Name, 'T720p')

    # directive: resolution-types | # see resolution-types.C1
    def test_resolution_idempotent(self):
        R1 = Resolution.FromAny('1916x1040', Registry=self.Reg)
        R2 = Resolution.FromAny(R1, Registry=self.Reg)
        self.assertIs(R1, R2)

    # directive: resolution-types | # see resolution-types.C1
    def test_none_and_empty(self):
        self.assertIsNone(Resolution.FromAny(None, Registry=self.Reg))
        self.assertIsNone(Resolution.FromAny('', Registry=self.Reg))
        self.assertIsNone(Resolution.FromAny('   ', Registry=self.Reg))

    # directive: resolution-types | # see resolution-types.C1
    def test_invalid_string_returns_none(self):
        self.assertIsNone(Resolution.FromAny('garbage', Registry=self.Reg))
        self.assertIsNone(Resolution.FromAny('1280', Registry=self.Reg))
        self.assertIsNone(Resolution.FromAny('xx', Registry=self.Reg))
        self.assertIsNone(Resolution.FromAny('axb', Registry=self.Reg))

    # directive: resolution-types | # see resolution-types.C1
    def test_zero_or_negative_dims_return_none(self):
        self.assertIsNone(Resolution.FromAny('0x720', Registry=self.Reg))
        self.assertIsNone(Resolution.FromAny('1280x0', Registry=self.Reg))

    # directive: resolution-types | # see resolution-types.C1
    def test_case_insensitive(self):
        R = Resolution.FromAny('1920X1080', Registry=self.Reg)
        self.assertEqual(R.Tier.Name, 'T1080p')


if __name__ == '__main__':
    unittest.main()
