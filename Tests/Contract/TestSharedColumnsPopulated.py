import json
import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from Core.Database.DatabaseService import DatabaseService
from Features.AudioNormalization.Services.PostEncodeMeasurementService import PostEncodeMeasurementService


# directive: transcode-flow-canonical | # see transcode.ST5 | # see audio-normalization.C5
class TestSharedColumnsPopulated(unittest.TestCase):
    """C5: every strategy populates AudioPolicyResolved + AudioPolicyJson + AudioTracksEmittedJson for every attempt."""

    CUTOVER = datetime(2026, 7, 3, 21, 0, 0, tzinfo=timezone.utc)

    def setUp(self):
        self.Db = DatabaseService()
        self.TouchedAttemptId = None
        self.PrevTracks = None
        self.PrevResolved = None
        self.PrevPolicyJson = None

    def tearDown(self):
        if self.TouchedAttemptId is not None:
            self.Db.ExecuteNonQuery(
                "UPDATE TranscodeAttempts "
                "SET AudioTracksEmittedJson = %s::jsonb, AudioPolicyResolved = %s, AudioPolicyJson = %s::jsonb "
                "WHERE Id = %s",
                (
                    self.PrevTracks if self.PrevTracks is not None else None,
                    self.PrevResolved,
                    self.PrevPolicyJson if self.PrevPolicyJson is not None else None,
                    self.TouchedAttemptId,
                ),
            )

    # directive: transcode-flow-canonical | # see transcode.ST5
    def test_persist_attestation_writes_all_three_columns(self):
        AttemptRows = self.Db.ExecuteQuery(
            "SELECT Id AS attemptid, AudioTracksEmittedJson AS tracks, "
            "       AudioPolicyResolved AS resolved, AudioPolicyJson AS policyjson "
            "FROM TranscodeAttempts ORDER BY Id DESC LIMIT 1"
        )
        if not AttemptRows:
            self.skipTest("No TranscodeAttempts row available to seed round-trip.")
        QueueRows = self.Db.ExecuteQuery(
            "SELECT Id AS queueid, AudioPolicyJson AS qpolicy "
            "FROM TranscodeQueue WHERE AudioPolicyJson IS NOT NULL "
            "ORDER BY Id DESC LIMIT 1"
        )
        QueueId = None
        ExpectedPolicy = None
        if QueueRows:
            QueueId = int(QueueRows[0].get('queueid') or QueueRows[0].get('QueueId'))
            ExpectedPolicy = QueueRows[0].get('qpolicy') or QueueRows[0].get('QPolicy')

        AttemptId = int(AttemptRows[0].get('attemptid') or AttemptRows[0].get('AttemptId'))
        self.TouchedAttemptId = AttemptId
        self.PrevTracks = self._Serialize(AttemptRows[0].get('tracks'))
        self.PrevResolved = AttemptRows[0].get('resolved')
        self.PrevPolicyJson = self._Serialize(AttemptRows[0].get('policyjson'))

        self.Db.ExecuteNonQuery(
            "UPDATE TranscodeAttempts "
            "SET AudioTracksEmittedJson = NULL, AudioPolicyResolved = NULL, AudioPolicyJson = NULL "
            "WHERE Id = %s",
            (AttemptId,),
        )

        Svc = PostEncodeMeasurementService()
        Results = [{'TrackIndex': 0, 'Label': 'Test', 'Language': 'eng', 'Strategy': 'measured'}]
        Ok = Svc._PersistAttestation(AttemptId, QueueId, Results, 'resolved')
        self.assertTrue(Ok, "PersistAttestation must succeed against a real attempt row.")

        After = self.Db.ExecuteQuery(
            "SELECT AudioTracksEmittedJson AS tracks, AudioPolicyResolved AS resolved, AudioPolicyJson AS policyjson "
            "FROM TranscodeAttempts WHERE Id = %s",
            (AttemptId,),
        )
        self.assertEqual(len(After), 1)
        A = After[0]
        self.assertIsNotNone(A.get('tracks') or A.get('Tracks'), "AudioTracksEmittedJson must be non-null.")
        self.assertEqual(A.get('resolved') or A.get('Resolved'), 'resolved')
        if QueueId is not None and ExpectedPolicy is not None:
            self.assertIsNotNone(A.get('policyjson') or A.get('PolicyJson'), "AudioPolicyJson must snapshot from queue.")

    # directive: transcode-flow-canonical | # see transcode.ST5
    def test_audit_post_cutover_attempts_have_all_three_populated(self):
        Rows = self.Db.ExecuteQuery(
            "SELECT COUNT(*) AS n, "
            "       COUNT(AudioPolicyResolved) AS apr, "
            "       COUNT(AudioPolicyJson) AS apj, "
            "       COUNT(AudioTracksEmittedJson) AS atej "
            "FROM TranscodeAttempts "
            "WHERE AttemptDate >= %s AND Success = TRUE",
            (self.CUTOVER,),
        )
        R = Rows[0]
        N = int(R.get('n') or R.get('N') or 0)
        if N == 0:
            self.skipTest("No post-cutover successful attempts yet -- run after Reset 8 smoke lands data.")
        Apr = int(R.get('apr') or R.get('Apr') or 0)
        Apj = int(R.get('apj') or R.get('Apj') or 0)
        Atej = int(R.get('atej') or R.get('Atej') or 0)
        self.assertEqual(Apr, N, f"AudioPolicyResolved must be 100% populated post-cutover; got {Apr}/{N}.")
        self.assertEqual(Apj, N, f"AudioPolicyJson must be 100% populated post-cutover; got {Apj}/{N}.")
        self.assertEqual(Atej, N, f"AudioTracksEmittedJson must be 100% populated post-cutover; got {Atej}/{N}.")

    def _Serialize(self, Value):
        if Value is None:
            return None
        if isinstance(Value, (dict, list)):
            return json.dumps(Value)
        return Value


if __name__ == '__main__':
    unittest.main()
