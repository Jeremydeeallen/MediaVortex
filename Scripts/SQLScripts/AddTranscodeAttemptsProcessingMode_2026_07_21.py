# directive: e2e-bug-fixes | # see e2e-bug-fixes.C29
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


def Main():
    Db = DatabaseService()
    Db.ExecuteNonQuery(
        "ALTER TABLE TranscodeAttempts ADD COLUMN IF NOT EXISTS ProcessingMode TEXT"
    )
    Affected = Db.ExecuteNonQuery(
        "UPDATE TranscodeAttempts ta SET ProcessingMode = tq.ProcessingMode "
        "FROM TranscodeQueue tq WHERE tq.MediaFileId = ta.MediaFileId "
        "AND ta.ProcessingMode IS NULL AND tq.ProcessingMode IS NOT NULL"
    )
    Nulls = Db.ExecuteQuery(
        "SELECT COUNT(*) AS n FROM TranscodeAttempts WHERE ProcessingMode IS NULL"
    )
    NullCount = Nulls[0].get('n') if Nulls else 0
    print(f"Applied. Backfilled {Affected} rows from TranscodeQueue.")
    print(f"Rows still NULL (queue row already deleted for these historical attempts): {NullCount}")


if __name__ == '__main__':
    Main()
