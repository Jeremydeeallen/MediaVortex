import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: transcode-flow-canonical -- C33 self-heal deletion; correct pipeline needs no sweeper
def Run():
    DB = DatabaseService()

    Existing = DB.ExecuteQuery(
        "SELECT ScannerName, Enabled, LastRunAt FROM Scanners WHERE ScannerName = 'AudioVerticalHealth'"
    )
    if not Existing:
        print("Scanners row 'AudioVerticalHealth' not present -- migration idempotent.")
        return
    print(f"Deleting Scanners row: {Existing[0]}")
    DB.ExecuteNonQuery("DELETE FROM Scanners WHERE ScannerName = 'AudioVerticalHealth'")

    Verify = DB.ExecuteQuery(
        "SELECT COUNT(*) AS n FROM Scanners WHERE ScannerName = 'AudioVerticalHealth'"
    )
    if Verify[0]['n'] != 0:
        raise RuntimeError("Delete failed; row still present")
    print("Row deleted.")

    TableExists = DB.ExecuteQuery(
        "SELECT COUNT(*) AS n FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name='audioverticalhealthruns'"
    )
    if TableExists[0]['n'] > 0:
        RowCount = DB.ExecuteQuery("SELECT COUNT(*) AS n FROM AudioVerticalHealthRuns")
        print(f"Dropping AudioVerticalHealthRuns table ({RowCount[0]['n']} historical rows)...")
        DB.ExecuteNonQuery("DROP TABLE AudioVerticalHealthRuns")
        print("Table dropped.")
    else:
        print("AudioVerticalHealthRuns table not present -- nothing to drop.")


if __name__ == '__main__':
    Run()
