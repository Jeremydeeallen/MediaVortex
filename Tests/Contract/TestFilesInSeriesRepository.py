import os
import unittest
from Core.Database.DatabaseService import DatabaseService
from Features.WorkBucket.Domain.BucketKey import BucketKey
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity
from Features.WorkBucket.Repositories.FilesInSeriesRepository import FilesInSeriesRepository


# directive: work-transcode-unified | # see work-bucket.C2
class TestFilesInSeriesRepository(unittest.TestCase):

    @classmethod
    # directive: work-transcode-unified | # see work-bucket.C2
    def setUpClass(cls):
        os.environ.setdefault('MEDIAVORTEX_DB_HOST', '10.0.0.15')

    # directive: work-transcode-unified | # see work-bucket.C2
    def test_returns_only_files_in_the_bucket(self):
        # see work-bucket.C2
        Sample = DatabaseService().ExecuteQuery(
            "SELECT mf.StorageRootId, split_part(mf.RelativePath, '/', 1) AS RelativePath "
            "FROM MediaFiles mf WHERE mf.WorkBucket = 'Transcode' "
            "GROUP BY mf.StorageRootId, split_part(mf.RelativePath, '/', 1) "
            "LIMIT 1"
        )
        if not Sample:
            self.skipTest("No Transcode bucket series in DB")
        S = Sample[0]
        Identity = SeriesIdentity(StorageRootId=int(S['storagerootid']), RelativePath=S['relativepath'])
        Files = FilesInSeriesRepository().ListFilesInSeries(
            Identity=Identity,
            Bucket=BucketKey.FromUrlKey('Transcode'),
        )
        self.assertGreater(len(Files), 0)
        Sizes = [F.SizeGB for F in Files]
        self.assertEqual(Sizes, sorted(Sizes, reverse=True))

    # directive: work-transcode-unified | # see work-bucket.C2
    def test_returns_empty_for_unknown_series(self):
        # see work-bucket.C2
        Files = FilesInSeriesRepository().ListFilesInSeries(
            Identity=SeriesIdentity(StorageRootId=999999, RelativePath='__no_such_show__'),
            Bucket=BucketKey.FromUrlKey('Transcode'),
        )
        self.assertEqual(Files, [])


if __name__ == '__main__':
    unittest.main()
