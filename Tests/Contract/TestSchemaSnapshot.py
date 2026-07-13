# directive: transcode-flow-canonical
import unittest

from Core.Database.DatabaseService import DatabaseService
from Core.Database.SchemaChecker import SchemaChecker, SchemaDriftError


# directive: transcode-flow-canonical
class TestSchemaSnapshot(unittest.TestCase):
    """Live-DB contract: committed .claude/schema/snapshot.json must match the live PostgreSQL schema. If a migration lands without regenerating the snapshot, this test fails on CI before the code deploys."""

    @classmethod
    def setUpClass(cls):
        cls.Db = DatabaseService()
        cls.Checker = SchemaChecker(cls.Db)

    def test_snapshot_file_exists(self):
        self.assertTrue(self.Checker.SnapshotPath.exists(), f"Snapshot file missing at {self.Checker.SnapshotPath}. Generate via `py Scripts/Migration/GenerateSchemaSnapshot.py`.")

    def test_snapshot_matches_live(self):
        Snapshot = self.Checker.LoadSnapshot()
        Live = self.Checker.QueryLive()
        D = self.Checker.Diff(Snapshot, Live)
        Breaking = {K: D[K] for K in ('MissingTables', 'MissingColumns', 'TypeMismatches') if D[K]}
        Additive = {K: D[K] for K in ('ExtraTables', 'ExtraColumns') if D[K]}
        self.assertFalse(Breaking, f"Breaking schema drift vs snapshot: {Breaking}. Migrate DB to match snapshot OR regenerate snapshot.")
        if Additive:
            self.fail(f"Additive schema drift vs snapshot (regenerate via Scripts/Migration/GenerateSchemaSnapshot.py): {Additive}")

    def test_assert_matches_passes_on_current(self):
        self.Checker.AssertMatches()

    def test_assert_matches_raises_on_synthetic_missing_table(self):
        Snap = self.Checker.LoadSnapshot()
        Snap['test_nonexistent_table_XYZ'] = {'fake_col': {'data_type': 'text', 'is_nullable': 'YES', 'is_generated': 'NEVER'}}
        Live = self.Checker.QueryLive()
        D = self.Checker.Diff(Snap, Live)
        self.assertIn('test_nonexistent_table_XYZ', D['MissingTables'])

    def test_assert_matches_raises_on_synthetic_missing_column(self):
        Snap = self.Checker.LoadSnapshot()
        AnyTable = next(iter(Snap.keys()))
        Snap[AnyTable]['fake_column_XYZ'] = {'data_type': 'text', 'is_nullable': 'YES', 'is_generated': 'NEVER'}
        Live = self.Checker.QueryLive()
        D = self.Checker.Diff(Snap, Live)
        self.assertIn(f"{AnyTable}.fake_column_XYZ", D['MissingColumns'])


if __name__ == '__main__':
    unittest.main()
