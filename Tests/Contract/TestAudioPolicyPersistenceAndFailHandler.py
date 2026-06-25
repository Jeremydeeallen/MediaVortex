import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from Core.Database.DatabaseService import DatabaseService
from Features.AudioNormalization.AudioStrategyResult import AudioPolicyUnresolvedError
from Features.AudioNormalization.AudioPipelineFailHandler import AudioPipelineFailHandler
from Features.AudioNormalization.TranscodeAudioPolicyVerdictRepository import (
    TranscodeAudioPolicyVerdictRepository,
)


# directive: audio-pipeline-fail-loud
class TestTranscodeAudioPolicyVerdictRepository(unittest.TestCase):

    def setUp(self):
        self.Db = DatabaseService()
        self.Repo = TranscodeAudioPolicyVerdictRepository(self.Db)
        self.Db.ExecuteNonQuery(
            "INSERT INTO TranscodeAttempts (AttemptDate, Success, ErrorMessage, WorkerName, ProfileName) "
            "VALUES (NOW(), NULL, 'phase-c-verdict-test', 'wakko-worker-1', 'TEST_PHASE_C')",
        )
        Row = self.Db.ExecuteQuery(
            "SELECT Id FROM TranscodeAttempts WHERE ErrorMessage='phase-c-verdict-test' ORDER BY Id DESC LIMIT 1",
        )
        self.AttemptId = int(Row[0]['id'])

    def tearDown(self):
        self.Db.ExecuteNonQuery(
            "DELETE FROM TranscodeAudioPolicyVerdicts WHERE TranscodeAttemptId = %s",
            (self.AttemptId,),
        )
        self.Db.ExecuteNonQuery("DELETE FROM TranscodeAttempts WHERE Id = %s", (self.AttemptId,))

    def test_persist_round_trip(self):
        Verdicts = [
            {'TrackIndex': 0, 'PolicyName': 'EAC3OrPassthroughCodecPolicy', 'PolicyReason': 'accept', 'PlanText': "{'Codec':'eac3'}"},
            {'TrackIndex': 0, 'PolicyName': 'ProfileCeilingBitratePolicy', 'PolicyReason': 'accept', 'PlanText': '192'},
        ]
        Count = self.Repo.PersistVerdicts(self.AttemptId, Verdicts)
        self.assertEqual(Count, 2)
        Out = self.Repo.GetVerdictsForAttempt(self.AttemptId)
        self.assertEqual(len(Out), 2)
        Names = sorted(R.get('PolicyName') or R.get('policyname') for R in Out)
        self.assertEqual(Names, ['EAC3OrPassthroughCodecPolicy', 'ProfileCeilingBitratePolicy'])

    def test_mark_attempt_resolved(self):
        self.Repo.MarkAttemptResolved(self.AttemptId, 'resolved')
        Row = self.Db.ExecuteQuery(
            "SELECT AudioPolicyResolved FROM TranscodeAttempts WHERE Id = %s",
            (self.AttemptId,),
        )[0]
        self.assertEqual(Row.get('AudioPolicyResolved') or Row.get('audiopolicyresolved'), 'resolved')


# directive: audio-pipeline-fail-loud
class _CapturingStateReporter:

    def __init__(self):
        self.Calls = []

    def Transition(self, State, AttemptId=None):
        self.Calls.append((State, AttemptId))


# directive: audio-pipeline-fail-loud
class TestAudioPipelineFailHandler(unittest.TestCase):

    def setUp(self):
        self.Db = DatabaseService()
        self.Reporter = _CapturingStateReporter()
        self.Handler = AudioPipelineFailHandler(WorkerName='wakko-worker-1', Db=self.Db, StateReporter=self.Reporter)
        self.Db.ExecuteNonQuery(
            "INSERT INTO TranscodeAttempts (AttemptDate, Success, ErrorMessage, WorkerName, ProfileName) "
            "VALUES (NOW(), NULL, 'phase-c-failhandler-test', 'wakko-worker-1', 'TEST_PHASE_C')",
        )
        Row = self.Db.ExecuteQuery(
            "SELECT Id FROM TranscodeAttempts WHERE ErrorMessage='phase-c-failhandler-test' ORDER BY Id DESC LIMIT 1",
        )
        self.AttemptId = int(Row[0]['id'])

    def tearDown(self):
        self.Db.ExecuteNonQuery("DELETE FROM TranscodeAttempts WHERE Id = %s", (self.AttemptId,))
        self.Db.ExecuteNonQuery(
            "UPDATE Workers SET RuntimeState = NULL, LastRuntimeStateUpdate = NULL WHERE WorkerName = 'wakko-worker-1'",
        )

    def test_handle_unresolved_writes_failure_and_transitions_faulted(self):
        Error = AudioPolicyUnresolvedError('ProfileCeilingBitratePolicy', 'no_ceiling_and_no_config_bitrate', TrackIndex=1)
        Out = self.Handler.HandleUnresolved(self.AttemptId, Error)

        Row = self.Db.ExecuteQuery(
            "SELECT Success, ErrorMessage, AudioPolicyResolved FROM TranscodeAttempts WHERE Id = %s",
            (self.AttemptId,),
        )[0]
        self.assertEqual(Row.get('Success') or Row.get('success'), False)
        Msg = Row.get('ErrorMessage') or Row.get('errormessage')
        self.assertIn('AudioPolicyUnresolvedError', Msg)
        self.assertIn('ProfileCeilingBitratePolicy', Msg)
        self.assertEqual(Row.get('AudioPolicyResolved') or Row.get('audiopolicyresolved'), 'unresolved')

        self.assertEqual(len(self.Reporter.Calls), 1)
        State, _AttemptArg = self.Reporter.Calls[0]
        self.assertTrue(State.startswith('Faulted:'))
        self.assertIn('ProfileCeilingBitratePolicy', State)

        self.assertEqual(Out['PolicyName'], 'ProfileCeilingBitratePolicy')
        self.assertEqual(Out['TrackIndex'], 1)


if __name__ == '__main__':
    unittest.main()
