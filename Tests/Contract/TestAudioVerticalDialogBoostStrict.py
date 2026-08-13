# directive: audio-vertical-dialog-boost-enforcement | # see audio-vertical-dialog-boost-enforcement.C6
import unittest
from dataclasses import dataclass
from typing import Optional
from unittest.mock import patch

from Features.AudioNormalization.AudioVertical import AudioVertical
from Features.AudioNormalization.AudioPolicyAdmissionGate import ADMITTED, AdmissionDecision


@dataclass
class _FakeMf:
    Id: int = 1
    AudioCodec: Optional[str] = 'aac'
    AudioComplete: Optional[bool] = False
    AudioCorruptSuspect: Optional[bool] = False
    HasExplicitEnglishAudio: Optional[bool] = True
    Resolution: Optional[str] = '1920x1080'
    AudioChannels: Optional[int] = 2
    ContainerFormat: Optional[str] = 'mp4'
    TranscodedByMediaVortex: Optional[bool] = False
    HasDialogBoostTrack: Optional[bool] = False


class _AdmitGate:
    def AdmitOrDefer(self, _Mf, IntendedProcessingMode=None):
        return AdmissionDecision(Outcome=ADMITTED, DeferReason=None, PolicyJson=None)


def _StubRules():
    return {
        'TargetIntegratedLufs': -23.0,
        'TargetTruePeakDbtp': -1.0,
        'AllowedCodecs': ['aac', 'ac3', 'eac3', 'mp3'],
    }


class TestAudioVerticalDialogBoostStrict(unittest.TestCase):

    def _Vert(self):
        V = AudioVertical(Gate=_AdmitGate())
        V._LoadRules = _StubRules
        return V

    def test_transcoded_with_dialog_boost_is_compliant(self):
        Mf = _FakeMf(TranscodedByMediaVortex=True, HasDialogBoostTrack=True)
        Compliant, Reason = self._Vert().Evaluate(Mf)
        self.assertTrue(Compliant)
        self.assertIsNone(Reason)

    def test_transcoded_without_dialog_boost_is_noncompliant(self):
        Mf = _FakeMf(TranscodedByMediaVortex=True, HasDialogBoostTrack=False)
        Compliant, Reason = self._Vert().Evaluate(Mf)
        self.assertFalse(Compliant)
        self.assertEqual(Reason, 'no_dialog_boost')

    def test_untranscoded_at_target_lufs_is_noncompliant(self):
        Mf = _FakeMf(TranscodedByMediaVortex=False, HasDialogBoostTrack=False, AudioComplete=True)
        Compliant, Reason = self._Vert().Evaluate(Mf)
        self.assertFalse(Compliant)
        self.assertEqual(Reason, 'no_dialog_boost')

    def test_untranscoded_not_at_target_is_noncompliant(self):
        Mf = _FakeMf(TranscodedByMediaVortex=False, HasDialogBoostTrack=False, AudioComplete=False)
        Compliant, Reason = self._Vert().Evaluate(Mf)
        self.assertFalse(Compliant)
        self.assertEqual(Reason, 'no_dialog_boost')


if __name__ == '__main__':
    unittest.main()
