import unittest
from dataclasses import dataclass
from typing import Optional

from Features.VideoEncoding.VideoVertical import VideoVertical


# directive: transcode-flow-canonical -- C33 profile-independent baseline
@dataclass
class _FakeMf:
    Id: int = 1
    Codec: Optional[str] = 'av1'
    Resolution: Optional[str] = '1280x720'
    ResolutionCategory: Optional[str] = '720p'
    VideoBitrateKbps: Optional[int] = 1500
    FrameRate: Optional[float] = 24.0
    AssignedProfile: Optional[str] = None
    TranscodedByMediaVortex: bool = False


# directive: transcode-flow-canonical -- C33 baseline rules injected via stub Db
class _StubDb:
    def __init__(self, AllowedCsv: str = 'av1', BppThreshold: float = 0.5):
        self._Csv = AllowedCsv
        self._Threshold = BppThreshold

    def ExecuteQuery(self, _Sql, _Params=None):
        return [{'acceptablevideocodecscsv': self._Csv, 'bpptranscodethreshold': self._Threshold}]


# directive: transcode-flow-canonical -- C33
class TestVideoComplianceBar(unittest.TestCase):

    def test_compliant_at_bar(self):
        Compliant, Reason = VideoVertical(Db=_StubDb()).Evaluate(_FakeMf())
        self.assertTrue(Compliant)
        self.assertIsNone(Reason)

    def test_codec_mismatch(self):
        Compliant, Reason = VideoVertical(Db=_StubDb()).Evaluate(_FakeMf(Codec='h264'))
        self.assertFalse(Compliant)
        self.assertIn('codec:h264', Reason)

    def test_high_bpp_flagged(self):
        # bpp = 1500000 / (1280*720*24) = 0.0678; not high. Use 50000 kbps to trip.
        Compliant, Reason = VideoVertical(Db=_StubDb(BppThreshold=0.1)).Evaluate(_FakeMf(VideoBitrateKbps=50000))
        self.assertFalse(Compliant)
        self.assertIn('high_bpp_excessive', Reason)

    def test_no_profile_needed(self):
        # AssignedProfile is None; evaluator does not care
        Compliant, Reason = VideoVertical(Db=_StubDb()).Evaluate(_FakeMf(AssignedProfile=None))
        self.assertTrue(Compliant)
        self.assertIsNone(Reason)

    def test_mediavortex_output_exempt(self):
        Compliant, Reason = VideoVertical(Db=_StubDb()).Evaluate(_FakeMf(TranscodedByMediaVortex=True))
        self.assertTrue(Compliant)
        self.assertEqual(Reason, 'mediavortex_output_accepted')


if __name__ == '__main__':
    unittest.main()
