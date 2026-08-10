# directive: pre-encode-savings-gate | # see video-encoding.C1
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
    AssignedProfile: Optional[str] = 'AV1 Tier 1 Efficient'
    ContentClass: Optional[str] = 'live_action'
    TranscodedByMediaVortex: bool = False


class _StubDb:
    def __init__(self, ProfileTargetKbps: Optional[int] = 900,
                 Multiplier: Optional[float] = 2.0):
        self._Target = ProfileTargetKbps
        self._Multiplier = Multiplier

    def ExecuteQuery(self, Sql, Params=None):
        SqlLower = Sql.lower()
        if 'from profiles p' in SqlLower and 'profilethresholds' in SqlLower and 'profilename' in SqlLower:
            if self._Target is None:
                return []
            return [{'targetkbps': self._Target}]
        if 'videocompliancethresholds' in SqlLower:
            if self._Multiplier is None:
                return []
            return [{'multiplier': self._Multiplier}]
        return []


class TestPreEncodeSavingsGate(unittest.TestCase):

    def test_source_below_ceiling_compliant(self):
        Db = _StubDb(ProfileTargetKbps=900, Multiplier=2.0)
        Compliant, Reason = VideoVertical(Db=Db).Evaluate(_FakeMf(VideoBitrateKbps=1500))
        self.assertTrue(Compliant)
        self.assertIn('source_at_or_below_ceiling:1500<=1800', Reason)
        self.assertIn('profile=AV1 Tier 1 Efficient:900*2.0', Reason)

    def test_source_at_ceiling_compliant(self):
        Db = _StubDb(ProfileTargetKbps=900, Multiplier=2.0)
        Compliant, Reason = VideoVertical(Db=Db).Evaluate(_FakeMf(VideoBitrateKbps=1800))
        self.assertTrue(Compliant)
        self.assertIn('source_at_or_below_ceiling:1800<=1800', Reason)

    def test_source_above_ceiling_non_compliant(self):
        Db = _StubDb(ProfileTargetKbps=900, Multiplier=2.0)
        Compliant, Reason = VideoVertical(Db=Db).Evaluate(_FakeMf(VideoBitrateKbps=5000))
        self.assertFalse(Compliant)
        self.assertIn('source_above_ceiling:5000>1800', Reason)

    def test_ace_ventura_case_still_transcoded(self):
        Db = _StubDb(ProfileTargetKbps=900, Multiplier=2.0)
        Compliant, Reason = VideoVertical(Db=Db).Evaluate(_FakeMf(
            ResolutionCategory='1080p', VideoBitrateKbps=2497,
            AssignedProfile='AV1 Tier 1 Efficient',
        ))
        self.assertFalse(Compliant)
        self.assertIn('source_above_ceiling:2497>1800', Reason)

    def test_ceiling_uses_assigned_profile_not_tier1(self):
        Db = _StubDb(ProfileTargetKbps=2400, Multiplier=2.0)
        Compliant, Reason = VideoVertical(Db=Db).Evaluate(_FakeMf(
            ResolutionCategory='1080p', VideoBitrateKbps=4000,
            AssignedProfile='AV1 Tier 2 Good',
        ))
        self.assertTrue(Compliant)
        self.assertIn('source_at_or_below_ceiling:4000<=4800', Reason)
        self.assertIn('profile=AV1 Tier 2 Good:2400*2.0', Reason)

    def test_codec_no_longer_a_signal(self):
        Db = _StubDb(ProfileTargetKbps=900, Multiplier=2.0)
        Compliant, Reason = VideoVertical(Db=Db).Evaluate(_FakeMf(Codec='wmv3', VideoBitrateKbps=1500))
        self.assertTrue(Compliant)
        self.assertNotIn('codec', Reason)

    def test_no_profile_returns_none_missing_input(self):
        Db = _StubDb()
        Compliant, Reason = VideoVertical(Db=Db).Evaluate(_FakeMf(AssignedProfile=None))
        self.assertIsNone(Compliant)
        self.assertEqual(Reason, 'missing_input:AssignedProfile')

    def test_missing_profile_target_returns_none_missing_input(self):
        Db = _StubDb(ProfileTargetKbps=None)
        Compliant, Reason = VideoVertical(Db=Db).Evaluate(_FakeMf())
        self.assertIsNone(Compliant)
        self.assertIn('missing_input:ProfileTargetKbps', Reason)

    def test_missing_bitrate_returns_none_missing_input(self):
        Db = _StubDb()
        Compliant, Reason = VideoVertical(Db=Db).Evaluate(_FakeMf(VideoBitrateKbps=None))
        self.assertIsNone(Compliant)
        self.assertEqual(Reason, 'missing_input:VideoBitrateKbps')

    def test_missing_resolution_category_returns_none_missing_input(self):
        Db = _StubDb()
        Compliant, Reason = VideoVertical(Db=Db).Evaluate(_FakeMf(ResolutionCategory=None))
        self.assertIsNone(Compliant)
        self.assertEqual(Reason, 'missing_input:ResolutionCategory')

    def test_missing_multiplier_fail_loud(self):
        Db = _StubDb(Multiplier=None)
        with self.assertRaises(RuntimeError) as Ctx:
            VideoVertical(Db=Db).Evaluate(_FakeMf(VideoBitrateKbps=5000))
        self.assertIn('VideoComplianceThresholds', str(Ctx.exception))


if __name__ == '__main__':
    unittest.main()
