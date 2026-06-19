import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.Services.AudioOperatorReviewService import (
    AudioOperatorReviewService,
    REVIEW_REASONS,
)


# directive: audio-review-queue-grouping | # see audio-normalization.C6
class TestGroupedSummaryAndBulkClear(unittest.TestCase):
    """G1/G2 live: grouped summary returns counts + samples; bulk clear flips defer reason without touching IsCompliant."""

    # directive: audio-review-queue-grouping | # see audio-normalization.C6
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('MEDIAVORTEX_DB_HOST', '10.0.0.15')

    # directive: audio-review-queue-grouping | # see audio-normalization.C6
    def test_grouped_summary_returns_per_reason_breakdown(self):
        Groups = AudioOperatorReviewService().GroupedSummary()
        for G in Groups:
            self.assertIn(G['AdmissionDeferReason'], REVIEW_REASONS)
            self.assertGreaterEqual(G['Total'], 0)
            self.assertEqual(
                G['AudioOnly'] + G['NeedsTranscode'] >= 0,
                True,
            )
            self.assertLessEqual(len(G['Samples']), 5)

    # directive: audio-review-queue-grouping | # see audio-normalization.C6
    def test_bulk_clear_rejects_unknown_reason(self):
        with self.assertRaises(ValueError):
            AudioOperatorReviewService().BulkClearByReason('not_a_real_reason')

    # directive: audio-vertical-converge-to-zero | # see directive.md Z1
    def test_grouped_summary_carries_action_label_and_verb(self):
        Groups = AudioOperatorReviewService().GroupedSummary()
        for G in Groups:
            self.assertIn('ActionLabel', G)
            self.assertIn('ActionVerb', G)
            self.assertIn(G['ActionVerb'], ('clear_and_recompute', 'mark_for_remeasurement', 'reenrich_speech_lang'))

    # directive: audio-vertical-converge-to-zero | # see directive.md Z1
    def test_bulk_action_dispatches_per_reason(self):
        from Features.AudioNormalization.Services.AudioOperatorReviewService import (
            REASON_OPERATOR_REVIEW_PENDING,
            REASON_INVALID_LOUDNESS_MEASUREMENT,
            REASON_AWAITING_SPEECH_ENRICHMENT,
        )
        from Features.AudioNormalization.Services.AudioOperatorReviewService import ACTION_FOR_REASON
        self.assertEqual(ACTION_FOR_REASON[REASON_OPERATOR_REVIEW_PENDING][1], 'clear_and_recompute')
        self.assertEqual(ACTION_FOR_REASON[REASON_INVALID_LOUDNESS_MEASUREMENT][1], 'mark_for_remeasurement')
        self.assertEqual(ACTION_FOR_REASON[REASON_AWAITING_SPEECH_ENRICHMENT][1], 'reenrich_speech_lang')


if __name__ == '__main__':
    unittest.main()
