# directive: mediavortex-output-terminal
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Core.Database.DatabaseService import DatabaseService


class TestWorkBucketMvTerminal(unittest.TestCase):
    """DD2: TranscodedByMediaVortex=TRUE overrides ANY compliance flag combination -> WorkBucket=Compliant."""

    def test_generated_column_short_circuits_on_mv_flag(self):
        Db = DatabaseService()
        Row = Db.ExecuteQuery(
            "SELECT generation_expression FROM information_schema.columns "
            "WHERE table_name = 'mediafiles' AND column_name = 'workbucket'"
        )
        self.assertTrue(Row, "WorkBucket generated column not found")
        Expr = Row[0].get('generation_expression', '')
        self.assertIn('transcodedbymediavortex', Expr.lower(),
                      f'WorkBucket generation expression must reference TranscodedByMediaVortex; got: {Expr}')

    def test_no_mv_output_lands_outside_compliant(self):
        Db = DatabaseService()
        Rows = Db.ExecuteQuery(
            "SELECT COUNT(*) AS N FROM MediaFiles "
            "WHERE TranscodedByMediaVortex = TRUE AND WorkBucket != 'Compliant'"
        )
        Count = int(Rows[0]['n']) if Rows else 0
        self.assertEqual(Count, 0,
                         f'{Count} TranscodedByMediaVortex=TRUE rows are in a non-Compliant bucket; WorkBucket short-circuit is broken')


if __name__ == '__main__':
    unittest.main()
