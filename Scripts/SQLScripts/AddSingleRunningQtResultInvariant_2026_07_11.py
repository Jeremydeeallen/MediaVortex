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
            "SELECT TranscodeAttemptId, COUNT(*)::int AS dup_count "
            "FROM QualityTestResults "
            "WHERE Status = 'Running' "
            "GROUP BY TranscodeAttemptId "
            "HAVING COUNT(*) > 1"
        )
        DupGroups = Cur.fetchall()
        TotalDupRows = sum(int(r[1]) for r in DupGroups) - len(DupGroups)
        print(f"Pre-migration: {len(DupGroups)} TranscodeAttemptIds have duplicate Running QT results ({TotalDupRows} excess rows to release).")

        Cur.execute(
            "UPDATE QualityTestResults q1 "
            "SET Status = 'Failed', ErrorMessage = 'released_by_single_running_qt_migration' "
            "WHERE Status = 'Running' "
            "  AND EXISTS ( "
            "    SELECT 1 FROM QualityTestResults q2 "
            "    WHERE q2.Status = 'Running' "
            "      AND q2.TranscodeAttemptId = q1.TranscodeAttemptId "
            "      AND q2.Id > q1.Id "
            "  )"
        )
        ReleasedCount = Cur.rowcount
        print(f"Dedup pass released {ReleasedCount} older-Id duplicate Running QT results (kept newest Id per TranscodeAttemptId).")

        Conn.commit()
        Conn.autocommit = True
        Cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS qtr_one_running_per_attempt "
            "ON QualityTestResults (TranscodeAttemptId) "
            "WHERE Status = 'Running'"
        )
        Conn.autocommit = False
        print("Created (or skipped existing) partial unique index qtr_one_running_per_attempt on QualityTestResults (TranscodeAttemptId) WHERE Status = 'Running'.")

        Cur.execute(
            "SELECT TranscodeAttemptId, COUNT(*)::int FROM QualityTestResults "
            "WHERE Status = 'Running' "
            "GROUP BY TranscodeAttemptId HAVING COUNT(*) > 1"
        )
        RemainingDups = Cur.fetchall()
        if RemainingDups:
            print(f"WARNING: {len(RemainingDups)} TranscodeAttemptIds still have duplicate Running QT results!")
        else:
            print("Verification: zero TranscodeAttemptIds with duplicate Running QT results.")
    except Exception:
        Conn.rollback()
        raise
    finally:
        Cur.close()
        Db.CloseConnection(Conn)


if __name__ == '__main__':
    RunMigration()
