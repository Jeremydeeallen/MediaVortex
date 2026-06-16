import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Core.Resolution.Resolution import Resolution
from Core.Resolution.ResolutionTier import ResolutionTier
from Core.Resolution.ResolutionTierRegistry import ResolutionTierRegistry
from Core.Resolution.ScalePolicy import WidthAnchoredScalePolicy, ScaleFilter


# directive: resolution-types | # see resolution-types.C3
def _MockRegistry():
    Repo = MagicMock()
    Repo.GetAll.return_value = [
        ResolutionTier('T480p',  600,  854,  480,  1),
        ResolutionTier('T720p',  1100, 1280, 720,  2),
        ResolutionTier('T1080p', 1700, 1920, 1080, 3),
        ResolutionTier('T2160p', 3000, 3840, 2160, 4),
    ]
    return ResolutionTierRegistry(Repo)


# directive: resolution-types | # see resolution-types.C3
class TestWidthAnchoredScalePolicy(unittest.TestCase):
    """C3 sole producer of scale-filter values. MIB-II regression + every tier pair."""

    # directive: resolution-types | # see resolution-types.C3
    def setUp(self):
        self.Reg = _MockRegistry()
        self.Policy = WidthAnchoredScalePolicy()
        self.T720 = self.Reg.Get('T720p')
        self.T1080 = self.Reg.Get('T1080p')

    # directive: resolution-types | # see resolution-types.C3
    def test_mib_ii_regression_1916x1040_to_720p(self):
        """The bug we are fixing: 1916x1040 source against -720p profile must emit scale=w=1280:h=-2."""
        Source = Resolution.FromAny('1916x1040', Registry=self.Reg)
        Decision = self.Policy.Decide(Source, self.T720)
        self.assertIsNotNone(Decision)
        self.assertEqual(Decision.AsFfmpegArg(), 'scale=w=1280:h=-2')

    # directive: resolution-types | # see resolution-types.C3
    def test_same_tier_no_scale(self):
        """Off-canonical pixels at the same tier must NOT trigger a scale."""
        Source = Resolution.FromAny('1916x1040', Registry=self.Reg)
        Decision = self.Policy.Decide(Source, self.T1080)
        self.assertIsNone(Decision)

    # directive: resolution-types | # see resolution-types.C3
    def test_upscale_blocked(self):
        Source = Resolution.FromAny('853x480', Registry=self.Reg)
        Decision = self.Policy.Decide(Source, self.T1080)
        self.assertIsNone(Decision)

    # directive: resolution-types | # see resolution-types.C3
    def test_every_downscale_pair_emits_target_canonical_width(self):
        for Src in self.Reg.All:
            for Tgt in self.Reg.All:
                if Src.Rank <= Tgt.Rank:
                    continue
                SourceRes = Resolution.FromAny((Src.CanonicalWidth, Src.CanonicalHeight), Registry=self.Reg)
                Decision = self.Policy.Decide(SourceRes, Tgt)
                with self.subTest(src=Src.Name, tgt=Tgt.Name):
                    self.assertIsNotNone(Decision)
                    self.assertEqual(Decision.Width, Tgt.CanonicalWidth)
                    self.assertEqual(Decision.HeightExpr, '-2')

    # directive: resolution-types | # see resolution-types.C3
    def test_ultra_wide_aspect_preserved_via_filter_shape(self):
        """2.40:1 source: filter carries width=1280 + h=-2; FFmpeg derives height from source aspect at runtime."""
        Source = Resolution.FromAny('1920x800', Registry=self.Reg)
        Decision = self.Policy.Decide(Source, self.T720)
        self.assertEqual(Decision.AsFfmpegArg(), 'scale=w=1280:h=-2')

    # directive: resolution-types | # see resolution-types.C3
    def test_none_inputs_return_none(self):
        Source = Resolution.FromAny('1080p', Registry=self.Reg)
        self.assertIsNone(self.Policy.Decide(None, self.T720))
        self.assertIsNone(self.Policy.Decide(Source, None))


# directive: resolution-types | # see resolution-types.C3
class TestScaleFilter(unittest.TestCase):
    """C3 value object emission."""

    # directive: resolution-types | # see resolution-types.C3
    def test_default_height_expr_negative_two(self):
        F = ScaleFilter(Width=1280)
        self.assertEqual(F.AsFfmpegArg(), 'scale=w=1280:h=-2')

    # directive: resolution-types | # see resolution-types.C3
    def test_custom_height_expr(self):
        F = ScaleFilter(Width=854, HeightExpr='480')
        self.assertEqual(F.AsFfmpegArg(), 'scale=w=854:h=480')


if __name__ == '__main__':
    unittest.main()
