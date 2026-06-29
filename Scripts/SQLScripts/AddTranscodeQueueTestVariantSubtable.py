# directive: transcode-worker-unification | # see worker-loop.C3

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: transcode-worker-unification | # see worker-loop.C3
def ColumnExists(Cur, TableName: str, ColumnName: str) -> bool:
    Cur.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=%s AND column_name=%s",
        (TableName.lower(), ColumnName.lower()),
    )
    return Cur.fetchone() is not None


# directive: transcode-worker-unification | # see worker-loop.C3
def RunMigration():
    Db = DatabaseService()
    Conn = Db.GetConnection()
    Cur = Conn.cursor()
    try:
        OriginalColumnPresent = ColumnExists(Cur, 'transcodequeue', 'testvariantsetid')
        DeprecatedColumnPresent = ColumnExists(Cur, 'transcodequeue', 'testvariantsetid_deprecated_2026_06_28')

        if not OriginalColumnPresent and DeprecatedColumnPresent:
            Cur.execute("SELECT COUNT(*)::int FROM TranscodeQueueTestVariant")
            ExistingCount = Cur.fetchone()[0]
            print(f"Migration already applied -- TestVariantSetId deprecated, TranscodeQueueTestVariant has {ExistingCount} rows.")
            return

        if OriginalColumnPresent:
            Cur.execute("SELECT COUNT(*)::int FROM TranscodeQueue WHERE TestVariantSetId IS NOT NULL")
            PreCount = Cur.fetchone()[0]
        else:
            PreCount = 0

        print(f"Creating TranscodeQueueTestVariant subtable (pre-migration non-NULL rows: {PreCount})...")

        Cur.execute(
            "CREATE TABLE IF NOT EXISTS TranscodeQueueTestVariant ("
            "  QueueId BIGINT PRIMARY KEY REFERENCES TranscodeQueue(Id), "
            "  TestVariantSetId INTEGER NOT NULL"
            ")"
        )

        if OriginalColumnPresent:
            Cur.execute(
                "INSERT INTO TranscodeQueueTestVariant (QueueId, TestVariantSetId) "
                "SELECT Id, TestVariantSetId FROM TranscodeQueue WHERE TestVariantSetId IS NOT NULL "
                "ON CONFLICT DO NOTHING"
            )
            BackfilledCount = Cur.rowcount
            print(f"  Backfilled {BackfilledCount} rows into TranscodeQueueTestVariant.")

            Cur.execute(
                "ALTER TABLE TranscodeQueue RENAME COLUMN TestVariantSetId TO TestVariantSetId_DEPRECATED_2026_06_28"
            )
            print("  Renamed TestVariantSetId -> TestVariantSetId_DEPRECATED_2026_06_28.")

        Conn.commit()

        Cur.execute("SELECT COUNT(*)::int FROM TranscodeQueueTestVariant")
        PostCount = Cur.fetchone()[0]
        print(f"Migration complete -- TranscodeQueueTestVariant: {PostCount} rows (expected {PreCount}).")
        if PostCount != PreCount:
            print(f"WARNING: count mismatch. Inspect manually.")
    except Exception:
        Conn.rollback()
        raise
    finally:
        Cur.close()
        Db.CloseConnection(Conn)


if __name__ == '__main__':
    RunMigration()
