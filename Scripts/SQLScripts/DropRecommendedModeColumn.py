import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def Run():
    DB = DatabaseService()
    DB.ExecuteNonQuery("ALTER TABLE MediaFiles DROP COLUMN IF EXISTS RecommendedMode")
    Rows = DB.ExecuteQuery(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'mediafiles' AND column_name = 'recommendedmode'"
    )
    if Rows:
        print("MediaFiles.RecommendedMode STILL PRESENT -- drop failed")
    else:
        print("MediaFiles.RecommendedMode dropped (or already absent)")


if __name__ == '__main__':
    Run()
