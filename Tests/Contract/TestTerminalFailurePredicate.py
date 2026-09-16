# directive: bug-0095-failure-classification | # see failure-accounting.C11
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Core.Database.TerminalFailurePredicate import (
    BuildTerminalGate,
    IsMediaFileTerminalBlocked,
    GetTerminalRemediation,
    _ALLOWED_MEDIAFILE_COLUMNS,
)
from Core.Database.DatabaseService import DatabaseService


class TestTerminalFailurePredicateShape(unittest.TestCase):

    def test_returns_sql_fragment_and_empty_params(self):
        Fragment, Params = BuildTerminalGate("mf.Id")
        self.assertIsInstance(Fragment, str)
        self.assertTrue(Fragment.startswith("NOT EXISTS"))
        self.assertIn("FailureClasses", Fragment)
        self.assertIn("Terminal = TRUE", Fragment)
        self.assertEqual(Params, ())

    def test_column_whitelist_refuses_injection(self):
        with self.assertRaises(ValueError):
            BuildTerminalGate("mf.Id; DROP TABLE users;")
        with self.assertRaises(ValueError):
            BuildTerminalGate("evil OR 1=1")

    def test_column_whitelist_accepts_known_columns(self):
        for Col in _ALLOWED_MEDIAFILE_COLUMNS:
            Fragment, _ = BuildTerminalGate(Col)
            self.assertIn(Col, Fragment)

    def test_fragment_embeds_in_valid_sql(self):
        """Fragment must be syntactically valid inside a WHERE clause against MediaFiles."""
        Fragment, _ = BuildTerminalGate("mf.Id")
        Db = DatabaseService()
        Rows = Db.ExecuteQuery(
            f"SELECT COUNT(*) AS n FROM MediaFiles mf WHERE {Fragment} AND mf.Id = -1"
        )
        self.assertEqual(int(Rows[0]['n']), 0)


class TestTerminalPointQuery(unittest.TestCase):

    def test_admits_when_no_failure(self):
        Db = DatabaseService()
        Rows = Db.ExecuteQuery(
            "SELECT mf.Id FROM MediaFiles mf "
            "LEFT JOIN TranscodeAttempts ta ON ta.MediaFileId = mf.Id "
            "GROUP BY mf.Id HAVING COUNT(ta.Id) = 0 LIMIT 1"
        )
        if not Rows:
            self.skipTest("no MediaFile without any attempt found")
        Mfid = int(Rows[0]['Id'])
        self.assertFalse(IsMediaFileTerminalBlocked(Mfid))
        self.assertIsNone(GetTerminalRemediation(Mfid))


if __name__ == '__main__':
    unittest.main()
