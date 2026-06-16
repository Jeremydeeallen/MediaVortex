import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.DialNormHandler import (
    DialNormHandler,
    DOLBY_DIALNORM_MIN,
    DOLBY_DIALNORM_MAX,
)
from Features.AudioNormalization.AudioStrategyClassifier import (
    TrackStrategy,
    STRATEGY_LINEAR,
)


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C20
class TestDialNormHandler(unittest.TestCase):
    """C20: source pass-through on Original stream-copy; freshly computed on re-encode; clamped to spec."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C20
    def test_compute_for_target_minus_23_lufs_returns_23(self):
        H = DialNormHandler()
        self.assertEqual(H.ComputeForLoudness(-23.0), 23)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C20
    def test_compute_clamps_at_dolby_max(self):
        H = DialNormHandler()
        self.assertEqual(H.ComputeForLoudness(-40.0), DOLBY_DIALNORM_MAX)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C20
    def test_compute_clamps_at_dolby_min(self):
        H = DialNormHandler()
        self.assertEqual(H.ComputeForLoudness(0.0), DOLBY_DIALNORM_MIN)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C20
    def test_extract_source_dialnorm_from_tags(self):
        H = DialNormHandler()
        Stream = {'tags': {'DialNorm': '24'}}
        self.assertEqual(H.GetSourceDialNorm(Stream), 24)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C20
    def test_extract_source_dialnorm_from_side_data(self):
        H = DialNormHandler()
        Stream = {'side_data_list': [{'dialnorm': 21}]}
        self.assertEqual(H.GetSourceDialNorm(Stream), 21)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C20
    def test_extract_returns_none_when_absent(self):
        H = DialNormHandler()
        self.assertIsNone(H.GetSourceDialNorm({'tags': {}}))

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C20
    def test_resolve_preserves_source_on_original_stream_copy(self):
        H = DialNormHandler()
        S = TrackStrategy(
            Strategy=STRATEGY_LINEAR,
            EffectiveTargetLufs=-23.0,
            EffectiveTruePeakDbtp=-2.0,
            EffectiveLra=None,
        )
        self.assertEqual(H.ResolveForTrack(S, SourceDialNorm=24, IsOriginalStreamCopy=True), 24)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C20
    def test_resolve_recomputes_on_re_encode(self):
        H = DialNormHandler()
        S = TrackStrategy(
            Strategy=STRATEGY_LINEAR,
            EffectiveTargetLufs=-23.0,
            EffectiveTruePeakDbtp=-2.0,
            EffectiveLra=None,
        )
        self.assertEqual(H.ResolveForTrack(S, SourceDialNorm=24, IsOriginalStreamCopy=False), 23)


if __name__ == '__main__':
    unittest.main()
