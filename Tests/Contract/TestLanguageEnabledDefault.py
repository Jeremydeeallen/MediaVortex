import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Core.Database.DatabaseService import DatabaseService


# directive: audio-language-detection C8
class TestLanguageEnabledDefault(unittest.TestCase):

    def test_workers_language_enabled_column_exists_with_default_false(self):
        Rows = DatabaseService().ExecuteQuery(
            "SELECT column_name, column_default, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_name='workers' AND column_name='languageenabled'"
        )
        self.assertEqual(len(Rows), 1, 'LanguageEnabled column missing on Workers')
        Row = Rows[0]
        Default = (Row.get('column_default') or Row.get('COLUMN_DEFAULT') or '').lower()
        self.assertIn('false', Default, msg=f'default should be FALSE, got: {Default!r}')
        Nullable = Row.get('is_nullable') or Row.get('IS_NULLABLE')
        self.assertEqual(str(Nullable).upper(), 'NO')

    def test_every_existing_worker_row_defaults_to_false(self):
        Rows = DatabaseService().ExecuteQuery(
            "SELECT WorkerName, LanguageEnabled FROM Workers WHERE Enabled=TRUE"
        )
        for R in Rows:
            self.assertIn(bool(R.get('LanguageEnabled') or R.get('languageenabled')), (False,),
                          msg=f"worker {R.get('WorkerName')} had LanguageEnabled=TRUE after migration")


if __name__ == '__main__':
    unittest.main()
