# directive: transcode-flow-canonical | # see video-encoding.C3
import unittest
from dataclasses import dataclass
from typing import Optional

from Features.VideoEncoding.VideoVertical import VideoVertical


# directive: transcode-flow-canonical | # see video-encoding.C3
@dataclass
class _FakeMf:
    Id: int = 1
    Codec: Optional[str] = 'av1'
    Resolution: Optional[str] = '1280x720'
    ResolutionCategory: Optional[str] = '720p'
    VideoBitrateKbps: Optional[int] = 1500
    FrameRate: Optional[float] = 24.0
    AssignedProfile: Optional[str] = 'AV1 Tier 1 Efficient'
    ContentClass: Optional[str] = 'live_action'
    TranscodedByMediaVortex: bool = False


# directive: transcode-flow-canonical | # see video-encoding.C3
class _StubDb:
    def __init__(self, AllowedCsv: str = 'av1', TargetKbps: Optional[int] = 900):
        self._Csv = AllowedCsv
        self._Target = TargetKbps

    def ExecuteQuery(self, Sql, Params=None):
        SqlLower = Sql.lower()
        if 'videocompliancerules' in SqlLower:
            return [{'acceptablevideocodecscsv': self._Csv}]
        if 'profilethresholds' in SqlLower:
            if self._Target is None:
                return []
            return [{'targetkbps': self._Target}]
        return []


# directive: transcode-flow-canonical | # see video-encoding.C3
class TestVideoComplianceBar(unittest.TestCase):

    def test_codec_mismatch(self):
        Compliant, Reason = VideoVertical(Db=_StubDb(AllowedCsv='av1')).Evaluate(_FakeMf(Codec='h264'))
        self.assertFalse(Compliant)
        self.assertIn('codec:h264', Reason)

    def test_source_at_or_below_target(self):
        Compliant, Reason = VideoVertical(Db=_StubDb(TargetKbps=900)).Evaluate(_FakeMf(VideoBitrateKbps=800))
        self.assertTrue(Compliant)
        self.assertIn('source_at_or_below_target:800<=900', Reason)

    def test_source_equal_to_target(self):
        Compliant, Reason = VideoVertical(Db=_StubDb(TargetKbps=900)).Evaluate(_FakeMf(VideoBitrateKbps=900))
        self.assertTrue(Compliant)
        self.assertIn('source_at_or_below_target:900<=900', Reason)

    def test_source_above_target(self):
        Compliant, Reason = VideoVertical(Db=_StubDb(TargetKbps=900)).Evaluate(_FakeMf(VideoBitrateKbps=2000))
        self.assertFalse(Compliant)
        self.assertIn('source_above_target:2000>900', Reason)

    def test_no_profile_falls_through_compliant(self):
        Compliant, Reason = VideoVertical(Db=_StubDb()).Evaluate(_FakeMf(AssignedProfile=None))
        self.assertTrue(Compliant)
        self.assertIsNone(Reason)

    def test_no_threshold_row_falls_through_compliant(self):
        Compliant, Reason = VideoVertical(Db=_StubDb(TargetKbps=None)).Evaluate(_FakeMf())
        self.assertTrue(Compliant)
        self.assertIsNone(Reason)

    def test_mediavortex_output_exempt(self):
        Compliant, Reason = VideoVertical(Db=_StubDb()).Evaluate(_FakeMf(TranscodedByMediaVortex=True))
        self.assertTrue(Compliant)
        self.assertEqual(Reason, 'mediavortex_output_accepted')


if __name__ == '__main__':
    unittest.main()
