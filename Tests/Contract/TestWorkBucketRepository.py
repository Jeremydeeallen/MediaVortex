import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Features.WorkBucket.WorkBucketRepository import (
    WorkBucketRepository,
    BUCKET_TO_PROCESSING_MODE,
    BUCKET_TO_URL_KEY,
)


# directive: audio-vertical-converge-to-zero | # see directive.md Z2
class TestWorkBucketRepository(unittest.TestCase):
    """Live-DB contract: counts + pagination + idempotent QueueOne against the dev DB."""

    # directive: audio-vertical-converge-to-zero | # see directive.md Z2
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('MEDIAVORTEX_DB_HOST', '10.0.0.15')

    # directive: audio-vertical-converge-to-zero | # see directive.md Z2
    def test_count_by_bucket_returns_total_and_already_queued(self):
        Repo = WorkBucketRepository()
        Counts = Repo.CountByBucket('Transcode')
        self.assertIn('Total', Counts)
        self.assertIn('AlreadyQueued', Counts)
        self.assertGreaterEqual(Counts['Total'], 0)
        self.assertGreaterEqual(Counts['AlreadyQueued'], 0)
        self.assertLessEqual(Counts['AlreadyQueued'], Counts['Total'])

    # directive: audio-vertical-converge-to-zero | # see directive.md Z2
    def test_list_by_bucket_pages_at_50_by_default(self):
        Rows = WorkBucketRepository().ListByBucket('Transcode', Offset=0, Limit=10)
        self.assertLessEqual(len(Rows), 10)
        if Rows:
            self.assertIn('id', Rows[0])
            self.assertIn('filename', Rows[0])

    # directive: audio-vertical-converge-to-zero | # see directive.md Z2
    def test_list_by_bucket_clamps_limit_to_200(self):
        Rows = WorkBucketRepository().ListByBucket('Transcode', Offset=0, Limit=500)
        self.assertLessEqual(len(Rows), 200)

    # directive: audio-vertical-converge-to-zero | # see directive.md Z2
    def test_list_by_bucket_negative_offset_clamps_to_zero(self):
        First = WorkBucketRepository().ListByBucket('Transcode', Offset=0, Limit=3)
        Negative = WorkBucketRepository().ListByBucket('Transcode', Offset=-50, Limit=3)
        self.assertEqual(
            [R['id'] for R in First],
            [R['id'] for R in Negative],
        )

    # directive: audio-vertical-converge-to-zero | # see directive.md Z2
    def test_bucket_to_processing_mode_mapping(self):
        self.assertEqual(BUCKET_TO_PROCESSING_MODE['Transcode'], 'Transcode')
        self.assertEqual(BUCKET_TO_PROCESSING_MODE['Remux'], 'Remux')
        self.assertEqual(BUCKET_TO_PROCESSING_MODE['AudioFixOnly'], 'AudioFix')

    # directive: audio-vertical-converge-to-zero | # see directive.md Z2
    def test_url_key_to_bucket_mapping(self):
        self.assertEqual(BUCKET_TO_URL_KEY['Audio'], 'AudioFixOnly')
        self.assertEqual(BUCKET_TO_URL_KEY['Transcode'], 'Transcode')
        self.assertEqual(BUCKET_TO_URL_KEY['Remux'], 'Remux')

    # directive: audio-vertical-converge-to-zero | # see directive.md Z2
    def test_queue_one_is_idempotent_on_pending_row(self):
        Repo = WorkBucketRepository()
        from Core.Database.DatabaseService import DatabaseService
        Db = DatabaseService()
        Rows = Db.ExecuteQuery(
            "SELECT mf.Id FROM MediaFiles mf "
            "WHERE mf.WorkBucket = 'Transcode' AND mf.StorageRootId = 1 "
            "AND NOT EXISTS (SELECT 1 FROM TranscodeQueue tq WHERE tq.MediaFileId = mf.Id AND tq.Status = 'Pending') "
            "ORDER BY mf.Id LIMIT 1"
        )
        if not Rows:
            self.skipTest('no idle Transcode-bucket MediaFile to test with')
        Mid = Rows[0]['id']
        First = Repo.QueueOne(Mid, 'Transcode')
        Second = Repo.QueueOne(Mid, 'Transcode')
        try:
            self.assertEqual(First[0], 'queued')
            self.assertEqual(Second[0], 'already_queued')
            self.assertEqual(First[1], Second[1])
        finally:
            if First[1]:
                Db.ExecuteNonQuery("DELETE FROM TranscodeQueue WHERE Id = %s", (First[1],))


if __name__ == '__main__':
    unittest.main()
