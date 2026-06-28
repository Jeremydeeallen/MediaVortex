import os
import unittest
from Core.Database.DatabaseService import DatabaseService
from Features.WorkBucket.Domain.BucketKey import BucketKey
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity
from Features.WorkBucket.Services.QueueAdmissionAppService import QueueAdmissionAppService


# directive: work-transcode-unified | # see work-bucket.C4
class TestQueueAdmissionAppService(unittest.TestCase):

    @classmethod
    # directive: work-transcode-unified | # see work-bucket.C4
    def setUpClass(cls):
        os.environ.setdefault('MEDIAVORTEX_DB_HOST', '10.0.0.15')

    # directive: work-transcode-unified | # see work-bucket.C4
    def test_admit_series_returns_admission_result(self):
        # see work-bucket.C4
        Sample = DatabaseService().ExecuteQuery(
            "SELECT mf.StorageRootId, split_part(mf.RelativePath, '/', 1) AS RelativePath "
            "FROM MediaFiles mf WHERE mf.WorkBucket = 'Transcode' "
            "GROUP BY mf.StorageRootId, split_part(mf.RelativePath, '/', 1) "
            "HAVING COUNT(*) >= 1 LIMIT 1"
        )
        if not Sample:
            self.skipTest("No Transcode series in DB")
        Identity = SeriesIdentity(StorageRootId=int(Sample[0]['storagerootid']), RelativePath=Sample[0]['relativepath'])
        DatabaseService().ExecuteNonQuery(
            "DELETE FROM TranscodeQueue WHERE Status='Pending' AND MediaFileId IN ("
            "  SELECT Id FROM MediaFiles WHERE WorkBucket='Transcode' AND StorageRootId=%s AND split_part(RelativePath,'/',1)=%s"
            ")",
            (Identity.StorageRootId, Identity.RelativePath),
        )
        Result = QueueAdmissionAppService().AdmitSeries(Identity, BucketKey.FromUrlKey('Transcode'))
        self.assertEqual(Result.Inserted + Result.AlreadyQueued, Result.Total)
        DatabaseService().ExecuteNonQuery(
            "DELETE FROM TranscodeQueue WHERE Status='Pending' AND MediaFileId IN ("
            "  SELECT Id FROM MediaFiles WHERE WorkBucket='Transcode' AND StorageRootId=%s AND split_part(RelativePath,'/',1)=%s"
            ")",
            (Identity.StorageRootId, Identity.RelativePath),
        )


if __name__ == '__main__':
    unittest.main()
