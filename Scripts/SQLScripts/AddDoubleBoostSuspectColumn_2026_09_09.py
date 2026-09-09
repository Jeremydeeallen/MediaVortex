# directive: dialog-boost-emission-integrity | # see .claude/directive.md C3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


# directive: dialog-boost-emission-integrity | # see .claude/directive.md C3
def Main():
    Db = DatabaseService()
    Db.ExecuteNonQuery(
        "ALTER TABLE MediaFiles "
        "ADD COLUMN IF NOT EXISTS HasDoubleBoostSuspect BOOL NOT NULL DEFAULT FALSE"
    )
    Rows = Db.ExecuteQuery(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'mediafiles' AND column_name = 'hasdoubleboostsuspect'"
    )
    if not Rows:
        raise RuntimeError("HasDoubleBoostSuspect column not present after ALTER")
    Snapshot = Db.ExecuteQuery(
        "SELECT COUNT(DISTINCT MediaFileId) AS n "
        "FROM TranscodeAttempts "
        "WHERE Success = TRUE AND DialogBoostEmitted = TRUE "
        "AND ffpmpegcommand ILIKE %s",
        ('%-mv.mp4"%',),
    )
    ExpectedCount = int((Snapshot[0] or {}).get('n') or 0) if Snapshot else 0
    Db.ExecuteNonQuery(
        "UPDATE MediaFiles SET HasDoubleBoostSuspect = TRUE WHERE Id IN ("
        "  SELECT DISTINCT MediaFileId FROM TranscodeAttempts "
        "  WHERE Success = TRUE AND DialogBoostEmitted = TRUE "
        "  AND ffpmpegcommand ILIKE %s"
        ")",
        ('%-mv.mp4"%',),
    )
    Post = Db.ExecuteQuery("SELECT COUNT(*) AS n FROM MediaFiles WHERE HasDoubleBoostSuspect = TRUE")
    FlaggedCount = int((Post[0] or {}).get('n') or 0) if Post else 0
    print(f"Applied. HasDoubleBoostSuspect column present. Pre-migration snapshot: {ExpectedCount} distinct MediaFileIds. Post-backfill flagged: {FlaggedCount}.")
    if FlaggedCount < ExpectedCount:
        raise RuntimeError(
            f"backfill undercount: expected {ExpectedCount} flagged rows, got {FlaggedCount}"
        )


if __name__ == '__main__':
    Main()
