import unittest

from Core.Database.DatabaseService import DatabaseService


# directive: compliance-symmetry
class TestComplianceIdempotency(unittest.TestCase):

    # directive: compliance-symmetry
    def setUp(self):
        self.Db = DatabaseService()
        Rows = self.Db.ExecuteQuery(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='mediafilesarchive' AND column_name='workbucket'"
        )
        self._HasArchiveBucket = bool(Rows)

    # directive: compliance-symmetry
    def test_no_audiofixonly_demoted_to_transcode(self):
        if not self._HasArchiveBucket:
            self.skipTest('MediaFilesArchive does not carry WorkBucket; idempotency probe is via live-pipeline E2E')
            return
        Rows = self.Db.ExecuteQuery(
            "SELECT COUNT(*) AS cnt FROM MediaFilesArchive a "
            "JOIN MediaFiles m ON m.Id = a.MediaFileId "
            "WHERE a.WorkBucket = 'AudioFixOnly' AND m.WorkBucket = 'Transcode'"
        )
        self.assertEqual(Rows[0]['cnt'], 0, 'AudioFixOnly worker must not poison VideoCompliant')

    # directive: compliance-symmetry
    def test_no_audiofixonly_demoted_to_remux(self):
        if not self._HasArchiveBucket:
            self.skipTest('MediaFilesArchive does not carry WorkBucket')
            return
        Rows = self.Db.ExecuteQuery(
            "SELECT COUNT(*) AS cnt FROM MediaFilesArchive a "
            "JOIN MediaFiles m ON m.Id = a.MediaFileId "
            "WHERE a.WorkBucket = 'AudioFixOnly' AND m.WorkBucket = 'Remux'"
        )
        self.assertEqual(Rows[0]['cnt'], 0, 'AudioFixOnly worker must not poison ContainerCompliant')

    # directive: compliance-symmetry
    def test_no_remux_demoted_to_transcode(self):
        if not self._HasArchiveBucket:
            self.skipTest('MediaFilesArchive does not carry WorkBucket')
            return
        Rows = self.Db.ExecuteQuery(
            "SELECT COUNT(*) AS cnt FROM MediaFilesArchive a "
            "JOIN MediaFiles m ON m.Id = a.MediaFileId "
            "WHERE a.WorkBucket = 'Remux' AND m.WorkBucket = 'Transcode'"
        )
        self.assertEqual(Rows[0]['cnt'], 0, 'Remux worker must not poison VideoCompliant')


if __name__ == '__main__':
    unittest.main()
