# directive: transcode-worker-unification | # see worker-loop.C3

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService

# directive: transcode-worker-unification
_NEW_GENERATED_EXPR = (
    "CASE "
    "WHEN (videocompliant IS NULL OR containercompliant IS NULL OR audiocompliant IS NULL) THEN NULL::text "
    "WHEN videocompliant = false THEN 'Transcode'::text "
    "WHEN containercompliant = false THEN 'Remux'::text "
    "WHEN audiocompliant = false THEN 'AudioFix'::text "
    "ELSE NULL::text "
    "END"
)


# directive: transcode-worker-unification | # see worker-loop.C3
def GetCurrentGeneratedExpr(Cur) -> str:
    Cur.execute(
        "SELECT pg_get_expr(adbin, adrelid) "
        "FROM pg_attribute a "
        "JOIN pg_attrdef d ON a.attrelid = d.adrelid AND a.attnum = d.adnum "
        "WHERE a.attrelid = 'mediafiles'::regclass AND a.attname = 'workbucket'"
    )
    Row = Cur.fetchone()
    return Row[0] if Row else None


# directive: transcode-worker-unification | # see worker-loop.C3
def RunMigration():
    Db = DatabaseService()
    Conn = Db.GetConnection()
    Cur = Conn.cursor()
    try:
        CurrentExpr = GetCurrentGeneratedExpr(Cur)

        if CurrentExpr is None:
            Cur.execute("SELECT COUNT(*)::int FROM MediaFiles WHERE WorkBucket = 'AudioFixOnly'")
            RemainingCount = Cur.fetchone()[0]
            if RemainingCount == 0:
                print("Migration already applied -- no 'AudioFixOnly' rows in MediaFiles (regular column).")
                return
            Cur.execute("UPDATE MediaFiles SET WorkBucket = 'AudioFix' WHERE WorkBucket = 'AudioFixOnly'")
            UpdatedCount = Cur.rowcount
            Conn.commit()
            print(f"Migration complete -- updated {UpdatedCount} MediaFiles rows from 'AudioFixOnly' to 'AudioFix'.")
            return

        if 'AudioFixOnly' not in CurrentExpr:
            Cur.execute("SELECT COUNT(*)::int FROM MediaFiles WHERE WorkBucket = 'AudioFixOnly'")
            RemainCount = Cur.fetchone()[0]
            if RemainCount == 0:
                print("Migration already applied -- generated expression does not reference 'AudioFixOnly' and no rows match.")
                return

        print("Regenerating WorkBucket generated column to replace 'AudioFixOnly' with 'AudioFix'...")
        Cur.execute("ALTER TABLE MediaFiles DROP COLUMN WorkBucket")
        Cur.execute(
            f"ALTER TABLE MediaFiles ADD COLUMN WorkBucket TEXT GENERATED ALWAYS AS ({_NEW_GENERATED_EXPR}) STORED"
        )

        Conn.commit()

        NewExpr = GetCurrentGeneratedExpr(Cur)
        Cur.execute("SELECT COUNT(*)::int FROM MediaFiles WHERE WorkBucket = 'AudioFixOnly'")
        RemainingAudioFixOnly = Cur.fetchone()[0]
        Cur.execute("SELECT COUNT(*)::int FROM MediaFiles WHERE WorkBucket = 'AudioFix'")
        AudioFixCount = Cur.fetchone()[0]

        print(f"Migration complete -- AudioFixOnly rows: {RemainingAudioFixOnly} (expect 0), AudioFix rows: {AudioFixCount}.")
        if RemainingAudioFixOnly != 0:
            print("WARNING: 'AudioFixOnly' rows still present. Inspect manually.")
    except Exception:
        Conn.rollback()
        raise
    finally:
        Cur.close()
        Db.CloseConnection(Conn)


if __name__ == '__main__':
    RunMigration()
