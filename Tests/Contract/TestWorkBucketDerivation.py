import unittest

from Core.Database.DatabaseService import DatabaseService


# directive: compliance-symmetry
class TestWorkBucketDerivation(unittest.TestCase):

    # directive: compliance-symmetry
    def test_workbucket_is_generated(self):
        Db = DatabaseService()
        Rows = Db.ExecuteQuery(
            "SELECT is_generated, generation_expression FROM information_schema.columns "
            "WHERE table_name='mediafiles' AND column_name='workbucket'"
        )
        self.assertEqual(len(Rows), 1)
        self.assertEqual(Rows[0]['is_generated'], 'ALWAYS')
        Expr = (Rows[0]['generation_expression'] or '').lower()
        for Need in ('videocompliant', 'containercompliant', 'audiocompliant',
                     'transcode', 'remux', 'audiofixonly', 'is null'):
            self.assertIn(Need, Expr, f'Generation expression missing token: {Need}')

    # directive: compliance-symmetry
    def test_workbucket_truth_table_against_sql(self):
        Db = DatabaseService()
        TruthTable = [
            (None, None, None, None),
            (True, True, True, None),
            (False, True, True, 'Transcode'),
            (True, False, True, 'Remux'),
            (True, True, False, 'AudioFixOnly'),
            (False, False, False, 'Transcode'),
            (True, False, False, 'Remux'),
            (None, True, True, None),
            (True, None, True, None),
            (True, True, None, None),
        ]
        for V, C, A, Expected in TruthTable:
            with self.subTest(V=V, C=C, A=A):
                Rows = Db.ExecuteQuery(
                    "SELECT CASE "
                    "WHEN %s::boolean IS NULL OR %s::boolean IS NULL OR %s::boolean IS NULL THEN NULL "
                    "WHEN %s::boolean = FALSE THEN 'Transcode' "
                    "WHEN %s::boolean = FALSE THEN 'Remux' "
                    "WHEN %s::boolean = FALSE THEN 'AudioFixOnly' "
                    "ELSE NULL END AS bucket",
                    (V, C, A, V, C, A),
                )
                Got = Rows[0]['bucket']
                self.assertEqual(Got, Expected, f'V={V} C={C} A={A}: expected {Expected!r}, got {Got!r}')


if __name__ == '__main__':
    unittest.main()
