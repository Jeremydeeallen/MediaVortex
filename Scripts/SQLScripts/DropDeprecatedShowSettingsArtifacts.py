#!/usr/bin/env python3

# directive: work-transcode-unified | DESTRUCTIVE operator migration -- see spec C15 and Docs/superpowers/specs/2026-06-28-work-transcode-unified-design.md
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: work-transcode-unified | # see work-bucket.C15
def RunMigration():
    DB = DatabaseService()
    print("DROP INDEX IF EXISTS idx_mediafiles_smartpopulate_deprecated_2026_06_28")
    DB.ExecuteNonQuery("DROP INDEX IF EXISTS idx_mediafiles_smartpopulate_deprecated_2026_06_28")
    print("DROP TABLE IF EXISTS ShowSettings_DEPRECATED_2026_06_28")
    DB.ExecuteNonQuery("DROP TABLE IF EXISTS ShowSettings_DEPRECATED_2026_06_28 CASCADE")
    print("Done.")


if __name__ == '__main__':
    Confirm = input("DESTRUCTIVE. Type 'DROP' to proceed: ")
    if Confirm != 'DROP':
        print("Aborted.")
    else:
        RunMigration()
