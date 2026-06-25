import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from Core.Database.DatabaseService import DatabaseService
from Core.Querying import PagedQuery
from Features.FailureAccounting.Repositories.FailedJobsRepository import FailedJobsRepository


# directive: audio-pipeline-fail-loud
class TestAudioOperatorVisibleFailure(unittest.TestCase):

    def setUp(self):
        self.Db = DatabaseService()
        self.Repo = FailedJobsRepository()
        self.TouchedAttemptId = None
        self.InsertedVerdictId = None
        self.PreviousAudioPolicyResolved = None

    def tearDown(self):
        if self.InsertedVerdictId is not None:
            self.Db.ExecuteNonQuery(
                "DELETE FROM TranscodeAudioPolicyVerdicts WHERE Id = %s",
                (self.InsertedVerdictId,),
            )
        if self.TouchedAttemptId is not None:
            self.Db.ExecuteNonQuery(
                "UPDATE TranscodeAttempts SET AudioPolicyResolved = %s WHERE Id = %s",
                (self.PreviousAudioPolicyResolved, self.TouchedAttemptId),
            )

    def test_failed_jobs_response_includes_audio_policy_columns(self):
        Q = PagedQuery(Page=1, PageSize=3)
        Result = self.Repo.GetFailedJobsPaged(Q)
        if not Result.Rows:
            self.skipTest("No capped failed jobs in DB to validate column presence against.")
        Row = Result.Rows[0]
        for Key in ('AudioPolicyResolved', 'LatestAudioPolicyReason', 'LatestAudioPolicyName'):
            self.assertTrue(Key in Row or Key.lower() in Row, f"Expected {Key} in FailedJobs response keys; got {sorted(Row.keys())}")

    def test_failed_jobs_response_surfaces_synthetic_audio_policy_verdict(self):
        Q = PagedQuery(Page=1, PageSize=1)
        Result = self.Repo.GetFailedJobsPaged(Q)
        if not Result.Rows:
            self.skipTest("No capped failed jobs to augment with synthetic audio policy state.")
        Target = Result.Rows[0]
        MediaFileId = int(Target.get('MediaFileId') or Target.get('mediafileid'))

        AttemptRows = self.Db.ExecuteQuery(
            "SELECT Id, AudioPolicyResolved FROM TranscodeAttempts "
            "WHERE MediaFileId = %s AND Success = FALSE ORDER BY AttemptDate DESC LIMIT 1",
            (MediaFileId,),
        )
        if not AttemptRows:
            self.skipTest(f"No failed attempt found for MediaFileId={MediaFileId}.")
        self.TouchedAttemptId = int(AttemptRows[0].get('Id') or AttemptRows[0].get('id'))
        self.PreviousAudioPolicyResolved = AttemptRows[0].get('AudioPolicyResolved') or AttemptRows[0].get('audiopolicyresolved')

        self.Db.ExecuteNonQuery(
            "UPDATE TranscodeAttempts SET AudioPolicyResolved = %s WHERE Id = %s",
            ('unresolved', self.TouchedAttemptId),
        )
        self.Db.ExecuteNonQuery(
            "INSERT INTO TranscodeAudioPolicyVerdicts "
            "(TranscodeAttemptId, TrackIndex, PolicyName, PolicyReason, PlanText) "
            "VALUES (%s, %s, %s, %s, %s)",
            (self.TouchedAttemptId, 0, 'ProfileCeilingBitratePolicy', 'no_ceiling_and_no_config_bitrate', None),
        )
        VerdictRow = self.Db.ExecuteQuery(
            "SELECT Id FROM TranscodeAudioPolicyVerdicts "
            "WHERE TranscodeAttemptId = %s ORDER BY Id DESC LIMIT 1",
            (self.TouchedAttemptId,),
        )
        self.InsertedVerdictId = int(VerdictRow[0].get('Id') or VerdictRow[0].get('id'))

        Refreshed = self.Repo.GetFailedJobsPaged(PagedQuery(Page=1, PageSize=200))
        Match = [R for R in Refreshed.Rows if (int(R.get('MediaFileId') or R.get('mediafileid')) == MediaFileId)]
        self.assertEqual(len(Match), 1, "Expected the augmented row to surface")
        Row = Match[0]
        self.assertEqual(Row.get('AudioPolicyResolved') or Row.get('audiopolicyresolved'), 'unresolved')
        self.assertEqual(Row.get('LatestAudioPolicyReason') or Row.get('latestaudiopolicyreason'), 'no_ceiling_and_no_config_bitrate')
        self.assertEqual(Row.get('LatestAudioPolicyName') or Row.get('latestaudiopolicyname'), 'ProfileCeilingBitratePolicy')


if __name__ == '__main__':
    unittest.main()
