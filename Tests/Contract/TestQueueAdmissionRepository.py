import os
import unittest
from Core.Database.DatabaseService import DatabaseService
from Features.WorkBucket.Domain.BucketKey import BucketKey
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity
from Features.WorkBucket.Repositories.QueueAdmissionRepository import QueueAdmissionRepository


# directive: work-transcode-unified | # see work-bucket.C4, work-bucket.C5
class TestQueueAdmissionRepository(unittest.TestCase):

    @classmethod
    # directive: work-transcode-unified
    def setUpClass(cls):
        os.environ.setdefault('MEDIAVORTEX_DB_HOST', '10.0.0.15')

    # directive: work-transcode-unified | # see work-bucket.C5
    def test_admit_one_is_idempotent(self):
        Row = DatabaseService().ExecuteQuery(
            "SELECT Id FROM MediaFiles WHERE WorkBucket = 'Transcode' AND TranscodedByMediaVortex IS NOT TRUE LIMIT 1"
        )
        if not Row:
            self.skipTest("No Transcode MediaFile in DB")
        MediaFileId = int(Row[0]['id'])
        Repo = QueueAdmissionRepository()
        DatabaseService().ExecuteNonQuery(
            "DELETE FROM TranscodeQueue WHERE MediaFileId = %s AND Status = 'Pending'",
            (MediaFileId,),
        )
        R1 = Repo.AdmitOne(MediaFileId, 'Transcode')
        R2 = Repo.AdmitOne(MediaFileId, 'Transcode')
        self.assertEqual(R1.Status, 'queued')
        self.assertEqual(R2.Status, 'already_queued')
        DatabaseService().ExecuteNonQuery(
            "DELETE FROM TranscodeQueue WHERE MediaFileId = %s AND Status = 'Pending'",
            (MediaFileId,),
        )

    # directive: work-transcode-unified | # see work-bucket.C4
    def test_admit_series_idempotent(self):
        Sample = DatabaseService().ExecuteQuery(
            "SELECT mf.StorageRootId, split_part(mf.RelativePath, '/', 1) AS RelativePath, COUNT(*)::int AS c "
            "FROM MediaFiles mf WHERE mf.WorkBucket = 'Transcode' "
            "GROUP BY mf.StorageRootId, split_part(mf.RelativePath, '/', 1) "
            "HAVING COUNT(*) >= 2 LIMIT 1"
        )
        if not Sample:
            self.skipTest("Need a Transcode series with >=2 files")
        S = Sample[0]
        Identity = SeriesIdentity(StorageRootId=int(S['storagerootid']), RelativePath=S['relativepath'])
        DatabaseService().ExecuteNonQuery(
            "DELETE FROM TranscodeQueue WHERE Status='Pending' AND MediaFileId IN ("
            "  SELECT Id FROM MediaFiles WHERE WorkBucket='Transcode' AND StorageRootId=%s AND split_part(RelativePath,'/',1)=%s"
            ")",
            (Identity.StorageRootId, Identity.RelativePath),
        )
        Repo = QueueAdmissionRepository()
        R1 = Repo.AdmitSeries(Identity, BucketKey.FromUrlKey('Transcode'))
        R2 = Repo.AdmitSeries(Identity, BucketKey.FromUrlKey('Transcode'))
        self.assertGreater(R1.Inserted, 0)
        self.assertEqual(R2.Inserted, 0)
        self.assertEqual(R2.AlreadyQueued, R1.Inserted)
        DatabaseService().ExecuteNonQuery(
            "DELETE FROM TranscodeQueue WHERE Status='Pending' AND MediaFileId IN ("
            "  SELECT Id FROM MediaFiles WHERE WorkBucket='Transcode' AND StorageRootId=%s AND split_part(RelativePath,'/',1)=%s"
            ")",
            (Identity.StorageRootId, Identity.RelativePath),
        )


if __name__ == '__main__':
    unittest.main()
