import re
import unittest
from pathlib import Path


_REPO = Path(__file__).resolve().parents[2]


# directive: compliance-symmetry
class TestCrossVerticalLeak(unittest.TestCase):

    # directive: compliance-symmetry
    def test_videovertical_drops_legacy_decision_logic(self):
        Source = (_REPO / 'Features' / 'VideoEncoding' / 'VideoVertical.py').read_text(encoding='utf-8')
        for Forbidden in ('EstimatedSavingsMB', 'IsAlreadyEfficient', 'MvTrusted', 'VideoComplianceRules', 'AcceptableVideoCodecsCsv'):
            self.assertNotIn(Forbidden, Source, f'VideoVertical.py still references legacy symbol: {Forbidden}')

    # directive: compliance-symmetry
    def test_containervertical_no_audio_codec_leak(self):
        Source = (_REPO / 'Features' / 'ContainerFormat' / 'ContainerVertical.py').read_text(encoding='utf-8')
        for Forbidden in ('AudioCodec', 'AcceptableAudioCodecsCsv', 'ContainerComplianceRules'):
            self.assertNotIn(Forbidden, Source, f'ContainerVertical.py still references {Forbidden}; audio belongs to AudioVertical')

    # directive: bug-0087-followup-maxaudiochannels-delete
    def test_maxaudiochannels_removed_from_audio_vertical_surface(self):
        for RelPath in (
            'Features/AudioNormalization/AudioVertical.py',
            'Features/AudioNormalization/AudioPolicyAdmissionGate.py',
            'Features/AudioNormalization/AudioNormalizationController.py',
            'Features/AudioNormalization/Repositories/AudioNormalizationConfigRepository.py',
            'Features/MediaFile/ComplianceSummaryController.py',
        ):
            Source = (_REPO / RelPath).read_text(encoding='utf-8')
            self.assertNotIn('MaxAudioChannels', Source, f'{RelPath} still references MaxAudioChannels')


if __name__ == '__main__':
    unittest.main()
