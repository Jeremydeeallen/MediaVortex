import os
import unittest
from Core.Database.DatabaseService import DatabaseService
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity
from Features.WorkBucket.Repositories.SeriesProfileRepository import SeriesProfileRepository


# directive: work-transcode-unified | # see work-bucket.C3
class TestSeriesProfileRepository(unittest.TestCase):
    """Contract: UPSERT / GET / DELETE against SeriesProfiles."""

    @classmethod
    # directive: work-transcode-unified | # see work-bucket.C3
    def setUpClass(cls):
        os.environ.setdefault('MEDIAVORTEX_DB_HOST', '10.0.0.15')
        cls.TestIdentity = SeriesIdentity(StorageRootId=99, RelativePath='__test_series_profile_repo__')

    # directive: work-transcode-unified | # see work-bucket.C3
    def setUp(self):
        DatabaseService().ExecuteNonQuery(
            "DELETE FROM SeriesProfiles WHERE StorageRootId = %s AND RelativePath = %s",
            (self.TestIdentity.StorageRootId, self.TestIdentity.RelativePath),
        )

    # directive: work-transcode-unified | # see work-bucket.C3
    def tearDown(self):
        DatabaseService().ExecuteNonQuery(
            "DELETE FROM SeriesProfiles WHERE StorageRootId = %s AND RelativePath = %s",
            (self.TestIdentity.StorageRootId, self.TestIdentity.RelativePath),
        )

    # directive: work-transcode-unified | # see work-bucket.C3
    def test_get_returns_none_when_absent(self):
        self.assertIsNone(SeriesProfileRepository().GetProfile(self.TestIdentity))

    # directive: work-transcode-unified | # see work-bucket.C3
    def test_upsert_inserts(self):
        Repo = SeriesProfileRepository()
        Repo.UpsertProfile(self.TestIdentity, 'h264-1080p')
        self.assertEqual(Repo.GetProfile(self.TestIdentity), 'h264-1080p')

    # directive: work-transcode-unified | # see work-bucket.C3
    def test_upsert_updates(self):
        Repo = SeriesProfileRepository()
        Repo.UpsertProfile(self.TestIdentity, 'h264-1080p')
        Repo.UpsertProfile(self.TestIdentity, 'hevc-2160p')
        self.assertEqual(Repo.GetProfile(self.TestIdentity), 'hevc-2160p')

    # directive: work-transcode-unified | # see work-bucket.C3
    def test_delete_removes(self):
        Repo = SeriesProfileRepository()
        Repo.UpsertProfile(self.TestIdentity, 'h264-1080p')
        Repo.DeleteProfile(self.TestIdentity)
        self.assertIsNone(Repo.GetProfile(self.TestIdentity))


if __name__ == '__main__':
    unittest.main()
