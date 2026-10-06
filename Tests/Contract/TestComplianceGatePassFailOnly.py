# directive: tv-video-rule-tier1 | # see compliance-gated-rename.C5
import unittest
from unittest.mock import patch

from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService


_CANDIDATE = {'Id': 1, 'ContainerFormat': 'mp4', 'AudioCodec': 'aac', 'VideoBitrateKbps': 99999,
              'ResolutionCategory': '720p', 'Codec': 'av1', 'TranscodedByMediaVortex': True}


# directive: tv-video-rule-tier1 | # see compliance-gated-rename.C5
class TestComplianceGatePassFailOnly(unittest.TestCase):

    # directive: tv-video-rule-tier1 | # see compliance-gated-rename.C5
    def _Evaluate(self, Container, Audio):
        Service = QueueManagementBusinessService.__new__(QueueManagementBusinessService)
        with patch('Features.ContainerFormat.ContainerVertical.ContainerVertical.Evaluate', return_value=Container), \
             patch('Features.AudioNormalization.AudioVertical.AudioVertical.Evaluate', return_value=Audio), \
             patch('Features.VideoEncoding.VideoVertical.VideoVertical.Evaluate', side_effect=AssertionError('video must not be judged for our own output')):
            return Service.EvaluateCandidateCompliance(dict(_CANDIDATE))

    # directive: tv-video-rule-tier1 | # see compliance-gated-rename.C5
    def test_pass_carries_no_bucket(self):
        Result = self._Evaluate((True, None), (True, None))
        self.assertEqual(Result, {'IsCompliant': True, 'RefusalReason': None})

    # directive: tv-video-rule-tier1 | # see compliance-gated-rename.C5
    def test_audio_failure_reports_audio_reason(self):
        Result = self._Evaluate((True, None), (False, 'no_dialog_boost'))
        self.assertEqual(Result, {'IsCompliant': False, 'RefusalReason': 'no_dialog_boost'})

    # directive: tv-video-rule-tier1 | # see compliance-gated-rename.C5
    def test_container_failure_reports_container_reason(self):
        Result = self._Evaluate((False, 'container:mkv'), (True, None))
        self.assertEqual(Result, {'IsCompliant': False, 'RefusalReason': 'container:mkv'})

    # directive: tv-video-rule-tier1 | # see compliance-gated-rename.C5
    def test_undecided_dimension_is_not_a_pass(self):
        Result = self._Evaluate((True, None), (None, 'invalid_loudness_measurement'))
        self.assertEqual(Result, {'IsCompliant': None, 'RefusalReason': 'invalid_loudness_measurement'})


if __name__ == '__main__':
    unittest.main()
