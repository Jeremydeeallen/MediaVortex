import unittest
from dataclasses import dataclass
from typing import Optional

from Core.Database.DatabaseService import DatabaseService
from Features.Profiles.EffectiveProfile import EffectiveProfile
from Features.AudioNormalization.AudioVertical import AudioVertical
from Features.AudioNormalization.AudioPolicyAdmissionGate import ADMITTED, AdmissionDecision


# directive: compliance-symmetry
@dataclass
class _FakeMf:
    Id: int = 1
    AudioCodec: Optional[str] = 'aac'
    AudioBitrateKbps: Optional[int] = 128
    AudioComplete: Optional[bool] = True
    AudioCorruptSuspect: Optional[bool] = False
    HasExplicitEnglishAudio: Optional[bool] = True
    LoudnessMeasurementFailureReason: Optional[str] = None
    Resolution: Optional[str] = '1280x720'
    AssignedProfile: Optional[str] = 'Test'
    AudioChannels: Optional[int] = 2


# directive: compliance-symmetry
class _StubResolver:
    def __init__(self, P): self._P = P
    def Resolve(self, _): return self._P


# directive: compliance-symmetry
class _AdmitGate:
    def AdmitOrDefer(self, _Mf, IntendedProcessingMode=None):
        return AdmissionDecision(Outcome=ADMITTED, DeferReason=None, PolicyJson=None)


# directive: compliance-symmetry
def _Vert(Profile):
    return AudioVertical(Gate=_AdmitGate(), ProfileResolver=_StubResolver(Profile))


class TestAudioComplianceBar(unittest.TestCase):

    # directive: compliance-symmetry
    def _BaseProfile(self, **O):
        Defaults = dict(ProfileName='Test', AudioCodec='aac', TargetAudioKbps=128, Container='mp4')
        Defaults.update(O)
        return EffectiveProfile(**Defaults)

    # directive: compliance-symmetry
    def test_compliant_when_codec_bitrate_and_audiocomplete_pass(self):
        self.assertEqual(_Vert(self._BaseProfile()).Evaluate(_FakeMf()), (True, None))

    # directive: compliance-symmetry
    def test_codec_mismatch(self):
        Mf = _FakeMf(AudioCodec='eac3')
        C, R = _Vert(self._BaseProfile()).Evaluate(Mf)
        self.assertFalse(C)
        self.assertIn('codec:eac3', R)

    # directive: compliance-symmetry
    def test_bitrate_over_tolerance(self):
        Mf = _FakeMf(AudioBitrateKbps=200)
        C, R = _Vert(self._BaseProfile()).Evaluate(Mf)
        self.assertFalse(C)
        self.assertIn('bitrate', R)

    # directive: compliance-symmetry
    def test_null_target_audio_kbps_skips_bitrate(self):
        Mf = _FakeMf(AudioBitrateKbps=99999)
        C, _ = _Vert(self._BaseProfile(TargetAudioKbps=None)).Evaluate(Mf)
        self.assertTrue(C)

    # directive: compliance-symmetry
    def test_audiocomplete_false_returns_false(self):
        Mf = _FakeMf(AudioComplete=False)
        C, R = _Vert(self._BaseProfile()).Evaluate(Mf)
        self.assertFalse(C)
        self.assertEqual(R, 'needs_normalization')

    # directive: compliance-symmetry
    def test_undecidable_no_english_audio(self):
        Mf = _FakeMf(HasExplicitEnglishAudio=False)
        C, R = _Vert(self._BaseProfile()).Evaluate(Mf)
        self.assertIsNone(C)
        self.assertEqual(R, 'no_english_audio')

    # directive: compliance-symmetry
    def test_undecidable_audio_corrupt_suspect(self):
        Mf = _FakeMf(AudioCorruptSuspect=True)
        C, R = _Vert(self._BaseProfile()).Evaluate(Mf)
        self.assertIsNone(C)
        self.assertEqual(R, 'audio_corrupt_suspect')

    # directive: compliance-symmetry
    def test_max_audio_channels_lives_on_audionormalizationconfig_not_profiles(self):
        Db = DatabaseService()
        Rows = Db.ExecuteQuery(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='profiles' AND column_name='maxaudiochannels'"
        )
        self.assertEqual(Rows, [], 'Profiles must NOT carry MaxAudioChannels; it lives on AudioNormalizationConfig')
        Rows2 = Db.ExecuteQuery(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='audionormalizationconfig' AND column_name='maxaudiochannels'"
        )
        self.assertEqual(len(Rows2), 1, 'AudioNormalizationConfig.MaxAudioChannels must exist')


if __name__ == '__main__':
    unittest.main()
