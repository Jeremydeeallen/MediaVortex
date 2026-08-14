# directive: video-vertical-codec-match-skip | # see video-encoding.C1
import unittest
from dataclasses import dataclass
from typing import Optional

from Features.VideoEncoding.VideoVertical import VideoVertical


@dataclass
class _FakeMf:
    Id: int = 1
    Codec: Optional[str] = 'h264'
    VideoBitrateKbps: Optional[int] = 1000
    ResolutionCategory: Optional[str] = '480p'
    AssignedProfile: Optional[str] = 'AV1 Tier 1 Efficient'
    ContentClass: Optional[str] = 'live_action'
    ContainerFormat: Optional[str] = 'mp4'
    Resolution: Optional[str] = '720x480'


class _StubTiers:
    def __init__(self, Codec='av1', TargetKbps=400):
        self._Codec = Codec
        self._Target = TargetKbps

    def GetProfileCodec(self, _ProfileName):
        return self._Codec

    def GetProfileTarget(self, _ProfileName, _ContentClass, _Resolution):
        return self._Target


class _StubThresholds:
    def __init__(self, Multiplier=4.0):
        self._M = Multiplier

    def GetMultiplier(self, _Resolution):
        return self._M


class TestVideoVerticalCodecMatch(unittest.TestCase):

    def _Vert(self, TargetCodec='av1', TargetKbps=400, Multiplier=4.0):
        return VideoVertical(Thresholds=_StubThresholds(Multiplier), Tiers=_StubTiers(TargetCodec, TargetKbps))

    def test_src_matches_target_codec_is_compliant(self):
        Mf = _FakeMf(Codec='av1', VideoBitrateKbps=1500)
        Ok, Reason = self._Vert().Evaluate(Mf)
        self.assertTrue(Ok)
        self.assertIn('source_codec_matches_target', Reason)

    def test_src_differs_below_ceiling_is_compliant(self):
        Mf = _FakeMf(Codec='h264', VideoBitrateKbps=800)
        Ok, Reason = self._Vert().Evaluate(Mf)
        self.assertTrue(Ok)
        self.assertIn('source_at_or_below_ceiling', Reason)

    def test_src_differs_above_ceiling_is_noncompliant(self):
        Mf = _FakeMf(Codec='h264', VideoBitrateKbps=2000)
        Ok, Reason = self._Vert().Evaluate(Mf)
        self.assertFalse(Ok)
        self.assertIn('source_above_ceiling', Reason)

    def test_src_matches_target_above_ceiling_codec_match_wins(self):
        Mf = _FakeMf(Codec='av1', VideoBitrateKbps=5000)
        Ok, Reason = self._Vert().Evaluate(Mf)
        self.assertTrue(Ok)
        self.assertIn('source_codec_matches_target', Reason)


if __name__ == '__main__':
    unittest.main()
