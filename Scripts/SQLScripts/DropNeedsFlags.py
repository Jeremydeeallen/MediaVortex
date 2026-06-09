import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C22
def Run():
    DB = DatabaseService()
    DB.ExecuteNonQuery("DROP INDEX IF EXISTS idx_mediafiles_needs_quick")
    DB.ExecuteNonQuery("DROP INDEX IF EXISTS idx_mediafiles_needs_transcode")
    DB.ExecuteNonQuery("ALTER TABLE MediaFiles DROP COLUMN IF EXISTS NeedsQuick")
    DB.ExecuteNonQuery("ALTER TABLE MediaFiles DROP COLUMN IF EXISTS NeedsTranscode")
    Rows = DB.ExecuteQuery(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'mediafiles' AND column_name IN ('needsquick', 'needstranscode')"
    )
    if Rows:
        print("MediaFiles still has: " + ", ".join(R['column_name'] for R in Rows))
    else:
        print("MediaFiles.NeedsQuick + NeedsTranscode dropped (or already absent); paired indexes also dropped")


if __name__ == '__main__':
    Run()
