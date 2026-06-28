# directive: work-transcode-unified | # see work-bucket.C3

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: work-transcode-unified | # see work-bucket.C3
def TableExists(Cursor, Name) -> bool:
    Cursor.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
        (Name.lower(),),
    )
    return Cursor.fetchone() is not None


# directive: work-transcode-unified | # see work-bucket.C3
def RunMigration():
    Db = DatabaseService()
    Conn = Db.GetConnection()
    Cur = Conn.cursor()
    try:
        SeriesExists = TableExists(Cur, 'seriesprofiles')
        ShowExists = TableExists(Cur, 'showsettings')
        DeprecatedExists = TableExists(Cur, 'showsettings_deprecated_2026_06_28')

        if SeriesExists and DeprecatedExists and not ShowExists:
            print("Migration already applied -- SeriesProfiles + deprecated marker present, no live ShowSettings.")
            return

        if SeriesExists and ShowExists:
            print("Both SeriesProfiles and ShowSettings exist -- inconsistent state. Aborting; investigate manually.")
            sys.exit(1)

        print("Beginning migration...")

        if not SeriesExists:
            print("  CREATE TABLE IF NOT EXISTS SeriesProfiles ...")
            Cur.execute(
                "CREATE TABLE IF NOT EXISTS SeriesProfiles ("
                "  Id SERIAL PRIMARY KEY, "
                "  StorageRootId INTEGER NOT NULL, "
                "  RelativePath VARCHAR(500) NOT NULL, "
                "  TargetResolution VARCHAR(20), "
                "  AssignedProfile VARCHAR(100), "
                "  CreatedDate TIMESTAMP NOT NULL DEFAULT NOW(), "
                "  LastModifiedDate TIMESTAMP NOT NULL DEFAULT NOW(), "
                "  CONSTRAINT seriesprofiles_natural_key UNIQUE (StorageRootId, RelativePath)"
                ")"
            )
            Cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_seriesprofiles_lookup "
                "ON SeriesProfiles (StorageRootId, RelativePath)"
            )

        if ShowExists:
            print("  INSERT INTO SeriesProfiles SELECT ... FROM ShowSettings ON CONFLICT DO NOTHING ...")
            Cur.execute(
                "INSERT INTO SeriesProfiles "
                "  (StorageRootId, RelativePath, TargetResolution, AssignedProfile, CreatedDate, LastModifiedDate) "
                "SELECT StorageRootId, RelativePath, TargetResolution, AssignedProfile, "
                "       CreatedDate, LastModifiedDate "
                "  FROM ShowSettings "
                "ON CONFLICT (StorageRootId, RelativePath) DO NOTHING"
            )
            CopiedCount = Cur.rowcount
            print(f"    copied {CopiedCount} rows")
            print("  ALTER TABLE ShowSettings RENAME TO ShowSettings_DEPRECATED_2026_06_28 ...")
            Cur.execute("ALTER TABLE ShowSettings RENAME TO ShowSettings_DEPRECATED_2026_06_28")

        Conn.commit()

        Cur.execute("SELECT COUNT(*)::int FROM SeriesProfiles")
        NewCount = Cur.fetchone()[0]
        print(f"  SeriesProfiles: {NewCount} rows")
        if TableExists(Cur, 'showsettings_deprecated_2026_06_28'):
            Cur.execute("SELECT COUNT(*)::int FROM ShowSettings_DEPRECATED_2026_06_28")
            DepCount = Cur.fetchone()[0]
            print(f"  ShowSettings_DEPRECATED_2026_06_28: {DepCount} rows")
            if DepCount != NewCount:
                print("  WARNING: row counts diverge. Inspect manually.")

        print("Migration complete.")
    except Exception:
        Conn.rollback()
        raise
    finally:
        Cur.close()
        Db.CloseConnection(Conn)


if __name__ == '__main__':
    RunMigration()
