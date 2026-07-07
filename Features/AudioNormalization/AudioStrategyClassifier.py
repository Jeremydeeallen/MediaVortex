from dataclasses import dataclass
from typing import Optional


STRATEGY_LINEAR = 'linear'
STRATEGY_ADAPTIVE = 'adaptive'
STRATEGY_LIMITER = 'limiter'
STRATEGY_SKIP = 'skip'
STRATEGY_REVIEW = 'review'


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C5
@dataclass
class TrackStrategy:
    """Per-track classification: strategy + effective targets + optional reason."""
    Strategy: str
    EffectiveTargetLufs: Optional[float]
    EffectiveTruePeakDbtp: Optional[float]
    EffectiveLra: Optional[float]
    Reason: Optional[str] = None


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C5
def _GetField(Obj, Name):
    """Read Name off a dict/object and return the value or None."""
    if hasattr(Obj, Name):
        return getattr(Obj, Name)
    if hasattr(Obj, 'get'):
        Val = Obj.get(Name)
        if Val is not None:
            return Val
        return Obj.get(Name.lower())
    return None


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C5
class AudioStrategyClassifier:
    """Per-track classifier: linear when gain fits; adaptive/limiter/skip/review when ungainable."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C5
    def ClassifyTrack(self, MediaFile, Track, Policy):
        """Return a TrackStrategy for a single EmitTracks entry given the resolved Policy."""
        if not _GetField(Policy, 'Enabled'):
            return TrackStrategy(
                Strategy=STRATEGY_SKIP,
                EffectiveTargetLufs=None,
                EffectiveTruePeakDbtp=None,
                EffectiveLra=None,
                Reason='policy_disabled',
            )

        SourceI = _GetField(MediaFile, 'SourceIntegratedLufs')
        SourceTp = _GetField(MediaFile, 'SourceTruePeakDbtp')
        SourceLra = _GetField(MediaFile, 'SourceLoudnessRangeLU')
        SourceThresh = _GetField(MediaFile, 'SourceIntegratedThresholdLufs')

        if None in (SourceI, SourceTp, SourceLra, SourceThresh):
            return TrackStrategy(
                Strategy=STRATEGY_REVIEW,
                EffectiveTargetLufs=None,
                EffectiveTruePeakDbtp=None,
                EffectiveLra=None,
                Reason='invalid_loudness_measurement',
            )

        if float(SourceI) <= -60.0:
            return TrackStrategy(
                Strategy=STRATEGY_REVIEW,
                EffectiveTargetLufs=None,
                EffectiveTruePeakDbtp=None,
                EffectiveLra=None,
                Reason='source_at_silence_floor',
            )

        TrackTargetLufs = Track.get('TargetLufs')
        TargetI = float(TrackTargetLufs) if TrackTargetLufs is not None else float(
            _GetField(Policy, 'TargetIntegratedLufs') or -23.0
        )
        TargetTp = float(_GetField(Policy, 'TargetTruePeakDbtp') or -2.0)
        Tolerance = float(_GetField(Policy, 'LoudnessTolerance') or 3.0)
        TrackLra = Track.get('TargetLra')
        EffectiveLra = float(TrackLra) if TrackLra is not None else None

        Gain = TargetI - float(SourceI)
        PredictedPeak = float(SourceTp) + Gain

        if PredictedPeak <= TargetTp:
            return TrackStrategy(
                Strategy=STRATEGY_LINEAR,
                EffectiveTargetLufs=TargetI,
                EffectiveTruePeakDbtp=TargetTp,
                EffectiveLra=EffectiveLra,
            )

        UngainablePolicy = (_GetField(Policy, 'UngainablePolicy') or 'adaptive').lower()

        if UngainablePolicy == 'skip':
            return TrackStrategy(
                Strategy=STRATEGY_SKIP,
                EffectiveTargetLufs=None,
                EffectiveTruePeakDbtp=None,
                EffectiveLra=None,
                Reason='ungainable_skip',
            )

        if UngainablePolicy == 'limiter':
            return TrackStrategy(
                Strategy=STRATEGY_LIMITER,
                EffectiveTargetLufs=TargetI,
                EffectiveTruePeakDbtp=TargetTp,
                EffectiveLra=EffectiveLra,
            )

        if UngainablePolicy == 'review':
            return TrackStrategy(
                Strategy=STRATEGY_REVIEW,
                EffectiveTargetLufs=TargetI,
                EffectiveTruePeakDbtp=TargetTp,
                EffectiveLra=EffectiveLra,
                Reason='ungainable_operator_review',
            )

        ReducedTarget = TargetTp - float(SourceTp) + float(SourceI)
        Delta = abs(ReducedTarget - TargetI)

        if Delta <= Tolerance:
            return TrackStrategy(
                Strategy=STRATEGY_ADAPTIVE,
                EffectiveTargetLufs=ReducedTarget,
                EffectiveTruePeakDbtp=TargetTp,
                EffectiveLra=EffectiveLra,
                Reason='adaptive_lowered_target',
            )

        return TrackStrategy(
            Strategy=STRATEGY_REVIEW,
            EffectiveTargetLufs=TargetI,
            EffectiveTruePeakDbtp=TargetTp,
            EffectiveLra=EffectiveLra,
            Reason='ungainable_beyond_tolerance',
        )

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C5
    def ClassifyAllTracks(self, MediaFile, Policy):
        """Return a list of (TrackConfig, TrackStrategy) for every entry in Policy.EmitTracks."""
        Tracks = _GetField(Policy, 'EmitTracks') or []
        return [(Track, self.ClassifyTrack(MediaFile, Track, Policy)) for Track in Tracks]
