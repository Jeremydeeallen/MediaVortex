#!/usr/bin/env python3
"""
AddAudioFixPriorityHints.py
Phase 2.8 migration for media-tabs-and-loudness.feature.md (criteria 21-22).

Creates the AudioFixPriorityHints table -- operator-pinned folder patterns
that boost the queue priority of AudioFix-mode rows whose FilePath matches.

Schema:
  Id              SERIAL PK
  FolderPattern   TEXT NOT NULL UNIQUE   -- substring matched against
                                            MediaFiles.FilePath (e.g. 'Westworld',
                                            'T:\\Movies', '/Season 1')
  BoostedPriority INTEGER NOT NULL DEFAULT 195
                  CHECK 195-200 -- the manual-override priority band per
                                   queue-priority.feature.md
  CreatedAt       TIMESTAMP DEFAULT NOW()
  Description     TEXT NULLABLE -- operator's note for the pin (optional)

Idempotent.
"""

import os
import psycopg2


def GetConnection():
    return psycopg2.connect(
        host=os.environ.get('MEDIAVORTEX_DB_HOST', 'localhost'),
        port=int(os.environ.get('MEDIAVORTEX_DB_PORT', '5432')),
        database=os.environ.get('MEDIAVORTEX_DB_NAME', 'mediavortex'),
        user=os.environ.get('MEDIAVORTEX_DB_USER', 'mediavortex'),
        password=os.environ.get('MEDIAVORTEX_DB_PASSWORD', 'mediavortex'),
    )


def TableExists(Cursor, TableName):
    Cursor.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = %s AND table_schema = current_schema()",
        (TableName.lower(),),
    )
    return Cursor.fetchone() is not None


def RunMigration():
    Conn = GetConnection()
    Cur = Conn.cursor()
    try:
        if TableExists(Cur, 'AudioFixPriorityHints'):
            print("AudioFixPriorityHints already exists -- skipping CREATE")
        else:
            print("Creating AudioFixPriorityHints table...")
            Cur.execute(
                """
                CREATE TABLE AudioFixPriorityHints (
                    Id              SERIAL PRIMARY KEY,
                    FolderPattern   TEXT NOT NULL UNIQUE,
                    BoostedPriority INTEGER NOT NULL DEFAULT 195
                                    CHECK (BoostedPriority BETWEEN 195 AND 200),
                    CreatedAt       TIMESTAMP NOT NULL DEFAULT NOW(),
                    Description     TEXT
                )
                """
            )
            Conn.commit()
            print("  done.")

        Cur.execute("SELECT COUNT(*) FROM AudioFixPriorityHints")
        print(f"\nAudioFixPriorityHints rows: {Cur.fetchone()[0]}")
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
