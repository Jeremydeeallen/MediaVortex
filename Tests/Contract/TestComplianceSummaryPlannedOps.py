import unittest

from Features.MediaFile.ComplianceSummary import DeriveBucket as _DeriveBucket, PlannedOps as _PlannedOps


# directive: transcode-flow-canonical -- C33k UI adapter 5-branch coverage
class TestComplianceSummaryPlannedOps(unittest.TestCase):

    def test_transcode_bucket_video_only(self):
        self.assertEqual(_PlannedOps('Transcode', False, True, True), ['video_reencode'])

    def test_transcode_bucket_video_plus_container_plus_audio(self):
        self.assertEqual(
            _PlannedOps('Transcode', False, False, False),
            ['video_reencode', 'container_rewrite', 'audio_reencode_loudnorm'],
        )

    def test_remux_bucket_container_only(self):
        self.assertEqual(_PlannedOps('Remux', True, False, True), ['container_rewrite'])

    def test_remux_bucket_container_plus_audio(self):
        self.assertEqual(
            _PlannedOps('Remux', True, False, False),
            ['container_rewrite', 'audio_reencode_loudnorm'],
        )

    def test_audiofix_bucket(self):
        self.assertEqual(_PlannedOps('AudioFix', True, True, False), ['audio_reencode_loudnorm'])

    def test_compliant_bucket_no_ops(self):
        self.assertEqual(_PlannedOps('Compliant', True, True, True), [])

    def test_unclassified_bucket_no_ops(self):
        self.assertEqual(_PlannedOps('Unclassified', None, None, None), [])

    def test_derive_bucket_null_video_is_unclassified(self):
        self.assertEqual(_DeriveBucket(None, True, True), 'Unclassified')

    def test_derive_bucket_all_true_is_compliant(self):
        self.assertEqual(_DeriveBucket(True, True, True), 'Compliant')

    def test_derive_bucket_video_false_is_transcode(self):
        self.assertEqual(_DeriveBucket(False, True, True), 'Transcode')

    def test_derive_bucket_container_false_is_remux(self):
        self.assertEqual(_DeriveBucket(True, False, True), 'Remux')

    def test_derive_bucket_audio_false_is_audiofix(self):
        self.assertEqual(_DeriveBucket(True, True, False), 'AudioFix')


if __name__ == '__main__':
    unittest.main()
