# directive: transcode-worker-unification


import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: transcode-worker-unification
def RunMigration():
    Db = DatabaseService()
    Conn = Db.GetConnection()
    Cur = Conn.cursor()
    try:
        Cur.execute(
            "SELECT MediaFileId, COUNT(*)::int AS dup_count "
            "FROM TranscodeQueue "
            "WHERE Status = 'Pending' AND TestVariantSetId IS NULL "
            "GROUP BY MediaFileId "
            "HAVING COUNT(*) > 1"
        )
        DupGroups = Cur.fetchall()
        TotalDupRows = sum(int(r[1]) for r in DupGroups) - len(DupGroups)
        print(f"Pre-migration: {len(DupGroups)} MediaFiles have duplicate Pending rows ({TotalDupRows} excess rows to drop).")

        Cur.execute(
            "DELETE FROM TranscodeQueue tq1 "
            "WHERE Status = 'Pending' "
            "  AND TestVariantSetId IS NULL "
            "  AND EXISTS ( "
            "    SELECT 1 FROM TranscodeQueue tq2 "
            "    WHERE tq2.Status = 'Pending' "
            "      AND tq2.TestVariantSetId IS NULL "
            "      AND tq2.MediaFileId = tq1.MediaFileId "
            "      AND tq2.Id < tq1.Id "
            "  )"
        )
        RemovedCount = Cur.rowcount
        print(f"Dedup pass removed {RemovedCount} duplicate Pending rows (kept oldest Id per MediaFileId).")

        Conn.commit()
        Conn.autocommit = True
        Cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_transcodequeue_pending_per_mediafile "
            "ON TranscodeQueue (MediaFileId) "
            "WHERE Status = 'Pending' AND TestVariantSetId IS NULL"
        )
        Conn.autocommit = False
        print("Created (or skipped existing) partial unique index idx_transcodequeue_pending_per_mediafile.")

        Cur.execute(
            "SELECT MediaFileId, COUNT(*)::int FROM TranscodeQueue "
            "WHERE Status = 'Pending' AND TestVariantSetId IS NULL "
            "GROUP BY MediaFileId HAVING COUNT(*) > 1"
        )
        RemainingDups = Cur.fetchall()
        if RemainingDups:
            print(f"WARNING: {len(RemainingDups)} MediaFiles still have duplicate Pending rows after migration!")
        else:
            print("Verification: zero MediaFiles with duplicate non-variant Pending rows.")
    except Exception:
        Conn.rollback()
        raise
    finally:
        Cur.close()
        Db.CloseConnection(Conn)


if __name__ == '__main__':
    RunMigration()
