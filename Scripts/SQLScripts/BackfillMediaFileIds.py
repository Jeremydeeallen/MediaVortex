#!/usr/bin/env python3
"""
BackfillMediaFileIds.py
Backfill MediaFileId in child tables from MediaFiles via case-insensitive FilePath join.

Reports rows backfilled and orphans (rows with no matching MediaFiles record).

Safe to run multiple times (only updates rows where MediaFileId IS NULL).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


CHILD_TABLES = [
    'TranscodeFiles',
    'TranscodeAttempts',
    'TranscodeQueue',
    'CompliantFiles',
    'ProblemFiles',
]


def Main():
    DB = DatabaseService()

    TotalBackfilled = 0
    TotalOrphans = 0

    for Table in CHILD_TABLES:
        # Check if table and column exist
        CheckQuery = """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s AND column_name = 'mediafileid'
        """
        Result = DB.ExecuteQuery(CheckQuery, (Table.lower(),))
        if not Result:
            print(f"[SKIP] {Table} does not have MediaFileId column")
            continue

        # Backfill MediaFileId from MediaFiles via case-insensitive FilePath match
        BackfillQuery = f"""
            UPDATE {Table} child
            SET MediaFileId = mf.Id
            FROM MediaFiles mf
            WHERE LOWER(child.FilePath) = LOWER(mf.FilePath)
              AND child.MediaFileId IS NULL
        """
        BackfilledCount = DB.ExecuteNonQuery(BackfillQuery)
        TotalBackfilled += BackfilledCount
        print(f"[OK] {Table}: backfilled {BackfilledCount} rows")

        # Count orphans (rows where no matching MediaFiles record exists)
        OrphanQuery = f"""
            SELECT COUNT(*) AS OrphanCount
            FROM {Table} child
            WHERE child.MediaFileId IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM MediaFiles mf
                  WHERE LOWER(mf.FilePath) = LOWER(child.FilePath)
              )
        """
        OrphanResult = DB.ExecuteQuery(OrphanQuery)
        OrphanCount = OrphanResult[0]['orphancount'] if OrphanResult else 0
        TotalOrphans += OrphanCount
        if OrphanCount > 0:
            print(f"[WARN] {Table}: {OrphanCount} orphan rows (no matching MediaFiles record)")

        # Count remaining NULLs (could be orphans or rows not yet matched)
        NullQuery = f"SELECT COUNT(*) AS NullCount FROM {Table} WHERE MediaFileId IS NULL"
        NullResult = DB.ExecuteQuery(NullQuery)
        NullCount = NullResult[0]['nullcount'] if NullResult else 0
        if NullCount > 0:
            print(f"[INFO] {Table}: {NullCount} rows still have NULL MediaFileId")

    print(f"\nTotal backfilled: {TotalBackfilled}")
    print(f"Total orphans: {TotalOrphans}")


if __name__ == '__main__':
    print("MediaVortex Surrogate Key Migration - Backfill MediaFileIds")
    print("=" * 60)
    Main()
