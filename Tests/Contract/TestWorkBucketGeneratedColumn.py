import os
import unittest

from Core.Database.DatabaseService import DatabaseService
from Features.WorkBucket.Domain.BucketKey import BucketKey


# directive: transcode-flow-canonical -- C33j
class TestWorkBucketGeneratedColumn(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('MEDIAVORTEX_DB_HOST', '10.0.0.15')

    def test_bucket_key_registry_includes_new_buckets(self):
        for UrlKey in ('Compliant', 'Unclassified', 'Transcode', 'Remux', 'Audio'):
            self.assertIsNotNone(BucketKey.FromUrlKey(UrlKey),
                f"BucketKey registry must include {UrlKey} per C33")

    def test_generated_column_matches_c33_case_expression(self):
        Db = DatabaseService()
        Rows = Db.ExecuteQuery(
            "SELECT generation_expression FROM information_schema.columns "
            "WHERE table_name='mediafiles' AND column_name='workbucket'"
        )
        self.assertTrue(Rows, "WorkBucket column must exist")
        Expr = Rows[0]['generation_expression']
        for Token in ("'Unclassified'", "'Compliant'", "'Transcode'", "'Remux'", "'AudioFix'"):
            self.assertIn(Token, Expr, f"WorkBucket CASE must include {Token} per C33")

    def test_no_media_file_row_has_null_bucket(self):
        Db = DatabaseService()
        Rows = Db.ExecuteQuery("SELECT COUNT(*) AS n FROM MediaFiles WHERE WorkBucket IS NULL")
        self.assertEqual(Rows[0]['n'], 0,
            "Every MediaFile row must have a non-NULL WorkBucket after C33 migration")

    def test_distinct_buckets_subset_of_c33_set(self):
        Db = DatabaseService()
        Rows = Db.ExecuteQuery("SELECT DISTINCT WorkBucket FROM MediaFiles")
        Distinct = {R['workbucket'] for R in Rows}
        Allowed = {'Compliant', 'Unclassified', 'Transcode', 'Remux', 'AudioFix'}
        self.assertTrue(Distinct.issubset(Allowed),
            f"Distinct buckets {Distinct} must be subset of {Allowed} per C33")


if __name__ == '__main__':
    unittest.main()
