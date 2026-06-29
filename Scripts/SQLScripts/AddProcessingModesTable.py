# directive: transcode-worker-unification | # see worker-loop.C3

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: transcode-worker-unification | # see worker-loop.C3
def RunMigration():
    Db = DatabaseService()
    Conn = Db.GetConnection()
    Cur = Conn.cursor()
    try:
        Cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='processingmodes'"
        )
        TableExists = Cur.fetchone() is not None

        Cur.execute(
            "CREATE TABLE IF NOT EXISTS ProcessingModes ("
            "  Name TEXT PRIMARY KEY, "
            "  BucketName TEXT NOT NULL, "
            "  RequiresVmaf BOOLEAN NOT NULL DEFAULT FALSE, "
            "  RequiresInterlacedFilter BOOLEAN NOT NULL DEFAULT FALSE, "
            "  RequiresNvencGate BOOLEAN NOT NULL DEFAULT FALSE, "
            "  ClaimCapabilityFlag TEXT NOT NULL"
            ")"
        )

        Cur.execute(
            "INSERT INTO ProcessingModes (Name, BucketName, RequiresVmaf, RequiresInterlacedFilter, RequiresNvencGate, ClaimCapabilityFlag) VALUES "
            "('Transcode', 'Transcode', TRUE, TRUE, FALSE, 'TranscodeEnabled'), "
            "('Remux', 'Remux', FALSE, FALSE, FALSE, 'RemuxEnabled'), "
            "('AudioFix', 'AudioFix', FALSE, FALSE, FALSE, 'RemuxEnabled'), "
            "('SubtitleFix', 'SubtitleFix', FALSE, FALSE, FALSE, 'RemuxEnabled'), "
            "('Quick', 'Quick', FALSE, FALSE, FALSE, 'RemuxEnabled') "
            "ON CONFLICT DO NOTHING"
        )
        InsertedCount = Cur.rowcount

        Conn.commit()

        Cur.execute("SELECT COUNT(*)::int FROM ProcessingModes")
        TotalCount = Cur.fetchone()[0]

        if TableExists and InsertedCount == 0:
            print(f"Migration already applied -- ProcessingModes table exists with {TotalCount} rows.")
        else:
            print(f"Migration complete -- ProcessingModes: {TotalCount} rows ({InsertedCount} inserted this run).")
    except Exception:
        Conn.rollback()
        raise
    finally:
        Cur.close()
        Db.CloseConnection(Conn)


if __name__ == '__main__':
    RunMigration()
