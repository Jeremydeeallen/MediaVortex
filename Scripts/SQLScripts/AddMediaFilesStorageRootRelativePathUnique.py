"""Add UNIQUE constraint on MediaFiles (StorageRootId, LOWER(RelativePath)).

Run AFTER DedupeMediaFilesByRelativePath.py has reduced duplicates to zero.
The constraint prevents future backslash-escape variants of the same logical
file from coexisting as distinct rows -- it is the persistence-layer half of
FileScanning.feature.md criterion 27.

Index form: expression index on LOWER(RelativePath) so the constraint is
case-insensitive (matches how ReconcileWithDisk keys the same tuple).

Idempotent via CREATE UNIQUE INDEX IF NOT EXISTS.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


def Run():
    Db = DatabaseService()

    print('=== Pre-check: duplicate groups must be zero ===')
    DupCount = Db.ExecuteQuery("""
        SELECT COUNT(*) AS c FROM (
            SELECT StorageRootId, LOWER(RelativePath)
            FROM MediaFiles
            WHERE StorageRootId IS NOT NULL AND RelativePath IS NOT NULL
            GROUP BY StorageRootId, LOWER(RelativePath)
            HAVING COUNT(*) > 1
        ) sq
    """)[0]['c']
    if DupCount > 0:
        print(f'ABORT: {DupCount} duplicate (StorageRootId, LOWER(RelativePath)) groups still exist.')
        print('       Run DedupeMediaFilesByRelativePath.py first.')
        sys.exit(1)
    print('  zero duplicates -- safe to add constraint')

    print('\n=== Creating unique index ===')
    Db.ExecuteNonQuery("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mediafiles_storageroot_relpath_unique
        ON MediaFiles (StorageRootId, LOWER(RelativePath))
        WHERE StorageRootId IS NOT NULL AND RelativePath IS NOT NULL
    """)
    print('  done')

    print('\n=== Verifying ===')
    Indexes = Db.ExecuteQuery(
        "SELECT indexdef FROM pg_indexes WHERE tablename='mediafiles' AND indexname='idx_mediafiles_storageroot_relpath_unique'"
    )
    if not Indexes:
        print('FAIL: index was not created')
        sys.exit(1)
    print(f'  {Indexes[0]["indexdef"]}')


if __name__ == '__main__':
    Run()
