import os
import unittest
from Core.Database.DatabaseService import DatabaseService, EscapeLikePattern
from Features.WorkBucket.Domain.BucketKey import BucketKey
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity
from Features.WorkBucket.Services.QueueAdmissionAppService import QueueAdmissionAppService


# directive: work-transcode-unified | # see work-bucket.C4
class TestQueueAdmissionAppService(unittest.TestCase):

    @classmethod
    # directive: work-transcode-unified | # see work-bucket.C4
    def setUpClass(cls):
        os.environ.setdefault('MEDIAVORTEX_DB_HOST', '10.0.0.15')

    # directive: work-transcode-unified | # see work-bucket.C5
    def test_admit_one_returns_status_and_id(self):
        # see work-bucket.C5
        Pat = '%' + EscapeLikePattern('-mv.') + '%'
        Row = DatabaseService().ExecuteQuery(
            "SELECT Id FROM MediaFiles WHERE WorkBucket = 'Transcode' AND TranscodedByMediaVortex IS NOT TRUE "
            "AND LOWER(RelativePath) NOT LIKE %s ESCAPE '!' LIMIT 1",
            (Pat,),
        )
        if not Row:
            self.skipTest("No Transcode MediaFile in DB")
        MediaFileId = int(Row[0]['id'])
        DatabaseService().ExecuteNonQuery(
            "DELETE FROM TranscodeQueue WHERE MediaFileId = %s AND Status = 'Pending'",
            (MediaFileId,),
        )
        Service = QueueAdmissionAppService()
        Bucket = BucketKey.FromUrlKey('Transcode')
        R1 = Service.AdmitOne(MediaFileId, Bucket)
        R2 = Service.AdmitOne(MediaFileId, Bucket)
        self.assertEqual(R1.Status, 'queued')
        self.assertEqual(R2.Status, 'already_queued')
        self.assertGreater(R1.QueueId, 0)
        self.assertEqual(R1.QueueId, R2.QueueId)
        DatabaseService().ExecuteNonQuery(
            "DELETE FROM TranscodeQueue WHERE MediaFileId = %s AND Status = 'Pending'",
            (MediaFileId,),
        )

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
        self.assertEqual(Result.Inserted + Result.AlreadyQueued + Result.Skipped + Result.AdmissionDeferred + Result.Errored, Result.Total)
        DatabaseService().ExecuteNonQuery(
            "DELETE FROM TranscodeQueue WHERE Status='Pending' AND MediaFileId IN ("
            "  SELECT Id FROM MediaFiles WHERE WorkBucket='Transcode' AND StorageRootId=%s AND split_part(RelativePath,'/',1)=%s"
            ")",
            (Identity.StorageRootId, Identity.RelativePath),
        )


if __name__ == '__main__':
    unittest.main()
