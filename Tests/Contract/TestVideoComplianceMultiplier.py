# directive: video-compliance-multiplier | # see video-encoding.C1
import unittest
from dataclasses import dataclass
from typing import Optional

from Features.VideoEncoding.VideoVertical import VideoVertical


@dataclass
class _FakeMf:
    Id: int = 1
    Codec: Optional[str] = 'h264'
    Resolution: Optional[str] = '1280x720'
    ResolutionCategory: Optional[str] = '720p'
    VideoBitrateKbps: Optional[int] = 1500
    FrameRate: Optional[float] = 24.0
    AssignedProfile: Optional[str] = 'NVENC AV1 CANARY Tier 1 -720p'
    ContentClass: Optional[str] = 'live_action'
    TranscodedByMediaVortex: bool = False


class _StubDb:
    def __init__(self, Family: Optional[str] = 'NVENC AV1 CANARY',
                 Tier1TargetKbps: Optional[int] = 900,
                 Multiplier: Optional[float] = 2.0):
        self._Family = Family
        self._Tier1 = Tier1TargetKbps
        self._Multiplier = Multiplier

    def ExecuteQuery(self, Sql, Params=None):
        SqlLower = Sql.lower()
        if 'from profiles ' in SqlLower and 'where profilename' in SqlLower:
            return [{'family': self._Family}] if self._Family else []
        if 'profilethresholds' in SqlLower and 'qualitytier = 1' in SqlLower:
            if self._Tier1 is None:
                return []
            return [{'targetkbps': self._Tier1}]
        if 'videocompliancethresholds' in SqlLower:
            if self._Multiplier is None:
                return []
            return [{'multiplier': self._Multiplier}]
        return []


class TestVideoComplianceMultiplier(unittest.TestCase):

    def test_boundary_at_720p_multiplier_2x_compliant_at_target(self):
        Db = _StubDb(Tier1TargetKbps=900, Multiplier=2.0)
        Compliant, Reason = VideoVertical(Db=Db).Evaluate(_FakeMf(VideoBitrateKbps=1800))
        self.assertTrue(Compliant)
        self.assertIn('source_at_or_below_multiplier:1800<=1800', Reason)

    def test_boundary_at_720p_multiplier_2x_below_target(self):
        Db = _StubDb(Tier1TargetKbps=900, Multiplier=2.0)
        Compliant, Reason = VideoVertical(Db=Db).Evaluate(_FakeMf(VideoBitrateKbps=1700))
        self.assertTrue(Compliant)
        self.assertIn('source_at_or_below_multiplier:1700<=1800', Reason)

    def test_boundary_at_720p_multiplier_2x_above_target(self):
        Db = _StubDb(Tier1TargetKbps=900, Multiplier=2.0)
        Compliant, Reason = VideoVertical(Db=Db).Evaluate(_FakeMf(VideoBitrateKbps=1900))
        self.assertFalse(Compliant)
        self.assertIn('source_above_multiplier:1900>1800', Reason)

    def test_boundary_at_480p_multiplier_1_5x(self):
        Db = _StubDb(Tier1TargetKbps=400, Multiplier=1.5)
        Compliant, Reason = VideoVertical(Db=Db).Evaluate(_FakeMf(ResolutionCategory='480p', VideoBitrateKbps=560))
        self.assertTrue(Compliant)
        self.assertIn('source_at_or_below_multiplier:560<=600', Reason)
        Compliant2, Reason2 = VideoVertical(Db=Db).Evaluate(_FakeMf(ResolutionCategory='480p', VideoBitrateKbps=640))
        self.assertFalse(Compliant2)
        self.assertIn('source_above_multiplier:640>600', Reason2)

    def test_boundary_at_2160p_multiplier_3x(self):
        Db = _StubDb(Tier1TargetKbps=4000, Multiplier=3.0)
        Compliant, Reason = VideoVertical(Db=Db).Evaluate(_FakeMf(ResolutionCategory='2160p', VideoBitrateKbps=11500))
        self.assertTrue(Compliant)
        self.assertIn('source_at_or_below_multiplier:11500<=12000', Reason)
        Compliant2, Reason2 = VideoVertical(Db=Db).Evaluate(_FakeMf(ResolutionCategory='2160p', VideoBitrateKbps=15000))
        self.assertFalse(Compliant2)
        self.assertIn('source_above_multiplier:15000>12000', Reason2)

    def test_codec_no_longer_a_signal(self):
        Db = _StubDb(Tier1TargetKbps=900, Multiplier=2.0)
        Compliant, Reason = VideoVertical(Db=Db).Evaluate(_FakeMf(Codec='wmv3', VideoBitrateKbps=1700))
        self.assertTrue(Compliant)
        self.assertNotIn('codec', Reason)

    def test_no_profile_falls_through_compliant(self):
        Db = _StubDb()
        Compliant, Reason = VideoVertical(Db=Db).Evaluate(_FakeMf(AssignedProfile=None))
        self.assertTrue(Compliant)
        self.assertIsNone(Reason)

    def test_missing_family_falls_through_compliant(self):
        Db = _StubDb(Family=None)
        Compliant, Reason = VideoVertical(Db=Db).Evaluate(_FakeMf())
        self.assertTrue(Compliant)
        self.assertIsNone(Reason)

    def test_missing_tier1_falls_through_compliant(self):
        Db = _StubDb(Tier1TargetKbps=None)
        Compliant, Reason = VideoVertical(Db=Db).Evaluate(_FakeMf())
        self.assertTrue(Compliant)
        self.assertIsNone(Reason)

    def test_missing_multiplier_fail_loud(self):
        Db = _StubDb(Multiplier=None)
        with self.assertRaises(RuntimeError) as Ctx:
            VideoVertical(Db=Db).Evaluate(_FakeMf())
        self.assertIn('VideoComplianceThresholds', str(Ctx.exception))

    def test_mediavortex_output_exempt(self):
        Db = _StubDb()
        Compliant, Reason = VideoVertical(Db=Db).Evaluate(_FakeMf(TranscodedByMediaVortex=True))
        self.assertTrue(Compliant)
        self.assertEqual(Reason, 'mediavortex_output_accepted')


if __name__ == '__main__':
    unittest.main()
