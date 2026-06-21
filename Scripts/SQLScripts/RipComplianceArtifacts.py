#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


# directive: compliance-rip
def ColumnExists(Cur, Table: str, Col: str) -> bool:
    Cur.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
        (Table.lower(), Col.lower()),
    )
    return Cur.fetchone() is not None


# directive: compliance-rip
def TableExists(Cur, Name: str) -> bool:
    Cur.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s",
        (Name.lower(),),
    )
    return Cur.fetchone() is not None


# directive: compliance-rip
def IsGenerated(Cur, Table: str, Col: str) -> bool:
    Cur.execute(
        "SELECT is_generated FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
        (Table.lower(), Col.lower()),
    )
    Row = Cur.fetchone()
    return Row is not None and str(Row[0]).upper() == 'ALWAYS'


# directive: compliance-rip
def DropColumnIfExists(Cur, Conn, Table: str, Col: str):
    if not ColumnExists(Cur, Table, Col):
        print(f"{Table}.{Col} absent -- skipping")
        return
    print(f"Dropping {Table}.{Col}...")
    Cur.execute(f"ALTER TABLE {Table} DROP COLUMN {Col}")
    Conn.commit()
    print("  done.")


# directive: compliance-rip
def RenameTableIfExists(Cur, Conn, Old: str, New: str):
    if not TableExists(Cur, Old):
        print(f"Table {Old} absent -- skipping (already renamed?)")
        return
    if TableExists(Cur, New):
        print(f"Target {New} already exists -- skipping rename")
        return
    print(f"Renaming {Old} -> {New}...")
    Cur.execute(f"ALTER TABLE {Old} RENAME TO {New}")
    Conn.commit()
    print("  done.")


# directive: compliance-rip
def ConvertIsCompliantToGenerated(Cur, Conn):
    if IsGenerated(Cur, 'MediaFiles', 'IsCompliant'):
        print("MediaFiles.IsCompliant already GENERATED -- skipping")
        return
    if not ColumnExists(Cur, 'MediaFiles', 'IsCompliant'):
        print("MediaFiles.IsCompliant absent -- adding as GENERATED...")
    else:
        print("Dropping existing IsCompliant column...")
        Cur.execute("ALTER TABLE MediaFiles DROP COLUMN IsCompliant")
        Conn.commit()
    print("Adding MediaFiles.IsCompliant as GENERATED ALWAYS AS ... STORED...")
    Cur.execute(
        "ALTER TABLE MediaFiles ADD COLUMN IsCompliant BOOLEAN GENERATED ALWAYS AS ("
        "CASE "
        "WHEN AudioCompliant IS NULL OR VideoCompliant IS NULL OR ContainerCompliant IS NULL THEN NULL "
        "WHEN AudioCompliant AND VideoCompliant AND ContainerCompliant THEN TRUE "
        "ELSE FALSE "
        "END"
        ") STORED"
    )
    Conn.commit()
    print("  done.")


# directive: compliance-rip
def RunMigration():
    Db = DatabaseService()
    Conn = Db.GetConnection()
    Cur = Conn.cursor()
    try:
        DropColumnIfExists(Cur, Conn, 'MediaFiles', 'OperationsNeededCsv')
        DropColumnIfExists(Cur, Conn, 'MediaFiles', 'ComplianceGateBlocked')
        DropColumnIfExists(Cur, Conn, 'MediaFiles', 'ComplianceEvaluatedAt')

        ConvertIsCompliantToGenerated(Cur, Conn)

        for Old, New in [
            ('TranscodeRules', 'TranscodeRules_OLD_2026_06_21'),
            ('RemuxRules', 'RemuxRules_OLD_2026_06_21'),
            ('AudioFixRules', 'AudioFixRules_OLD_2026_06_21'),
            ('SubtitleFixRules', 'SubtitleFixRules_OLD_2026_06_21'),
            ('ComplianceGates', 'ComplianceGates_OLD_2026_06_21'),
        ]:
            RenameTableIfExists(Cur, Conn, Old, New)

        print()
        print("Final IsCompliant distribution (probed files):")
        Cur.execute(
            "SELECT COALESCE(IsCompliant::text, '(null)') AS B, COUNT(*) "
            "FROM MediaFiles WHERE Resolution IS NOT NULL GROUP BY 1 ORDER BY COUNT(*) DESC"
        )
        for B, C in Cur.fetchall():
            print(f"  IsCompliant={B:>8}  count={C}")
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
