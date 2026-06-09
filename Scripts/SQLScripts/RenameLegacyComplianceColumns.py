import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def Run():
    """Rename legacy compliance columns to *_legacy as a forcing function for caller discovery; rollback via RollbackRenameLegacyComplianceColumns.py is one ALTER each."""
    DB = DatabaseService()

    Renames = (
        ('mediafiles', 'recommendedmode', 'RecommendedMode_legacy', 'ALTER TABLE MediaFiles RENAME COLUMN RecommendedMode TO RecommendedMode_legacy'),
        ('mediafiles', 'needstranscode', 'NeedsTranscode_legacy', 'ALTER TABLE MediaFiles RENAME COLUMN NeedsTranscode TO NeedsTranscode_legacy'),
        ('mediafiles', 'needsquick', 'NeedsQuick_legacy', 'ALTER TABLE MediaFiles RENAME COLUMN NeedsQuick TO NeedsQuick_legacy'),
    )

    for TableName, OldColumnLower, NewColumnPretty, AlterSql in Renames:
        Existing = DB.ExecuteQuery(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s AND LOWER(column_name) IN (%s, %s)",
            (TableName, OldColumnLower, NewColumnPretty.lower()),
        )
        Present = {R['column_name'].lower() for R in Existing}
        if OldColumnLower in Present and NewColumnPretty.lower() not in Present:
            DB.ExecuteNonQuery(AlterSql)
            print(f"  RENAMED {TableName}.{OldColumnLower} -> {NewColumnPretty}")
        elif NewColumnPretty.lower() in Present and OldColumnLower not in Present:
            print(f"  already renamed: {TableName}.{NewColumnPretty}")
        elif OldColumnLower in Present and NewColumnPretty.lower() in Present:
            print(f"  BOTH present (manual cleanup needed): {TableName}.{OldColumnLower} + .{NewColumnPretty}")
        else:
            print(f"  NEITHER present: {TableName}.{OldColumnLower} / .{NewColumnPretty} -- skipping")

    IndexRenames = (
        ('idx_mediafiles_needs_transcode', 'idx_mediafiles_needs_transcode_legacy'),
        ('idx_mediafiles_needs_quick', 'idx_mediafiles_needs_quick_legacy'),
    )

    for OldIdx, NewIdx in IndexRenames:
        Existing = DB.ExecuteQuery(
            "SELECT indexname FROM pg_indexes WHERE tablename = 'mediafiles' AND indexname IN (%s, %s)",
            (OldIdx, NewIdx),
        )
        Present = {R['indexname'] for R in Existing}
        if OldIdx in Present and NewIdx not in Present:
            DB.ExecuteNonQuery("ALTER INDEX " + OldIdx + " RENAME TO " + NewIdx)
            print(f"  RENAMED index {OldIdx} -> {NewIdx}")
        elif NewIdx in Present and OldIdx not in Present:
            print(f"  already renamed: {NewIdx}")
        else:
            print(f"  index neither / both present: {OldIdx} / {NewIdx} -- skipping")

    AfterRows = DB.ExecuteQuery(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'mediafiles' AND LOWER(column_name) IN ('recommendedmode', 'needstranscode', 'needsquick', 'recommendedmode_legacy', 'needstranscode_legacy', 'needsquick_legacy') ORDER BY column_name"
    )
    print("")
    print("Post-state MediaFiles columns matching legacy / _legacy:")
    for R in AfterRows:
        print("  " + R['column_name'])


if __name__ == '__main__':
    Run()
