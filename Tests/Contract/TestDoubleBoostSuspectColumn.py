# directive: dialog-boost-emission-integrity | # see .claude/directive.md C3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Core.Database.DatabaseService import DatabaseService


class TestDoubleBoostSuspectColumn(unittest.TestCase):

    def test_column_exists_with_correct_shape(self):
        Rows = DatabaseService().ExecuteQuery(
            "SELECT column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_name = 'mediafiles' AND column_name = 'hasdoubleboostsuspect'"
        )
        self.assertTrue(Rows, "HasDoubleBoostSuspect column must exist on MediaFiles")
        Row = Rows[0]
        self.assertEqual(Row.get('data_type'), 'boolean')
        self.assertEqual(Row.get('is_nullable'), 'NO')
        self.assertIn('false', str(Row.get('column_default') or '').lower())

    def test_flagged_count_matches_source_query(self):
        Flagged = DatabaseService().ExecuteQuery(
            "SELECT COUNT(*) AS n FROM MediaFiles WHERE HasDoubleBoostSuspect = TRUE"
        )
        Source = DatabaseService().ExecuteQuery(
            "SELECT COUNT(DISTINCT MediaFileId) AS n "
            "FROM TranscodeAttempts "
            "WHERE Success = TRUE AND DialogBoostEmitted = TRUE "
            "AND ffpmpegcommand ILIKE %s",
            ('%-mv.mp4"%',),
        )
        FlaggedCount = int((Flagged[0] or {}).get('n') or 0)
        SourceCount = int((Source[0] or {}).get('n') or 0)
        self.assertGreaterEqual(
            FlaggedCount, SourceCount,
            f"backfill undercount: flagged={FlaggedCount}, source-query={SourceCount}"
        )


if __name__ == '__main__':
    unittest.main()
