# directive: transcode-flow-canonical
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: transcode-flow-canonical
def RunMigration():
    Db = DatabaseService()
    Conn = Db.GetConnection()
    Cur = Conn.cursor()
    try:
        Cur.execute(
            "SELECT MediaFileId, COUNT(*)::int AS dup_count "
            "FROM TranscodeAttempts "
            "WHERE Success IS NULL "
            "GROUP BY MediaFileId "
            "HAVING COUNT(*) > 1"
        )
        DupGroups = Cur.fetchall()
        TotalDupRows = sum(int(r[1]) for r in DupGroups) - len(DupGroups)
        print(f"Pre-migration: {len(DupGroups)} MediaFiles have duplicate in-flight attempts ({TotalDupRows} excess rows to release).")

        Cur.execute(
            "UPDATE TranscodeAttempts ta1 "
            "SET Success = FALSE, ErrorMessage = 'released_by_single_inflight_migration' "
            "WHERE Success IS NULL "
            "  AND EXISTS ( "
            "    SELECT 1 FROM TranscodeAttempts ta2 "
            "    WHERE ta2.Success IS NULL "
            "      AND ta2.MediaFileId = ta1.MediaFileId "
            "      AND ta2.Id > ta1.Id "
            "  )"
        )
        ReleasedCount = Cur.rowcount
        print(f"Dedup pass released {ReleasedCount} older-Id duplicate in-flight attempts (kept newest Id per MediaFileId).")

        Conn.commit()
        Conn.autocommit = True
        Cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ta_one_inflight_per_mfid "
            "ON TranscodeAttempts (MediaFileId) "
            "WHERE Success IS NULL"
        )
        Conn.autocommit = False
        print("Created (or skipped existing) partial unique index ta_one_inflight_per_mfid on TranscodeAttempts (MediaFileId) WHERE Success IS NULL.")

        Cur.execute(
            "SELECT MediaFileId, COUNT(*)::int FROM TranscodeAttempts "
            "WHERE Success IS NULL "
            "GROUP BY MediaFileId HAVING COUNT(*) > 1"
        )
        RemainingDups = Cur.fetchall()
        if RemainingDups:
            print(f"WARNING: {len(RemainingDups)} MediaFiles still have duplicate in-flight attempts after migration!")
        else:
            print("Verification: zero MediaFiles with duplicate in-flight attempts.")
    except Exception:
        Conn.rollback()
        raise
    finally:
        Cur.close()
        Db.CloseConnection(Conn)


if __name__ == '__main__':
    RunMigration()
