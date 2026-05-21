"""Drop LocalStaging mode from the database.

Context: LocalStaging was introduced to work around Brain's RAID5 saturating
under 4 concurrent workers (see archived local-staging.feature.md). The
2026-05 migration to Porky's 7-disk ZFS over 40 GbE removed that bottleneck;
only 4 of 17 workers were ever opted in, and the rest silently ran InPlace.
This script collapses the schema to a single mode (InPlace).

Operations:
    1. DELETE FROM systemsettings WHERE settingkey = 'TranscodeFileMode'
       (no caller needs a setting when there is only one mode)
    2. ALTER TABLE workers DROP COLUMN stagingdirectory

Usage:
    py Scripts/SQLScripts/drop_local_staging_2026_05_21.py            # dry-run
    py Scripts/SQLScripts/drop_local_staging_2026_05_21.py --execute  # apply
"""

import argparse
import sys

sys.path.insert(0, '.')
from Core.Database.DatabaseService import DatabaseService


def Main() -> int:
    Parser = argparse.ArgumentParser(description=__doc__)
    Parser.add_argument("--execute", action="store_true",
                        help="Apply changes. Default is dry-run.")
    Args = Parser.parse_args()
    Mode = "EXECUTE" if Args.execute else "DRY-RUN"

    Db = DatabaseService()
    print(f"\n=== Drop LocalStaging ({Mode}) ===\n")

    SettingRows = Db.ExecuteQuery(
        "SELECT SettingKey, SettingValue FROM SystemSettings WHERE SettingKey = 'TranscodeFileMode'")
    print(f"systemsettings.TranscodeFileMode rows: {len(SettingRows)}")
    for r in SettingRows:
        print(f"  current value = {r['SettingValue']!r}")

    NonNullStaging = Db.ExecuteQuery(
        "SELECT WorkerName, StagingDirectory FROM Workers WHERE StagingDirectory IS NOT NULL ORDER BY WorkerName")
    print(f"\nworkers with StagingDirectory set: {len(NonNullStaging)}")
    for r in NonNullStaging:
        print(f"  {r['WorkerName']:<20} {r['StagingDirectory']}")

    ColExists = Db.ExecuteQuery(
        "SELECT 1 FROM information_schema.columns WHERE table_name='workers' AND column_name='stagingdirectory'")
    print(f"\nworkers.stagingdirectory column exists: {bool(ColExists)}")

    if not Args.execute:
        print("\nWould:")
        print("  1. DELETE FROM systemsettings WHERE settingkey='TranscodeFileMode'")
        print("  2. ALTER TABLE workers DROP COLUMN stagingdirectory")
        print("\nRe-run with --execute to apply.")
        return 0

    Conn = Db.GetConnection()
    Cur = Conn.cursor()
    try:
        Cur.execute("DELETE FROM systemsettings WHERE settingkey = 'TranscodeFileMode'")
        Deleted = Cur.rowcount
        print(f"\nDeleted {Deleted} systemsettings row(s).")

        if ColExists:
            Cur.execute("ALTER TABLE workers DROP COLUMN stagingdirectory")
            print("Dropped workers.stagingdirectory column.")
        else:
            print("workers.stagingdirectory already absent -- skipping ALTER.")

        Conn.commit()
        print("\nCommitted.")
        return 0
    except Exception as Exc:
        Conn.rollback()
        print(f"\nERROR -- rolled back. {type(Exc).__name__}: {Exc}", file=sys.stderr)
        return 1
    finally:
        Cur.close()
        Db.CloseConnection(Conn)


if __name__ == "__main__":
    sys.exit(Main())
