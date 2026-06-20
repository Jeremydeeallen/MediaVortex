#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


# directive: compliance-schema-and-audio
def ColumnExists(Cursor, TableName, ColumnName):
    Cursor.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
        (TableName.lower(), ColumnName.lower()),
    )
    return Cursor.fetchone() is not None


# directive: compliance-schema-and-audio
def AddColumn(Cursor, Conn, TableName, ColumnName, ColumnDef):
    if ColumnExists(Cursor, TableName, ColumnName):
        print(f"{TableName}.{ColumnName} already exists -- skipping")
        return
    print(f"Adding {TableName}.{ColumnName} {ColumnDef}...")
    Cursor.execute(f"ALTER TABLE {TableName} ADD COLUMN {ColumnName} {ColumnDef}")
    Conn.commit()
    print("  done.")


# directive: compliance-schema-and-audio
def RunMigration():
    Db = DatabaseService()
    Conn = Db.GetConnection()
    Cur = Conn.cursor()
    try:
        AddColumn(Cur, Conn, 'MediaFiles', 'AudioCompliant', 'BOOLEAN')
        AddColumn(Cur, Conn, 'MediaFiles', 'AudioCompliantReason', 'TEXT')
        AddColumn(Cur, Conn, 'MediaFiles', 'VideoCompliant', 'BOOLEAN')
        AddColumn(Cur, Conn, 'MediaFiles', 'VideoCompliantReason', 'TEXT')
        AddColumn(Cur, Conn, 'MediaFiles', 'ContainerCompliant', 'BOOLEAN')
        AddColumn(Cur, Conn, 'MediaFiles', 'ContainerCompliantReason', 'TEXT')
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
