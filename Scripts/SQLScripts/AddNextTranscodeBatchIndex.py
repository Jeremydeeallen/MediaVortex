import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


def Run():
    DB = DatabaseService()
    IndexName = 'idx_mediafiles_next_transcode_batch'
    CreateSql = (
        "CREATE INDEX IF NOT EXISTS " + IndexName + " "
        "ON MediaFiles (SizeMB DESC NULLS LAST) "
        "WHERE NeedsTranscode = TRUE AND SizeMB > 0 AND HasExplicitEnglishAudio IS NOT FALSE"
    )
    DB.ExecuteNonQuery(CreateSql)
    print("Ensured partial index " + IndexName + " on MediaFiles (SizeMB DESC) WHERE NeedsTranscode -- supports NextTranscodeBatch")

    ExplainSql = (
        "EXPLAIN ANALYZE "
        "SELECT m.Id, m.SizeMB, COUNT(*) OVER() AS TotalCount "
        "FROM MediaFiles m "
        "WHERE m.NeedsTranscode = TRUE "
        "AND m.Id NOT IN (SELECT MediaFileId FROM TranscodeQueue WHERE MediaFileId IS NOT NULL) "
        "AND m.SizeMB > 0 "
        "AND m.HasExplicitEnglishAudio IS NOT FALSE "
        "ORDER BY m.SizeMB DESC NULLS LAST "
        "LIMIT 100"
    )
    Rows = DB.ExecuteQuery(ExplainSql)
    print("")
    print("EXPLAIN ANALYZE for NextTranscodeBatch (no Drive, no Search):")
    for Row in Rows:
        for V in Row.values():
            print("  " + str(V))


if __name__ == '__main__':
    Run()
