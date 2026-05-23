"""Add a CHECK constraint on MediaFiles.FilePath that rejects values with
consecutive separators anywhere except the leading UNC marker (`\\\\`).

Run after BackfillMalformedFilePaths so existing rows already match the
constraint. After this lands, any future scanner that emits a malformed
path will fail loudly at INSERT/UPDATE rather than silently corrupting
the column.

Idempotent: re-runs are no-ops when the constraint already exists.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


CONSTRAINT_NAME = 'mediafiles_filepath_no_double_separator'

# Skip the first character so the leading '\' of a UNC path is allowed
# (UNC starts with two backslashes, the second is at position 2 in 1-based
# substring terms). Use position() with chr(92) to avoid POSIX regex
# backslash-escaping ambiguity.
CHECK_SQL = (
    "ALTER TABLE MediaFiles "
    f"ADD CONSTRAINT {CONSTRAINT_NAME} "
    "CHECK ("
    "FilePath IS NULL OR ("
    "position((chr(92) || chr(92)) IN SUBSTRING(FilePath FROM 2)) = 0 "
    "AND position('//' IN SUBSTRING(FilePath FROM 2)) = 0"
    ")"
    ")"
)
DROP_SQL = f"ALTER TABLE MediaFiles DROP CONSTRAINT IF EXISTS {CONSTRAINT_NAME}"


def Main():
    Db = DatabaseService()
    Db.ExecuteNonQuery(DROP_SQL)

    Violators = Db.ExecuteQuery(
        "SELECT COUNT(*) AS N FROM MediaFiles "
        "WHERE FilePath IS NOT NULL AND ("
        "position((chr(92) || chr(92)) IN SUBSTRING(FilePath FROM 2)) > 0 "
        "OR position('//' IN SUBSTRING(FilePath FROM 2)) > 0"
        ")"
    )[0]['N']
    if Violators:
        print(
            f"REFUSING to add constraint -- {Violators} existing rows would violate it.\n"
            f"Run BackfillMalformedFilePaths.py first."
        )
        return 1

    Db.ExecuteNonQuery(CHECK_SQL)
    print(f"Added CHECK constraint {CONSTRAINT_NAME} on MediaFiles.FilePath.")
    return 0


if __name__ == "__main__":
    raise SystemExit(Main())
