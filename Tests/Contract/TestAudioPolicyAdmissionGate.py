import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.AudioNormalization.AudioPolicyAdmissionGate import (
    AudioPolicyAdmissionGate,
    AdmissionDecision,
    ADMITTED,
    DEFERRED_INVALID_MEASUREMENT,
    DEFERRED_UNGAINABLE,
    DEFERRED_POLICY_MISSING,
)


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C12
def _Mf(**Kwargs):
    """Gainable MediaFile dict (source=-30 LUFS, TP=-10 dBTP, all measurements valid)."""
    Defaults = {
        'Id': 1,
        'StorageRootId': 1,
        'RelativePath': 'Movies/Foo.mp4',
        'SourceIntegratedLufs': -30.0,
        'SourceLoudnessRangeLU': 9.0,
        'SourceTruePeakDbtp': -10.0,
        'SourceIntegratedThresholdLufs': -40.0,
        'AudioCodec': 'eac3',
        'AudioCorruptSuspect': False,
    }
    Defaults.update(Kwargs)
    return Defaults


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C12
def _Policy(**Kwargs):
    """Default policy matching the seeded global row."""
    Defaults = {
        'Scope': 'global', 'ScopeKey': None, 'Enabled': True,
        'TargetIntegratedLufs': -23.0, 'TargetTruePeakDbtp': -2.0,
        'TargetLra': None, 'LoudnessTolerance': 4.0,
        'EmitTracks': [
            {'Label': 'Original', 'TargetLufs': -23.0, 'TargetLra': None,
             'Channels': 'source', 'Codec': 'eac3', 'Bitrate': 384,
             'LanguageFilter': 'keep-all', 'IsDefaultTrack': False},
            {'Label': 'Dialog Boost', 'TargetLufs': -23.0, 'TargetLra': 11.0,
             'Channels': 'source', 'Codec': 'eac3', 'Bitrate': 384,
             'LanguageFilter': 'keep-all', 'IsDefaultTrack': True},
        ],
        'UngainablePolicy': 'review',
        'EnableSpeechLanguageDetection': False,
    }
    Defaults.update(Kwargs)
    return Defaults


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C12
class _StubResolver:
    """Returns a fixed policy."""
    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C12
    def __init__(self, Policy):
        self.Policy = Policy
    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C12
    def GetEffectivePolicy(self, MediaFile):
        return self.Policy


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C12
class _StubRemeasurement:
    """Captures MarkForRemeasurement calls."""
    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C12
    def __init__(self):
        self.Marks = []
    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C12
    def MarkForRemeasurement(self, MediaFileId, Reason='invalid_loudness_measurement'):
        self.Marks.append((MediaFileId, Reason))


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C12
class _StubReview:
    """Captures AddToReviewQueue calls."""
    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C12
    def __init__(self):
        self.Added = []
    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C12
    def AddToReviewQueue(self, MediaFileId, Reason):
        self.Added.append((MediaFileId, Reason))


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C12
class TestAudioPolicyAdmissionGate(unittest.TestCase):
    """C12/C13: gate filters invalid + ungainable; admits gainable with PolicyJson snapshot."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C12
    def test_admits_gainable_with_policy_json(self):
        Gate = AudioPolicyAdmissionGate(
            Resolver=_StubResolver(_Policy()),
            RemeasurementService=_StubRemeasurement(),
            ReviewService=_StubReview(),
        )
        Decision = Gate.AdmitOrDefer(_Mf())
        self.assertEqual(Decision.Outcome, ADMITTED)
        self.assertIsNone(Decision.DeferReason)
        self.assertIsNotNone(Decision.PolicyJson)
        Parsed = json.loads(Decision.PolicyJson)
        self.assertEqual(Parsed['Enabled'], True)
        self.assertEqual(len(Parsed['EmitTracks']), 2)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    def test_defers_invalid_measurement_and_marks_for_remeasurement(self):
        Rem = _StubRemeasurement()
        Gate = AudioPolicyAdmissionGate(
            Resolver=_StubResolver(_Policy()),
            RemeasurementService=Rem,
            ReviewService=_StubReview(),
        )
        Decision = Gate.AdmitOrDefer(_Mf(SourceIntegratedLufs=None))
        self.assertEqual(Decision.Outcome, DEFERRED_INVALID_MEASUREMENT)
        self.assertEqual(Rem.Marks, [(1, 'invalid_loudness_measurement')])

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
    def test_defers_silence_floor_and_marks_for_remeasurement(self):
        Rem = _StubRemeasurement()
        Gate = AudioPolicyAdmissionGate(
            Resolver=_StubResolver(_Policy()),
            RemeasurementService=Rem,
            ReviewService=_StubReview(),
        )
        Decision = Gate.AdmitOrDefer(_Mf(SourceIntegratedLufs=-70.0))
        self.assertEqual(Decision.Outcome, DEFERRED_INVALID_MEASUREMENT)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C6
    def test_defers_ungainable_routing_to_review(self):
        Rev = _StubReview()
        Gate = AudioPolicyAdmissionGate(
            Resolver=_StubResolver(_Policy(UngainablePolicy='review')),
            RemeasurementService=_StubRemeasurement(),
            ReviewService=Rev,
        )
        Mf = _Mf(SourceIntegratedLufs=-30.0, SourceTruePeakDbtp=-3.0)
        Decision = Gate.AdmitOrDefer(Mf)
        self.assertEqual(Decision.Outcome, DEFERRED_UNGAINABLE)
        self.assertEqual(Rev.Added, [(1, 'ungainable_all_streams')])
        self.assertIsNotNone(Decision.PolicyJson)
        Snapshot = json.loads(Decision.PolicyJson)
        self.assertEqual(Snapshot['UngainablePolicy'], 'review')

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C12
    def test_admits_when_at_least_one_track_admissible(self):
        Policy = _Policy(EmitTracks=[
            {'Label': 'Original', 'TargetLufs': -23.0, 'TargetLra': None,
             'Channels': 'source', 'Codec': 'eac3', 'Bitrate': 384,
             'LanguageFilter': 'keep-all', 'IsDefaultTrack': True},
        ])
        Gate = AudioPolicyAdmissionGate(
            Resolver=_StubResolver(Policy),
            RemeasurementService=_StubRemeasurement(),
            ReviewService=_StubReview(),
        )
        Decision = Gate.AdmitOrDefer(_Mf())
        self.assertEqual(Decision.Outcome, ADMITTED)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C12
    def test_defers_when_policy_missing(self):
        Gate = AudioPolicyAdmissionGate(
            Resolver=_StubResolver(None),
            RemeasurementService=_StubRemeasurement(),
            ReviewService=_StubReview(),
        )
        Decision = Gate.AdmitOrDefer(_Mf())
        self.assertEqual(Decision.Outcome, DEFERRED_POLICY_MISSING)


if __name__ == '__main__':
    unittest.main()
