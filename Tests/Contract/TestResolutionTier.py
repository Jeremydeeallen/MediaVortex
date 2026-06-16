import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Core.Resolution.ResolutionTier import ResolutionTier
from Core.Resolution.ResolutionTierRegistry import ResolutionTierRegistry


# directive: resolution-types | # see resolution-types.C2
def _MockRepo():
    """Stub repo seeded with the same 4 canonical tiers the DB ships with."""
    Repo = MagicMock()
    Repo.GetAll.return_value = [
        ResolutionTier('T480p',  600,  854,  480,  1),
        ResolutionTier('T720p',  1100, 1280, 720,  2),
        ResolutionTier('T1080p', 1700, 1920, 1080, 3),
        ResolutionTier('T2160p', 3000, 3840, 2160, 4),
    ]
    return Repo


# directive: resolution-types | # see resolution-types.C14
class TestRegistryFromDimsMaxEdge(unittest.TestCase):
    """C14 max(Width, Height) classification -- orientation-agnostic boundary tests."""

    # directive: resolution-types | # see resolution-types.C14
    def setUp(self):
        self.Reg = ResolutionTierRegistry(_MockRepo())

    # directive: resolution-types | # see resolution-types.C14
    def test_boundary_2160p(self):
        self.assertEqual(self.Reg.FromDims(3840, 2160).Name, 'T2160p')
        self.assertEqual(self.Reg.FromDims(3000, 1500).Name, 'T2160p')
        self.assertEqual(self.Reg.FromDims(2999, 1500).Name, 'T1080p')

    # directive: resolution-types | # see resolution-types.C14
    def test_boundary_1080p(self):
        self.assertEqual(self.Reg.FromDims(1920, 1080).Name, 'T1080p')
        self.assertEqual(self.Reg.FromDims(1700, 900).Name, 'T1080p')
        self.assertEqual(self.Reg.FromDims(1699, 900).Name, 'T720p')

    # directive: resolution-types | # see resolution-types.C14
    def test_boundary_720p(self):
        self.assertEqual(self.Reg.FromDims(1280, 720).Name, 'T720p')
        self.assertEqual(self.Reg.FromDims(1100, 600).Name, 'T720p')
        self.assertEqual(self.Reg.FromDims(1099, 600).Name, 'T480p')

    # directive: resolution-types | # see resolution-types.C14
    def test_boundary_480p(self):
        self.assertEqual(self.Reg.FromDims(854, 480).Name, 'T480p')
        self.assertEqual(self.Reg.FromDims(600, 480).Name, 'T480p')
        self.assertEqual(self.Reg.FromDims(100, 100).Name, 'T480p')

    # directive: resolution-types | # see resolution-types.C14
    def test_cinematic_letterbox_1916x1040(self):
        """MIB-II regression -- cinematic 1.85:1 must land at T1080p."""
        self.assertEqual(self.Reg.FromDims(1916, 1040).Name, 'T1080p')

    # directive: resolution-types | # see resolution-types.C14
    def test_ultra_wide_1920x800(self):
        self.assertEqual(self.Reg.FromDims(1920, 800).Name, 'T1080p')

    # directive: resolution-types | # see resolution-types.C14
    def test_broadcast_720p_crop_1280x718(self):
        self.assertEqual(self.Reg.FromDims(1280, 718).Name, 'T720p')

    # directive: resolution-types | # see resolution-types.C14
    def test_portrait_fullhd_1080x1920(self):
        """Production's width-primary rule misclassified portrait FullHD as T480p; max-edge gets it right."""
        self.assertEqual(self.Reg.FromDims(1080, 1920).Name, 'T1080p')

    # directive: resolution-types | # see resolution-types.C14
    def test_portrait_4k_2160x3840(self):
        self.assertEqual(self.Reg.FromDims(2160, 3840).Name, 'T2160p')

    # directive: resolution-types | # see resolution-types.C14
    def test_square_1080_below_720p_threshold(self):
        """Square 1080x1080: max=1080 < 1100 (T720p MinLongEdge), so lands at T480p. Operator can lower the threshold via SQL if desired (resolution-types.C13)."""
        self.assertEqual(self.Reg.FromDims(1080, 1080).Name, 'T480p')

    # directive: resolution-types | # see resolution-types.C14
    def test_canonical_round_trip(self):
        for T in self.Reg.All:
            self.assertEqual(self.Reg.FromDims(T.CanonicalWidth, T.CanonicalHeight).Name, T.Name)


# directive: resolution-types | # see resolution-types.C2
class TestRegistryFromCategory(unittest.TestCase):
    """C2 legacy-category string mapping at the boundary."""

    # directive: resolution-types | # see resolution-types.C2
    def setUp(self):
        self.Reg = ResolutionTierRegistry(_MockRepo())

    # directive: resolution-types | # see resolution-types.C2
    def test_canonical_strings(self):
        self.assertEqual(self.Reg.FromCategory('480p').Name, 'T480p')
        self.assertEqual(self.Reg.FromCategory('720p').Name, 'T720p')
        self.assertEqual(self.Reg.FromCategory('1080p').Name, 'T1080p')
        self.assertEqual(self.Reg.FromCategory('2160p').Name, 'T2160p')

    # directive: resolution-types | # see resolution-types.C2
    def test_synonyms(self):
        self.assertEqual(self.Reg.FromCategory('4k').Name, 'T2160p')
        self.assertEqual(self.Reg.FromCategory('UHD').Name, 'T2160p')

    # directive: resolution-types | # see resolution-types.C2
    def test_direct_name(self):
        self.assertEqual(self.Reg.FromCategory('T1080p').Name, 'T1080p')

    # directive: resolution-types | # see resolution-types.C2
    def test_none_or_empty(self):
        self.assertIsNone(self.Reg.FromCategory(None))
        self.assertIsNone(self.Reg.FromCategory(''))
        self.assertIsNone(self.Reg.FromCategory('   '))

    # directive: resolution-types | # see resolution-types.C2
    def test_unknown_returns_none(self):
        self.assertIsNone(self.Reg.FromCategory('1440p'))
        self.assertIsNone(self.Reg.FromCategory('No downscaling'))


# directive: resolution-types | # see resolution-types.C13
class TestRegistryDataDriven(unittest.TestCase):
    """C13 tunable thresholds without code change -- registry honors DB values."""

    # directive: resolution-types | # see resolution-types.C13
    def test_custom_threshold_takes_effect(self):
        CustomRepo = MagicMock()
        CustomRepo.GetAll.return_value = [
            ResolutionTier('T480p', 0, 854, 480, 1),
            ResolutionTier('T1080p', 1500, 1920, 1080, 3),
        ]
        Reg = ResolutionTierRegistry(CustomRepo)
        self.assertEqual(Reg.FromDims(1500, 800).Name, 'T1080p')
        self.assertEqual(Reg.FromDims(1499, 800).Name, 'T480p')

    # directive: resolution-types | # see resolution-types.C13
    def test_empty_table_raises(self):
        EmptyRepo = MagicMock()
        EmptyRepo.GetAll.return_value = []
        with self.assertRaises(RuntimeError):
            ResolutionTierRegistry(EmptyRepo)

    # directive: resolution-types | # see resolution-types.C13
    def test_new_tier_added_via_db_only(self):
        """OCP probe: adding a row in the DB is enough; no code edit required to recognize a new tier."""
        FutureRepo = MagicMock()
        FutureRepo.GetAll.return_value = [
            ResolutionTier('T480p',  600,  854,  480,  1),
            ResolutionTier('T720p',  1100, 1280, 720,  2),
            ResolutionTier('T1080p', 1700, 1920, 1080, 3),
            ResolutionTier('T1440p', 2400, 2560, 1440, 4),
            ResolutionTier('T2160p', 3000, 3840, 2160, 5),
        ]
        Reg = ResolutionTierRegistry(FutureRepo)
        self.assertEqual(Reg.FromDims(2560, 1440).Name, 'T1440p')
        self.assertEqual(Reg.FromDims(2400, 1080).Name, 'T1440p')
        self.assertEqual(Reg.FromDims(2399, 1080).Name, 'T1080p')


if __name__ == '__main__':
    unittest.main()
