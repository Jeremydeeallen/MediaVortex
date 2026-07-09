# directive: transcode-flow-canonical
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


# directive: transcode-flow-canonical
def _ColumnExists(Db: DatabaseService, Table: str, Column: str) -> bool:
    Rows = Db.ExecuteQuery(
        "SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name=%s",
        (Table.lower(), Column.lower()),
    )
    return bool(Rows)


# directive: transcode-flow-canonical
def _DropColumnIfExists(Db: DatabaseService, Column: str) -> None:
    if not _ColumnExists(Db, 'workers', Column):
        print(f"  workers.{Column}: already gone (skip)")
        return
    Db.ExecuteNonQuery(f"ALTER TABLE workers DROP COLUMN {Column}", ())
    print(f"  workers.{Column}: dropped")


# directive: transcode-flow-canonical
def Main():
    Db = DatabaseService()
    print("=== RetirePerModeConcurrency ===\n")
    print("Ensure MaxConcurrentJobs holds the authoritative value before dropping per-mode columns")
    Db.ExecuteNonQuery(
        "UPDATE workers SET MaxConcurrentJobs = GREATEST(COALESCE(MaxConcurrentJobs,1), COALESCE(MaxConcurrentTranscodeJobs,1))",
        (),
    )
    print("  MaxConcurrentJobs = GREATEST(existing, MaxConcurrentTranscodeJobs) landed")

    print("\nDrop retired per-mode concurrency columns")
    _DropColumnIfExists(Db, 'MaxConcurrentTranscodeJobs')
    _DropColumnIfExists(Db, 'MaxConcurrentRemuxJobs')

    print("\nVerify")
    Cols = Db.ExecuteQuery(
        "SELECT column_name FROM information_schema.columns WHERE table_name='workers' AND column_name ILIKE 'maxconcurrent%%' ORDER BY column_name",
        (),
    )
    for R in Cols or []:
        print(f"  remaining: {R.get('column_name')}")
    print("\nDone.")


if __name__ == '__main__':
    Main()
