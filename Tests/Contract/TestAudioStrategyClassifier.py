import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.AudioStrategyClassifier import (
    AudioStrategyClassifier,
    STRATEGY_LINEAR,
    STRATEGY_ADAPTIVE,
    STRATEGY_LIMITER,
    STRATEGY_SKIP,
    STRATEGY_REVIEW,
)


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C5
def _Mf(**Kwargs):
    """Build a MediaFile-shaped dict; defaults populate a gainable source (Source=-30 / TP=-10 / LRA=9)."""
    Defaults = {
        'Id': 1,
        'SourceIntegratedLufs': -30.0,
        'SourceLoudnessRangeLU': 9.0,
        'SourceTruePeakDbtp': -10.0,
        'SourceIntegratedThresholdLufs': -40.0,
    }
    Defaults.update(Kwargs)
    return Defaults


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C5
def _Policy(EmitTracks=None, UngainablePolicy='adaptive', **Kwargs):
    """Build a Policy-shaped dict; defaults match the seeded global row."""
    if EmitTracks is None:
        EmitTracks = [
            {'Label': 'Original', 'TargetLufs': -23.0, 'TargetLra': None},
            {'Label': 'Dialog Boost', 'TargetLufs': -23.0, 'TargetLra': 11.0},
        ]
    Policy = {
        'Enabled': True,
        'TargetIntegratedLufs': -23.0,
        'TargetTruePeakDbtp': -2.0,
        'LoudnessTolerance': 4.0,
        'EmitTracks': EmitTracks,
        'UngainablePolicy': UngainablePolicy,
    }
    Policy.update(Kwargs)
    return Policy


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C5
class TestAudioStrategyClassifier(unittest.TestCase):
    """C5/C6: classifier returns linear/adaptive/limiter/skip/review per UngainablePolicy + measurement state."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C5
    def test_linear_when_gain_fits(self):
        C = AudioStrategyClassifier()
        Track = {'TargetLufs': -23.0, 'TargetLra': None}
        Result = C.ClassifyTrack(_Mf(), Track, _Policy())
        self.assertEqual(Result.Strategy, STRATEGY_LINEAR)
        self.assertEqual(Result.EffectiveTargetLufs, -23.0)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C5
    def test_adaptive_when_gain_too_high_but_within_tolerance(self):
        C = AudioStrategyClassifier()
        Track = {'TargetLufs': -23.0, 'TargetLra': None}
        Mf = _Mf(SourceIntegratedLufs=-28.0, SourceTruePeakDbtp=-3.0)
        Result = C.ClassifyTrack(Mf, Track, _Policy(UngainablePolicy='adaptive'))
        self.assertEqual(Result.Strategy, STRATEGY_ADAPTIVE)
        self.assertLess(Result.EffectiveTargetLufs, -23.0)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C5
    def test_review_when_adaptive_beyond_tolerance(self):
        C = AudioStrategyClassifier()
        Track = {'TargetLufs': -23.0, 'TargetLra': None}
        Mf = _Mf(SourceIntegratedLufs=-50.0, SourceTruePeakDbtp=-3.0)
        Result = C.ClassifyTrack(Mf, Track, _Policy(UngainablePolicy='adaptive', LoudnessTolerance=4.0))
        self.assertEqual(Result.Strategy, STRATEGY_REVIEW)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C6
    def test_skip_when_policy_disabled(self):
        C = AudioStrategyClassifier()
        Track = {'TargetLufs': -23.0, 'TargetLra': None}
        Result = C.ClassifyTrack(_Mf(), Track, _Policy(Enabled=False))
        self.assertEqual(Result.Strategy, STRATEGY_SKIP)
        self.assertEqual(Result.Reason, 'policy_disabled')

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C5
    def test_skip_when_ungainable_policy_is_skip(self):
        C = AudioStrategyClassifier()
        Track = {'TargetLufs': -23.0, 'TargetLra': None}
        Mf = _Mf(SourceIntegratedLufs=-25.0, SourceTruePeakDbtp=-1.0)
        Result = C.ClassifyTrack(Mf, Track, _Policy(UngainablePolicy='skip'))
        self.assertEqual(Result.Strategy, STRATEGY_SKIP)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C5
    def test_limiter_when_ungainable_policy_is_limiter(self):
        C = AudioStrategyClassifier()
        Track = {'TargetLufs': -23.0, 'TargetLra': None}
        Mf = _Mf(SourceIntegratedLufs=-25.0, SourceTruePeakDbtp=-1.0)
        Result = C.ClassifyTrack(Mf, Track, _Policy(UngainablePolicy='limiter'))
        self.assertEqual(Result.Strategy, STRATEGY_LIMITER)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C6
    def test_review_when_ungainable_policy_is_review(self):
        C = AudioStrategyClassifier()
        Track = {'TargetLufs': -23.0, 'TargetLra': None}
        Mf = _Mf(SourceIntegratedLufs=-25.0, SourceTruePeakDbtp=-1.0)
        Result = C.ClassifyTrack(Mf, Track, _Policy(UngainablePolicy='review'))
        self.assertEqual(Result.Strategy, STRATEGY_REVIEW)
        self.assertEqual(Result.Reason, 'ungainable_operator_review')

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C6
    def test_review_when_measurements_missing(self):
        C = AudioStrategyClassifier()
        Track = {'TargetLufs': -23.0, 'TargetLra': None}
        Mf = _Mf(SourceIntegratedLufs=None)
        Result = C.ClassifyTrack(Mf, Track, _Policy())
        self.assertEqual(Result.Strategy, STRATEGY_REVIEW)
        self.assertEqual(Result.Reason, 'invalid_loudness_measurement')

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C5
    def test_review_when_source_at_silence_floor(self):
        C = AudioStrategyClassifier()
        Track = {'TargetLufs': -23.0, 'TargetLra': None}
        Mf = _Mf(SourceIntegratedLufs=-70.0)
        Result = C.ClassifyTrack(Mf, Track, _Policy())
        self.assertEqual(Result.Strategy, STRATEGY_REVIEW)
        self.assertEqual(Result.Reason, 'source_at_silence_floor')

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C5
    def test_classify_all_tracks_returns_one_per_emit_track(self):
        C = AudioStrategyClassifier()
        Results = C.ClassifyAllTracks(_Mf(), _Policy())
        self.assertEqual(len(Results), 2)
        Labels = [Track['Label'] for Track, _ in Results]
        self.assertEqual(Labels, ['Original', 'Dialog Boost'])
        Strategies = [Strat.Strategy for _, Strat in Results]
        self.assertEqual(Strategies, [STRATEGY_LINEAR, STRATEGY_LINEAR])

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C5
    def test_dialog_boost_track_inherits_lra(self):
        C = AudioStrategyClassifier()
        Track = {'TargetLufs': -23.0, 'TargetLra': 11.0}
        Result = C.ClassifyTrack(_Mf(), Track, _Policy())
        self.assertEqual(Result.Strategy, STRATEGY_LINEAR)
        self.assertEqual(Result.EffectiveLra, 11.0)


if __name__ == '__main__':
    unittest.main()
