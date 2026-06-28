# directive: work-transcode-unified -- rename SmartPopulate index to deprecated marker; drop deferred to soak.
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: work-transcode-unified | # see work-bucket.C15
def IndexExists(DB, Name):
    Rows = DB.ExecuteQuery(
        "SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname=%s",
        (Name.lower(),),
    )
    return len(Rows) > 0


# directive: work-transcode-unified | # see work-bucket.C15
def RunMigration():
    DB = DatabaseService()
    Original = 'idx_mediafiles_smartpopulate'
    Deprecated = 'idx_mediafiles_smartpopulate_deprecated_2026_06_28'
    if IndexExists(DB, Deprecated):
        print("Already deprecated -- nothing to do.")
        return
    if not IndexExists(DB, Original):
        print("Original index absent and no deprecated marker -- nothing to do.")
        return
    print(f"ALTER INDEX {Original} RENAME TO {Deprecated}")
    DB.ExecuteNonQuery(f"ALTER INDEX {Original} RENAME TO {Deprecated}")
    print("Done.")


if __name__ == '__main__':
    RunMigration()
