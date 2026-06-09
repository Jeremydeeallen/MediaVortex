import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C24
def Run():
    DB = DatabaseService()

    DB.ExecuteNonQuery(
        "CREATE INDEX IF NOT EXISTS idx_mediafiles_wb_transcode "
        "ON MediaFiles (SizeMB DESC NULLS LAST) "
        "WHERE WorkBucket = 'Transcode' AND HasExplicitEnglishAudio IS NOT FALSE"
    )
    DB.ExecuteNonQuery(
        "CREATE INDEX IF NOT EXISTS idx_mediafiles_wb_remux "
        "ON MediaFiles (SizeMB DESC NULLS LAST) "
        "WHERE WorkBucket = 'Remux' AND HasExplicitEnglishAudio IS NOT FALSE"
    )
    DB.ExecuteNonQuery(
        "CREATE INDEX IF NOT EXISTS idx_mediafiles_wb_audiofix "
        "ON MediaFiles (SizeMB DESC NULLS LAST) "
        "WHERE WorkBucket = 'AudioFixOnly' AND HasExplicitEnglishAudio IS NOT FALSE"
    )
    DB.ExecuteNonQuery(
        "CREATE INDEX IF NOT EXISTS idx_mediafiles_wb_subtitlefix "
        "ON MediaFiles (SizeMB DESC NULLS LAST) "
        "WHERE WorkBucket = 'SubtitleFixOnly' AND HasExplicitEnglishAudio IS NOT FALSE"
    )

    Rows = DB.ExecuteQuery(
        "SELECT indexname FROM pg_indexes WHERE tablename = 'mediafiles' "
        "AND indexname LIKE 'idx_mediafiles_wb_%%' ORDER BY indexname"
    )
    print("WorkBucket partial indexes present:")
    for Row in Rows:
        print("  " + Row['indexname'])


if __name__ == '__main__':
    Run()
