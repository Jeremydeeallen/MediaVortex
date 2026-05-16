"""Add Version + BuildInfo columns to Workers table.

`Version` (nullable VARCHAR(64)): the git commit SHA the worker process
was built / started from. NULL renders as "unknown" in the UI.

`BuildInfo` (nullable TEXT): the full /opt/mediavortex/BUILD_INFO file
contents (commit, built_at, built_by lines) for Docker workers, or NULL
for non-Docker workers without the file.

Idempotent -- safe to run multiple times.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


def Run():
    DB = DatabaseService()
    DB.ExecuteNonQuery("ALTER TABLE Workers ADD COLUMN IF NOT EXISTS Version VARCHAR(64)")
    DB.ExecuteNonQuery("ALTER TABLE Workers ADD COLUMN IF NOT EXISTS BuildInfo TEXT")
    print("Added Version (VARCHAR(64)) and BuildInfo (TEXT) columns to Workers")


if __name__ == '__main__':
    Run()
