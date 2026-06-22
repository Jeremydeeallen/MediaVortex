import unittest
from dataclasses import dataclass
from typing import Optional

from Core.Resolution.ResolutionTier import ResolutionTier
from Features.Profiles.EffectiveProfile import EffectiveProfile
from Features.VideoEncoding.VideoVertical import VideoVertical


# directive: compliance-symmetry
@dataclass
class _FakeMf:
    Id: int = 1
    Codec: Optional[str] = 'av1'
    ResolutionCategory: Optional[str] = '720p'
    VideoBitrateKbps: Optional[int] = 1500
    AssignedProfile: Optional[str] = 'Test'


# directive: compliance-symmetry
class _StubResolver:
    def __init__(self, Profile):
        self._P = Profile

    def Resolve(self, _Mf):
        return self._P


# directive: compliance-symmetry
def _Tier(Cat: str) -> ResolutionTier:
    from Core.Resolution.ResolutionTierRegistry import ResolutionTierRegistry
    return ResolutionTierRegistry().FromCategory(Cat)


# directive: compliance-symmetry
def _Vert(Profile):
    return VideoVertical(ProfileResolver=_StubResolver(Profile))


class TestVideoComplianceBar(unittest.TestCase):

    # directive: compliance-symmetry
    def _BaseProfile(self, **Overrides):
        Defaults = dict(
            ProfileName='Test',
            StreamCodecName='av1',
            TargetResolutionCategory=_Tier('720p'),
            TargetVideoKbps=1500,
            AllowUpscale=False,
            AudioCodec='aac',
            TargetAudioKbps=128,
            Container='mp4',
        )
        Defaults.update(Overrides)
        return EffectiveProfile(**Defaults)

    # directive: compliance-symmetry
    def test_compliant_at_bar(self):
        Mf = _FakeMf()
        Profile = self._BaseProfile()
        self.assertEqual(_Vert(Profile).Evaluate(Mf), (True, None))

    # directive: compliance-symmetry
    def test_codec_mismatch(self):
        Mf = _FakeMf(Codec='h264')
        Profile = self._BaseProfile()
        Compliant, Reason = _Vert(Profile).Evaluate(Mf)
        self.assertFalse(Compliant)
        self.assertIn('codec:h264', Reason)

    # directive: compliance-symmetry
    def test_resolution_too_high(self):
        Mf = _FakeMf(ResolutionCategory='1080p')
        Profile = self._BaseProfile()
        Compliant, Reason = _Vert(Profile).Evaluate(Mf)
        self.assertFalse(Compliant)
        self.assertIn('resolution', Reason)

    # directive: compliance-symmetry
    def test_resolution_below_without_upscale(self):
        Mf = _FakeMf(ResolutionCategory='480p')
        Profile = self._BaseProfile(AllowUpscale=False)
        Compliant, Reason = _Vert(Profile).Evaluate(Mf)
        self.assertTrue(Compliant)
        self.assertEqual(Reason, 'upscale_prevented')

    # directive: compliance-symmetry
    def test_resolution_below_with_upscale(self):
        Mf = _FakeMf(ResolutionCategory='480p', VideoBitrateKbps=500)
        Profile = self._BaseProfile(AllowUpscale=True)
        Compliant, _ = _Vert(Profile).Evaluate(Mf)
        self.assertTrue(Compliant)

    # directive: compliance-symmetry
    def test_bitrate_within_5pct_tolerance(self):
        Mf = _FakeMf(VideoBitrateKbps=1574)
        Profile = self._BaseProfile(TargetVideoKbps=1500)
        Compliant, Reason = _Vert(Profile).Evaluate(Mf)
        self.assertTrue(Compliant, msg=f'Expected compliant within 5%, got {Reason}')

    # directive: compliance-symmetry
    def test_bitrate_over_5pct_tolerance(self):
        Mf = _FakeMf(VideoBitrateKbps=1700)
        Profile = self._BaseProfile(TargetVideoKbps=1500)
        Compliant, Reason = _Vert(Profile).Evaluate(Mf)
        self.assertFalse(Compliant)
        self.assertIn('bitrate', Reason)

    # directive: compliance-symmetry
    def test_null_target_kbps_skips_bitrate_check(self):
        Mf = _FakeMf(VideoBitrateKbps=999999)
        Profile = self._BaseProfile(TargetVideoKbps=None)
        Compliant, _ = _Vert(Profile).Evaluate(Mf)
        self.assertTrue(Compliant)

    # directive: compliance-symmetry
    def test_no_effective_profile_returns_none(self):
        Mf = _FakeMf()
        Compliant, Reason = VideoVertical(ProfileResolver=_StubResolver(None)).Evaluate(Mf)
        self.assertIsNone(Compliant)
        self.assertEqual(Reason, 'no_effective_profile')


if __name__ == '__main__':
    unittest.main()
