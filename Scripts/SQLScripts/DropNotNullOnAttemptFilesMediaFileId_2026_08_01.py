# see probe-worker-decoupled -- MediaFileId nullable + FK ON DELETE SET NULL so parent MediaFiles delete preserves attempt history (reconcile-with-disk case where source file is gone).
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


def Run():
    Db = DatabaseService()
    Db.ExecuteNonQuery("ALTER TABLE TranscodeAttempts ALTER COLUMN MediaFileId DROP NOT NULL")
    Db.ExecuteNonQuery("ALTER TABLE TranscodeFiles ALTER COLUMN MediaFileId DROP NOT NULL")
    Db.ExecuteNonQuery("ALTER TABLE TranscodeAttempts DROP CONSTRAINT IF EXISTS fk_transcodeattempts_mediafileid")
    Db.ExecuteNonQuery(
        "ALTER TABLE TranscodeAttempts ADD CONSTRAINT fk_transcodeattempts_mediafileid "
        "FOREIGN KEY (MediaFileId) REFERENCES MediaFiles(Id) ON DELETE SET NULL"
    )
    Db.ExecuteNonQuery("ALTER TABLE TranscodeFiles DROP CONSTRAINT IF EXISTS fk_transcodefiles_mediafileid")
    Db.ExecuteNonQuery(
        "ALTER TABLE TranscodeFiles ADD CONSTRAINT fk_transcodefiles_mediafileid "
        "FOREIGN KEY (MediaFileId) REFERENCES MediaFiles(Id) ON DELETE SET NULL"
    )
    print("MediaFileId now NULLABLE + FK ON DELETE SET NULL on TranscodeAttempts + TranscodeFiles")


if __name__ == '__main__':
    Run()
