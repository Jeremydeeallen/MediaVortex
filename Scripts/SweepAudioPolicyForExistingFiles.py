import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Core.Database.DatabaseService import DatabaseService
from Features.AudioNormalization.AudioPolicyResolver import AudioPolicyResolver
from Features.AudioNormalization.AudioStrategyClassifier import (
    AudioStrategyClassifier,
    STRATEGY_REVIEW,
)
from Features.AudioNormalization.LoudnessMeasurementValidator import LoudnessMeasurementValidator


SELECT_CANDIDATES_SQL = (
    "SELECT Id, FileName, StorageRootId, RelativePath, "
    "SourceIntegratedLufs, SourceLoudnessRangeLU, SourceTruePeakDbtp, "
    "SourceIntegratedThresholdLufs, AdmissionDeferReason "
    "FROM MediaFiles "
    "WHERE AdmissionDeferReason IS NULL "
    "AND SourceIntegratedLufs IS NOT NULL "
    "ORDER BY Id"
)


MARK_INVALID_SQL = (
    "UPDATE MediaFiles SET AdmissionDeferReason = 'invalid_loudness_measurement' WHERE Id = %s"
)


MARK_UNGAINABLE_SQL = (
    "UPDATE MediaFiles SET AdmissionDeferReason = 'ungainable_all_streams' WHERE Id = %s"
)


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
def AnalyzeRow(Row, Resolver, Classifier, Validator):
    """Return 'invalid' / 'ungainable' / 'admit' for a MediaFile row using vertical services."""
    if not Validator.IsValid(Row):
        return 'invalid'
    Policy = Resolver.GetEffectivePolicy(Row)
    if Policy is None:
        return 'admit'
    Tracks = Policy.get('emittracks') or Policy.get('EmitTracks') or []
    if not Tracks:
        return 'admit'
    AnyAdmissible = False
    for Track in Tracks:
        Strategy = Classifier.ClassifyTrack(Row, Track, Policy)
        if Strategy.Strategy != STRATEGY_REVIEW:
            AnyAdmissible = True
            break
    return 'admit' if AnyAdmissible else 'ungainable'


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C13
def Main():
    """Walk MediaFiles; classify; mark invalid / ungainable; dry-run by default."""
    Parser = argparse.ArgumentParser(description='Audio policy sweep across MediaFiles')
    Parser.add_argument('--apply', action='store_true', help='Apply UPDATEs (default: dry-run)')
    Parser.add_argument('--limit', type=int, default=0, help='Cap row count (0 = no cap)')
    Args = Parser.parse_args()

    Resolver = AudioPolicyResolver()
    Classifier = AudioStrategyClassifier()
    Validator = LoudnessMeasurementValidator()

    Rows = DatabaseService().ExecuteQuery(SELECT_CANDIDATES_SQL)
    if Args.limit:
        Rows = Rows[:Args.limit]
    print(f"Scanning {len(Rows)} MediaFiles (apply={Args.apply})")

    Counts = {'invalid': 0, 'ungainable': 0, 'admit': 0}
    InvalidIds = []
    UngainableIds = []
    for Row in Rows:
        Verdict = AnalyzeRow(Row, Resolver, Classifier, Validator)
        Counts[Verdict] += 1
        if Verdict == 'invalid':
            InvalidIds.append(Row['id'])
        elif Verdict == 'ungainable':
            UngainableIds.append(Row['id'])

    print(f"  invalid_loudness_measurement: {Counts['invalid']}")
    print(f"  ungainable_all_streams: {Counts['ungainable']}")
    print(f"  admit (no defer): {Counts['admit']}")

    if not Args.apply:
        print("Dry-run -- pass --apply to UPDATE MediaFiles.")
        return 0

    Db = DatabaseService()
    for MfId in InvalidIds:
        Db.ExecuteNonQuery(MARK_INVALID_SQL, (MfId,))
    for MfId in UngainableIds:
        Db.ExecuteNonQuery(MARK_UNGAINABLE_SQL, (MfId,))
    print(f"Applied {len(InvalidIds)} invalid + {len(UngainableIds)} ungainable defer reasons.")
    return 0


if __name__ == '__main__':
    raise SystemExit(Main())
