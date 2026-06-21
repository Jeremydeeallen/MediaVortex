#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


# directive: compliance-cutover
def IsAlreadyGenerated(Cur) -> bool:
    Cur.execute(
        "SELECT is_generated, generation_expression FROM information_schema.columns "
        "WHERE table_name = 'mediafiles' AND column_name = 'workbucket'"
    )
    Row = Cur.fetchone()
    if Row is None or str(Row[0]).upper() != 'ALWAYS':
        return False
    return 'AudioFixOnly' in (Row[1] or '')


# directive: compliance-cutover
def DropConstraintIfExists(Cur, Conn, Name: str):
    Cur.execute(
        "SELECT 1 FROM pg_constraint WHERE conname = %s",
        (Name.lower(),),
    )
    if Cur.fetchone():
        print(f"Dropping constraint {Name}...")
        Cur.execute(f"ALTER TABLE MediaFiles DROP CONSTRAINT {Name}")
        Conn.commit()
        print("  done.")
    else:
        print(f"Constraint {Name} absent -- skipping.")


# directive: compliance-cutover
def RunMigration():
    Db = DatabaseService()
    Conn = Db.GetConnection()
    Cur = Conn.cursor()
    try:
        if IsAlreadyGenerated(Cur):
            print("MediaFiles.WorkBucket is already a GENERATED column -- nothing to do.")
            return

        DropConstraintIfExists(Cur, Conn, 'chk_compliance_consistency')

        print("Dropping existing WorkBucket column + dependent index...")
        Cur.execute("DROP INDEX IF EXISTS idx_mediafiles_workbucket")
        Cur.execute("ALTER TABLE MediaFiles DROP COLUMN IF EXISTS WorkBucket")
        Conn.commit()
        print("  done.")

        print("Adding WorkBucket as GENERATED ALWAYS AS ... STORED column...")
        Cur.execute(
            "ALTER TABLE MediaFiles ADD COLUMN WorkBucket TEXT GENERATED ALWAYS AS ("
            "CASE "
            "WHEN AudioCompliant IS NULL OR VideoCompliant IS NULL OR ContainerCompliant IS NULL THEN NULL "
            "WHEN NOT VideoCompliant THEN 'Transcode' "
            "WHEN NOT ContainerCompliant THEN 'Remux' "
            "WHEN NOT AudioCompliant THEN 'AudioFixOnly' "
            "ELSE NULL "
            "END"
            ") STORED"
        )
        Conn.commit()
        print("  done.")

        print("Creating index idx_mediafiles_workbucket...")
        Cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_mediafiles_workbucket ON MediaFiles(WorkBucket) "
            "WHERE WorkBucket IS NOT NULL"
        )
        Conn.commit()
        print("  done.")

        print("Post-conversion distribution:")
        Cur.execute(
            "SELECT COALESCE(WorkBucket, '(null)') AS Bucket, COUNT(*) "
            "FROM MediaFiles WHERE Resolution IS NOT NULL GROUP BY 1 ORDER BY COUNT(*) DESC"
        )
        for B, C in Cur.fetchall():
            print(f"  {B:>10}  {C}")
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
