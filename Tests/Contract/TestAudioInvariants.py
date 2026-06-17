import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.SelfHealing.Invariants.PendingQueueWithoutPolicyJson import PendingQueueWithoutPolicyJson
from Features.AudioNormalization.SelfHealing.Invariants.SuccessfulAttemptWithoutTracksEmitted import SuccessfulAttemptWithoutTracksEmitted
from Features.AudioNormalization.SelfHealing.Invariants.StaleOperatorReview import StaleOperatorReview
from Features.AudioNormalization.SelfHealing.Invariants.InvalidMeasurementWithoutRemeasure import InvalidMeasurementWithoutRemeasure
from Features.AudioNormalization.SelfHealing.Invariants.PreVerticalTranscodedFile import PreVerticalTranscodedFile
from Features.AudioNormalization.SelfHealing.Invariants.ConsistencyBandDeviantWithComplete import ConsistencyBandDeviantWithComplete


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H3
class TestAudioInvariantsLive(unittest.TestCase):
    """H3: live-DB probe -- each invariant's Detect() returns 0 violations in a healthy steady state. Failing tests name the row ids."""

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H3
    def test_no_pending_queue_without_policy_json(self):
        Violations = PendingQueueWithoutPolicyJson().Detect()
        self.assertEqual(
            len(Violations), 0,
            f"TranscodeQueue.Id violations: {Violations[:20]}",
        )

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H3
    def test_no_successful_attempt_without_tracks_emitted(self):
        Violations = SuccessfulAttemptWithoutTracksEmitted().Detect()
        self.assertEqual(
            len(Violations), 0,
            f"TranscodeAttempts.Id (attempt, media_file) violations: {Violations[:20]}",
        )

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H3
    def test_no_stale_operator_review(self):
        Violations = StaleOperatorReview().Detect()
        self.assertEqual(
            len(Violations), 0,
            f"MediaFiles.Id stale review violations (>30d): {Violations[:20]}",
        )

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H3
    def test_no_invalid_measurement_without_remeasure(self):
        Violations = InvalidMeasurementWithoutRemeasure().Detect()
        self.assertEqual(
            len(Violations), 0,
            f"MediaFiles.Id invalid-measurement violations (>24h): {Violations[:20]}",
        )

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H3
    def test_no_pre_vertical_transcoded_file_when_policy_aggressive(self):
        Violations = PreVerticalTranscodedFile().Detect()
        self.assertEqual(
            len(Violations), 0,
            f"MediaFiles.Id pre-vertical violations under current policy: {Violations[:20]}",
        )

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H3
    def test_no_consistency_band_deviant_with_complete(self):
        Violations = ConsistencyBandDeviantWithComplete().Detect()
        self.assertEqual(
            len(Violations), 0,
            f"MediaFiles.Id deviant-with-AudioComplete violations: {Violations[:20]}",
        )


if __name__ == '__main__':
    unittest.main()
