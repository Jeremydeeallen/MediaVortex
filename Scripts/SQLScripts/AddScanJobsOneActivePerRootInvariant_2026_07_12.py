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
            "SELECT StorageRootId, RelativePath, COUNT(*)::int AS dup_count "
            "FROM ScanJobs "
            "WHERE Status IN ('Pending', 'Running') "
            "GROUP BY StorageRootId, RelativePath "
            "HAVING COUNT(*) > 1"
        )
        DupGroups = Cur.fetchall()
        TotalDupRows = sum(int(r[2]) for r in DupGroups) - len(DupGroups)
        print(f"Pre-migration: {len(DupGroups)} rootfolders have duplicate active scans ({TotalDupRows} excess rows to fail).")

        Cur.execute(
            "UPDATE ScanJobs sj1 "
            "SET Status = 'Failed', EndTime = NOW(), ErrorMessage = 'released_by_one_active_per_root_migration' "
            "WHERE Status IN ('Pending', 'Running') "
            "  AND EXISTS ( "
            "    SELECT 1 FROM ScanJobs sj2 "
            "    WHERE sj2.Status IN ('Pending', 'Running') "
            "      AND sj2.StorageRootId = sj1.StorageRootId "
            "      AND COALESCE(sj2.RelativePath, '') = COALESCE(sj1.RelativePath, '') "
            "      AND sj2.Id > sj1.Id "
            "  )"
        )
        ReleasedCount = Cur.rowcount
        print(f"Dedup pass failed {ReleasedCount} older-Id duplicate active scans (kept newest Id per rootfolder).")

        Conn.commit()
        Conn.autocommit = True
        Cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS sj_one_active_per_root "
            "ON ScanJobs (StorageRootId, COALESCE(RelativePath, '')) "
            "WHERE Status IN ('Pending', 'Running')"
        )
        Conn.autocommit = False
        print("Created (or skipped existing) partial unique index sj_one_active_per_root on ScanJobs (StorageRootId, RelativePath) WHERE Status IN ('Pending', 'Running').")

        Cur.execute(
            "SELECT StorageRootId, RelativePath, COUNT(*)::int FROM ScanJobs "
            "WHERE Status IN ('Pending', 'Running') "
            "GROUP BY StorageRootId, RelativePath HAVING COUNT(*) > 1"
        )
        RemainingDups = Cur.fetchall()
        if RemainingDups:
            print(f"WARNING: {len(RemainingDups)} rootfolders still have duplicate active scans!")
        else:
            print("Verification: zero rootfolders with duplicate active scans.")
    except Exception:
        Conn.rollback()
        raise
    finally:
        Cur.close()
        Db.CloseConnection(Conn)


if __name__ == '__main__':
    RunMigration()
