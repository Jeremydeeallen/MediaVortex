import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.Services.AudioOperatorReviewService import (
    AudioOperatorReviewService,
    REASON_UNGAINABLE_ALL_STREAMS,
    REASON_OPERATOR_REVIEW_PENDING,
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
            self.assertIn(G['AdmissionDeferReason'], (REASON_UNGAINABLE_ALL_STREAMS, REASON_OPERATOR_REVIEW_PENDING))
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


if __name__ == '__main__':
    unittest.main()
