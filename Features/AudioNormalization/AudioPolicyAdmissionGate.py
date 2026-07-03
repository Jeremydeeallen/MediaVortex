import json
from dataclasses import dataclass
from typing import Optional

from Core.Database.DatabaseService import DatabaseService
from Features.AudioNormalization.AudioPolicyResolver import AudioPolicyResolver
from Features.AudioNormalization.AudioStrategyClassifier import (
    AudioStrategyClassifier,
    STRATEGY_REVIEW,
)
from Features.AudioNormalization.LoudnessMeasurementValidator import LoudnessMeasurementValidator
from Features.AudioNormalization.Services.AudioOperatorReviewService import (
    AudioOperatorReviewService,
    REASON_UNGAINABLE_ALL_STREAMS,
)
from Features.AudioNormalization.Services.AudioRemeasurementService import (
    AudioRemeasurementService,
    REASON_INVALID_LOUDNESS,
)


ADMITTED = 'admitted'
DEFERRED_INVALID_MEASUREMENT = 'invalid_loudness_measurement'
DEFERRED_UNGAINABLE = 'ungainable_all_streams'
DEFERRED_POLICY_MISSING = 'audio_policy_missing'
DEFERRED_NO_TRACKS = 'no_emit_tracks_admissible'
DEFERRED_CHANNELS_EXCEED_MAX = 'channels_exceed_max'


SNAPSHOT_POLICY_SQL = (
    "UPDATE TranscodeQueue SET AudioPolicyJson = %s::jsonb "
    "WHERE MediaFileId = %s AND AudioPolicyJson IS NULL"
)


BACKFILL_POST_INSERT_SQL = (
    "UPDATE TranscodeQueue tq SET AudioPolicyJson = ("
    "  SELECT to_jsonb(c.*) FROM AudioNormalizationConfig c "
    "  WHERE (c.Scope = 'item' AND c.ScopeKey = tq.MediaFileId::TEXT) "
    "     OR (c.Scope = 'library' AND c.ScopeKey IN ("
    "         SELECT mf.StorageRootId::TEXT FROM MediaFiles mf WHERE mf.Id = tq.MediaFileId"
    "     )) "
    "     OR (c.Scope = 'global' AND c.ScopeKey IS NULL) "
    "  ORDER BY CASE c.Scope "
    "    WHEN 'item' THEN 1 WHEN 'folder' THEN 2 WHEN 'library' THEN 3 ELSE 4 "
    "  END LIMIT 1"
    ") "
    "WHERE tq.AudioPolicyJson IS NULL "
    "AND tq.DateAdded > NOW() - INTERVAL '60 seconds'"
)


BACKFILL_ALL_PENDING_SQL = (
    "UPDATE TranscodeQueue tq SET AudioPolicyJson = ("
    "  SELECT to_jsonb(c.*) FROM AudioNormalizationConfig c "
    "  WHERE (c.Scope = 'item' AND c.ScopeKey = tq.MediaFileId::TEXT) "
    "     OR (c.Scope = 'library' AND c.ScopeKey IN ("
    "         SELECT mf.StorageRootId::TEXT FROM MediaFiles mf WHERE mf.Id = tq.MediaFileId"
    "     )) "
    "     OR (c.Scope = 'global' AND c.ScopeKey IS NULL) "
    "  ORDER BY CASE c.Scope "
    "    WHEN 'item' THEN 1 WHEN 'folder' THEN 2 WHEN 'library' THEN 3 ELSE 4 "
    "  END LIMIT 1"
    ") "
    "WHERE tq.AudioPolicyJson IS NULL"
)


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C12
@dataclass
class AdmissionDecision:
    """Gate outcome: admitted+policy or deferred+reason."""
    Outcome: str
    DeferReason: Optional[str]
    PolicyJson: Optional[str]


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C12
def _GetField(Obj, Name):
    """Read Name off a dict/object/CaseInsensitiveDict and return the value or None."""
    if hasattr(Obj, Name):
        return getattr(Obj, Name)
    if hasattr(Obj, 'get'):
        Val = Obj.get(Name)
        if Val is not None:
            return Val
        return Obj.get(Name.lower())
    return None


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C12
class AudioPolicyAdmissionGate:
    """Validator + resolver + classifier; defers invalid / ungainable before queue insert; snapshots policy on admitted."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C12
    def __init__(self, Resolver=None, Classifier=None, Validator=None,
                 RemeasurementService=None, ReviewService=None):
        """Constructor injection; defaults wire the production collaborators."""
        self.Resolver = Resolver or AudioPolicyResolver()
        self.Classifier = Classifier or AudioStrategyClassifier()
        self.Validator = Validator or LoudnessMeasurementValidator()
        self.Remeasurement = RemeasurementService or AudioRemeasurementService()
        self.Review = ReviewService or AudioOperatorReviewService()

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C12
    def AdmitOrDefer(self, MediaFile, IntendedProcessingMode=None):
        """Run validator + classifier; return AdmissionDecision; side-effect: write defer reason or operator-review marker."""
        MediaFileId = _GetField(MediaFile, 'Id')

        if not self.Validator.IsValid(MediaFile):
            if MediaFileId is not None:
                self.Remeasurement.MarkForRemeasurement(MediaFileId, REASON_INVALID_LOUDNESS)
            return AdmissionDecision(
                Outcome=DEFERRED_INVALID_MEASUREMENT,
                DeferReason=REASON_INVALID_LOUDNESS,
                PolicyJson=None,
            )

        Policy = self.Resolver.GetEffectivePolicy(MediaFile)
        if Policy is None:
            return AdmissionDecision(
                Outcome=DEFERRED_POLICY_MISSING,
                DeferReason=DEFERRED_POLICY_MISSING,
                PolicyJson=None,
            )

        # directive: transcode-flow-canonical | # see transcode-flow-canonical.C11 -- MaxAudioChannels cap dead under 2-track contract; kept as column for future per-track use.
        Tracks = _GetField(Policy, 'EmitTracks') or []
        if not Tracks:
            return AdmissionDecision(
                Outcome=ADMITTED,
                DeferReason=None,
                PolicyJson=json.dumps(self._PolicyToDict(Policy)),
            )

        AnyAdmissible = False
        for Track in Tracks:
            Strategy = self.Classifier.ClassifyTrack(MediaFile, Track, Policy)
            if Strategy.Strategy != STRATEGY_REVIEW:
                AnyAdmissible = True
                break

        if not AnyAdmissible:
            if MediaFileId is not None:
                self.Review.AddToReviewQueue(MediaFileId, REASON_UNGAINABLE_ALL_STREAMS)
            return AdmissionDecision(
                Outcome=DEFERRED_UNGAINABLE,
                DeferReason=REASON_UNGAINABLE_ALL_STREAMS,
                PolicyJson=None,
            )

        return AdmissionDecision(
            Outcome=ADMITTED,
            DeferReason=None,
            PolicyJson=json.dumps(self._PolicyToDict(Policy)),
        )

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C12
    def SnapshotPolicyOnQueueRow(self, MediaFileId, PolicyJson):
        """Write the policy JSON to TranscodeQueue.AudioPolicyJson for the given MediaFile's pending row."""
        if PolicyJson is None:
            return
        DatabaseService().ExecuteNonQuery(SNAPSHOT_POLICY_SQL, (PolicyJson, MediaFileId))

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C12
    def BackfillRecentInserts(self):
        """Snapshot the resolved policy onto every TranscodeQueue row inserted in the last 60 seconds."""
        DatabaseService().ExecuteNonQuery(BACKFILL_POST_INSERT_SQL)

    # directive: audio-vertical-live-encode-gaps | # see audio-normalization.C12
    def BackfillAllPending(self):
        """Snapshot the resolved policy onto every Pending TranscodeQueue row with NULL AudioPolicyJson, regardless of DateAdded."""
        DatabaseService().ExecuteNonQuery(BACKFILL_ALL_PENDING_SQL)

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C12
    def _PolicyToDict(self, Policy):
        """Coerce a CaseInsensitiveDict / dict / object policy row into a serializable dict."""
        Result = {}
        for Key in (
            'Scope', 'ScopeKey', 'Enabled', 'TargetLra', 'LoudnessTolerance',
            'EmitTracks', 'UngainablePolicy', 'EnableSpeechLanguageDetection',
            'MaxAudioChannels',
        ):
            Val = _GetField(Policy, Key)
            if Val is not None:
                Result[Key] = Val
        return Result
