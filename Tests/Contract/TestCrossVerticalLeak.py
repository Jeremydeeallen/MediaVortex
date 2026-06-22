import re
import unittest
from pathlib import Path


_REPO = Path(__file__).resolve().parents[2]


# directive: compliance-symmetry
class TestCrossVerticalLeak(unittest.TestCase):

    # directive: compliance-symmetry
    def test_videovertical_drops_legacy_decision_logic(self):
        Source = (_REPO / 'Features' / 'VideoEncoding' / 'VideoVertical.py').read_text(encoding='utf-8')
        for Forbidden in ('EstimatedSavingsMB', 'IsAlreadyEfficient', 'MvTrusted', 'TranscodedByMediaVortex', 'VideoComplianceRules'):
            self.assertNotIn(Forbidden, Source, f'VideoVertical.py still references legacy symbol: {Forbidden}')

    # directive: compliance-symmetry
    def test_containervertical_no_audio_codec_leak(self):
        Source = (_REPO / 'Features' / 'ContainerFormat' / 'ContainerVertical.py').read_text(encoding='utf-8')
        for Forbidden in ('AudioCodec', 'AcceptableAudioCodecsCsv', 'ContainerComplianceRules'):
            self.assertNotIn(Forbidden, Source, f'ContainerVertical.py still references {Forbidden}; audio belongs to AudioVertical')

    # directive: compliance-symmetry
    def test_audiovertical_does_not_read_maxaudiochannels_directly(self):
        Source = (_REPO / 'Features' / 'AudioNormalization' / 'AudioVertical.py').read_text(encoding='utf-8')
        self.assertNotIn('MaxAudioChannels', Source,
                         'AudioVertical must defer channel count check to AudioPolicyAdmissionGate, not read MaxAudioChannels')

    # directive: compliance-symmetry
    def test_audiopolicyadmissiongate_owns_channel_check(self):
        Source = (_REPO / 'Features' / 'AudioNormalization' / 'AudioPolicyAdmissionGate.py').read_text(encoding='utf-8')
        self.assertIn('MaxAudioChannels', Source)
        self.assertIn('channels_exceed_max', Source)


if __name__ == '__main__':
    unittest.main()
