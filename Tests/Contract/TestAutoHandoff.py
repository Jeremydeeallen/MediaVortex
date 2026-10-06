import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

from Features.FileReplacement.TranscodedOutputPlacement import TranscodedOutputPlacement
from Features.ServiceControl.ActiveJobRepository import ActiveJobRepository
from Features.ServiceControl.StuckJobDetectionService import StuckJobDetectionService
from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService

QMBS_PATH = 'Features.TranscodeQueue.QueueManagementBusinessService.QueueManagementBusinessService'


# directive: auto-handoff | # see transcode.ST9
class _FakeDb:
    # directive: auto-handoff | # see transcode.ST9
    def __init__(self, Rows=None, Raises=None):
        self.Rows = Rows
        self.Raises = Raises

    # directive: auto-handoff | # see transcode.ST9
    def ExecuteQuery(self, Query, Params=None):
        if self.Raises:
            raise self.Raises
        return self.Rows


# directive: auto-handoff | # see transcode.ST9
class TestPlacementQueuesNextStage(unittest.TestCase):

    # directive: auto-handoff | # see transcode.ST9
    def _Placement(self, Bucket):
        Rows = [] if Bucket is None else [{'WorkBucket': Bucket}]
        Manager = SimpleNamespace(DatabaseService=_FakeDb(Rows))
        return TranscodedOutputPlacement(DatabaseManagerInstance=Manager, FileManagerInstance=object(),
                                         WorkerName='t', PostFlightRegistryInstance=object())

    # directive: auto-handoff | # see transcode.ST9
    def test_TranscodeThenAudioBucketQueuesAudioFix(self):
        with mock.patch(QMBS_PATH) as Svc:
            Svc.return_value.AddJobToQueue.return_value = {'Success': True, 'ItemId': 1}
            self._Placement('AudioFix')._QueueNextStage(5, 'Transcode')
            Svc.return_value.AddJobToQueue.assert_called_once_with(MediaFileId=5, ProcessingMode='AudioFix')

    # directive: auto-handoff | # see transcode.ST9
    def test_SameLabelIsNeverQueuedAgain(self):
        with mock.patch(QMBS_PATH) as Svc:
            self._Placement('AudioFix')._QueueNextStage(5, 'AudioFix')
            Svc.return_value.AddJobToQueue.assert_not_called()

    # directive: auto-handoff | # see transcode.ST9
    def test_NoWorkBucketQueuesNothing(self):
        for Bucket in ('Compliant', 'Unclassified'):
            with mock.patch(QMBS_PATH) as Svc:
                self._Placement(Bucket)._QueueNextStage(5, 'AudioFix')
                Svc.return_value.AddJobToQueue.assert_not_called()

    # directive: auto-handoff | # see transcode.ST9
    def test_MissingRowRaises(self):
        with mock.patch(QMBS_PATH):
            with self.assertRaises(RuntimeError):
                self._Placement(None)._QueueNextStage(5, 'Transcode')


# directive: auto-handoff | # see transcode.ST2
class TestAddJobRefusesNoWorkBucket(unittest.TestCase):

    # directive: auto-handoff | # see transcode.ST2
    def test_CompliantFileWithoutLabelIsRefused(self):
        Svc = QueueManagementBusinessService.__new__(QueueManagementBusinessService)
        Svc.DatabaseManager = SimpleNamespace(DatabaseService=_FakeDb([{'workbucket': 'Compliant'}]))
        Result = Svc.AddJobToQueue(5)
        self.assertFalse(Result['Success'])
        self.assertIn('Compliant', Result['ErrorMessage'])

    # directive: auto-handoff | # see transcode.ST2
    def test_UnknownLabelIsRefused(self):
        Svc = QueueManagementBusinessService.__new__(QueueManagementBusinessService)
        Svc.DatabaseManager = SimpleNamespace(DatabaseService=_FakeDb([]))
        Result = Svc.AddJobToQueue(5, ProcessingMode='Quick')
        self.assertFalse(Result['Success'])
        self.assertIn('Quick', Result['ErrorMessage'])


# directive: auto-handoff | # see stuck-job-detection.ST2
class TestStuckGraceAfterClaim(unittest.TestCase):

    # directive: auto-handoff | # see stuck-job-detection.ST2
    def _Service(self):
        Svc = StuckJobDetectionService.__new__(StuckJobDetectionService)
        Svc.ActiveJobRepository = SimpleNamespace(GetActiveJobsByService=lambda Query: [])
        Svc._ReadSetupPhaseTimeoutMin = lambda: 30
        return Svc

    # directive: auto-handoff | # see stuck-job-detection.ST2
    def _Job(self, MinutesAgo):
        return SimpleNamespace(Id=1, DateStarted=datetime.now(timezone.utc) - timedelta(minutes=MinutesAgo))

    # directive: auto-handoff | # see stuck-job-detection.ST2
    def test_JustClaimedWithoutActiveJobIsNotStuck(self):
        Stuck, _ = self._Service().IsJobStuck(self._Job(1))
        self.assertFalse(Stuck)

    # directive: auto-handoff | # see stuck-job-detection.ST2
    def test_PastTimeoutWithoutActiveJobIsStuck(self):
        Stuck, _ = self._Service().IsJobStuck(self._Job(31))
        self.assertTrue(Stuck)


# directive: auto-handoff | # see stuck-job-detection.ST2
class TestActiveJobsReadFailureRaises(unittest.TestCase):

    # directive: auto-handoff | # see stuck-job-detection.ST2
    def test_QueryFailureRaises(self):
        Repo = ActiveJobRepository.__new__(ActiveJobRepository)
        Repo.DatabaseService = _FakeDb(Raises=RuntimeError('db down'))
        with self.assertRaises(RuntimeError):
            Repo.GetActiveJobsByService(ActiveJobRepository.BuildActiveJobsQuery('TranscodeService'))


if __name__ == '__main__':
    unittest.main()
