"""Idempotent migration: rename FilePath columns to FilePath_Deprecated on child tables.

TranscodeQueue.FilePath is NOT renamed (it's a display column still in use).
CompliantFiles.FilePath is NOT renamed (no active code reads it).

This is a soft delete -- the columns still exist with their data for rollback.
Drop them in Phase 4 after confirming everything works.

Rollback:
    ALTER TABLE TranscodeAttempts RENAME COLUMN FilePath_Deprecated TO FilePath;
    ALTER TABLE TranscodeFiles RENAME COLUMN FilePath_Deprecated TO FilePath;
    ALTER TABLE ProblemFiles RENAME COLUMN FilePath_Deprecated TO FilePath;
"""
import os
import psycopg2


def GetConnection():
    return psycopg2.connect(
        host=os.environ.get('MEDIAVORTEX_DB_HOST', 'localhost'),
        port=int(os.environ.get('MEDIAVORTEX_DB_PORT', 5432)),
        dbname=os.environ.get('MEDIAVORTEX_DB_NAME', 'mediavortex'),
        user=os.environ.get('MEDIAVORTEX_DB_USER', 'mediavortex'),
        password=os.environ.get('MEDIAVORTEX_DB_PASSWORD', 'mediavortex'),
    )


def ColumnExists(Cursor, TableName, ColumnName):
    Cursor.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
        (TableName.lower(), ColumnName.lower()),
    )
    return Cursor.fetchone() is not None


def RenameColumn(Cursor, TableName, OldName, NewName):
    if ColumnExists(Cursor, TableName, OldName) and not ColumnExists(Cursor, TableName, NewName):
        Cursor.execute(f'ALTER TABLE {TableName} RENAME COLUMN "{OldName}" TO "{NewName}"')
        print(f"  Renamed {TableName}.{OldName} -> {NewName}")
    elif ColumnExists(Cursor, TableName, NewName):
        print(f"  {TableName}.{NewName} already exists -- skipping")
    else:
        print(f"  {TableName}.{OldName} not found -- skipping")


def Main():
    Connection = GetConnection()
    try:
        Cursor = Connection.cursor()

        Tables = [
            ("transcodeattempts", "filepath", "filepath_deprecated"),
            ("transcodefiles", "filepath", "filepath_deprecated"),
            ("problemfiles", "filepath", "filepath_deprecated"),
        ]

        print("Renaming FilePath columns to FilePath_Deprecated...")
        for TableName, OldName, NewName in Tables:
            RenameColumn(Cursor, TableName, OldName, NewName)

        Connection.commit()
        print("Done. Columns renamed successfully.")
    except Exception as e:
        Connection.rollback()
        print(f"Error: {e}")
        raise
    finally:
        Connection.close()


if __name__ == "__main__":
    Main()
