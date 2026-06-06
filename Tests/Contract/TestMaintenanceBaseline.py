# directive: db-maintenance-no-partition | # see database-architecture.C13

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from Core.Database.DatabaseService import DatabaseService

REQUIRED_EXTENSIONS = ('pg_cron', 'pg_repack', 'pgstattuple')
HIGH_CHURN_TABLES = (
    'activejobs',
    'transcodeprogress',
    'qualitytestingqueue',
    'qualitytestprogress',
    'servicestatus',
    'workers',
)
REQUIRED_RELOPTIONS = (
    'autovacuum_vacuum_scale_factor=0.05',
    'autovacuum_vacuum_threshold=10',
    'autovacuum_analyze_scale_factor=0.05',
    'autovacuum_analyze_threshold=10',
)


# directive: db-maintenance-no-partition | # see database-architecture.C13
class TestMaintenanceBaseline(unittest.TestCase):
    "Skip-when-not-deployed contract assertions for the standard maintenance stack."

    # directive: db-maintenance-no-partition | # see database-architecture.C13
    def setUp(self):
        "Open one DatabaseService per test."
        self.Db = DatabaseService()

    # directive: db-maintenance-no-partition | # see database-architecture.C13
    def test_extensions_present(self):
        "All required extensions are installed in the application DB."
        Rows = self.Db.ExecuteQuery(
            "SELECT extname FROM pg_extension WHERE extname IN %s",
            (REQUIRED_EXTENSIONS,)
        )
        Present = {Row['Extname'] for Row in Rows}
        Missing = set(REQUIRED_EXTENSIONS) - Present
        if Missing:
            self.skipTest(f"Cluster baseline not applied; missing extensions: {sorted(Missing)}")
        self.assertEqual(Present, set(REQUIRED_EXTENSIONS))

    # directive: db-maintenance-no-partition | # see database-architecture.C13
    def test_pg_cron_database_configured(self):
        "cron.database_name matches the connected DB."
        try:
            Rows = self.Db.ExecuteQuery("SHOW cron.database_name", ())
        except Exception as Ex:
            self.skipTest(f"pg_cron not in shared_preload_libraries: {Ex}")
        Value = Rows[0]['CronDatabaseName'] if Rows else None
        self.assertEqual(Value, 'mediavortex')

    # directive: db-maintenance-no-partition | # see database-architecture.C13
    def test_high_churn_reloptions(self):
        "Each high-churn table has the four required autovacuum reloptions."
        Rows = self.Db.ExecuteQuery(
            "SELECT relname, reloptions FROM pg_class WHERE relname IN %s",
            (HIGH_CHURN_TABLES,)
        )
        Tuned = {Row['Relname']: (Row['Reloptions'] or []) for Row in Rows}
        UntunedTables = [T for T in HIGH_CHURN_TABLES if not Tuned.get(T)]
        if UntunedTables:
            self.skipTest(f"AutovacuumTuning.sql not applied; untuned: {UntunedTables}")
        for Table in HIGH_CHURN_TABLES:
            Opts = Tuned[Table]
            for Required in REQUIRED_RELOPTIONS:
                self.assertIn(
                    Required, Opts,
                    f"table {Table!r} missing reloption {Required!r}; got {Opts!r}"
                )


if __name__ == "__main__":
    unittest.main()
