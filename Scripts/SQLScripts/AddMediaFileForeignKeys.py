#!/usr/bin/env python3
"""
AddMediaFileForeignKeys.py
Add foreign key constraints from child tables to MediaFiles.Id.

Run AFTER code deploy (separate step from column addition and backfill).

FK behavior:
- TranscodeFiles, TranscodeAttempts: ON DELETE SET NULL (preserve history)
- TranscodeQueue, CompliantFiles, ProblemFiles: ON DELETE CASCADE

Safe to run multiple times (idempotent via DO $$ exception handling).
"""

import os
import sys
import psycopg2


def GetConnection():
    """Get database connection using same env vars as Core/Database/DatabaseService.py."""
    return psycopg2.connect(
        host=os.environ.get('MEDIAVORTEX_DB_HOST', 'localhost'),
        port=int(os.environ.get('MEDIAVORTEX_DB_PORT', '5432')),
        database=os.environ.get('MEDIAVORTEX_DB_NAME', 'mediavortex'),
        user=os.environ.get('MEDIAVORTEX_DB_USER', 'mediavortex'),
        password=os.environ.get('MEDIAVORTEX_DB_PASSWORD', 'mediavortex')
    )


FK_DEFINITIONS = [
    ('TranscodeFiles', 'fk_transcodefiles_mediafileid', 'SET NULL'),
    ('TranscodeAttempts', 'fk_transcodeattempts_mediafileid', 'SET NULL'),
    ('TranscodeQueue', 'fk_transcodequeue_mediafileid', 'CASCADE'),
    ('CompliantFiles', 'fk_compliantfiles_mediafileid', 'CASCADE'),
    ('ProblemFiles', 'fk_problemfiles_mediafileid', 'CASCADE'),
]


def RunMigration():
    """Add foreign key constraints to all child tables."""
    Connection = GetConnection()
    Cursor = Connection.cursor()

    try:
        for Table, ConstraintName, OnDelete in FK_DEFINITIONS:
            # Use DO $$ block with exception handling for idempotency
            Cursor.execute(f"""
                DO $$
                BEGIN
                    ALTER TABLE {Table}
                    ADD CONSTRAINT {ConstraintName}
                    FOREIGN KEY (MediaFileId) REFERENCES MediaFiles(Id)
                    ON DELETE {OnDelete};
                    RAISE NOTICE 'Added FK constraint {ConstraintName} to {Table}';
                EXCEPTION
                    WHEN duplicate_object THEN
                        RAISE NOTICE 'FK constraint {ConstraintName} already exists on {Table}';
                    WHEN undefined_column THEN
                        RAISE NOTICE 'MediaFileId column does not exist on {Table} -- run AddMediaFileIdColumns.py first';
                END;
                $$;
            """)
            Connection.commit()
            print(f"[OK] {Table}: FK constraint {ConstraintName} (ON DELETE {OnDelete})")

        print("\nMigration completed successfully.")

    except Exception as e:
        Connection.rollback()
        print(f"[ERROR] Migration failed: {e}")
        sys.exit(1)
    finally:
        Cursor.close()
        Connection.close()


if __name__ == "__main__":
    print("MediaVortex Surrogate Key Migration - Add Foreign Keys")
    print("=" * 60)
    RunMigration()
