import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def Run():
    """Rollback the RenameLegacyComplianceColumns rename -- restores original column + index names."""
    DB = DatabaseService()

    Rollbacks = (
        ('mediafiles', 'recommendedmode_legacy', 'RecommendedMode', 'ALTER TABLE MediaFiles RENAME COLUMN RecommendedMode_legacy TO RecommendedMode'),
        ('mediafiles', 'needstranscode_legacy', 'NeedsTranscode', 'ALTER TABLE MediaFiles RENAME COLUMN NeedsTranscode_legacy TO NeedsTranscode'),
        ('mediafiles', 'needsquick_legacy', 'NeedsQuick', 'ALTER TABLE MediaFiles RENAME COLUMN NeedsQuick_legacy TO NeedsQuick'),
    )

    for TableName, OldColumnLower, NewColumnPretty, AlterSql in Rollbacks:
        Existing = DB.ExecuteQuery(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s AND LOWER(column_name) IN (%s, %s)",
            (TableName, OldColumnLower, NewColumnPretty.lower()),
        )
        Present = {R['column_name'].lower() for R in Existing}
        if OldColumnLower in Present and NewColumnPretty.lower() not in Present:
            DB.ExecuteNonQuery(AlterSql)
            print(f"  ROLLED BACK {TableName}.{OldColumnLower} -> {NewColumnPretty}")
        elif NewColumnPretty.lower() in Present and OldColumnLower not in Present:
            print(f"  already rolled back: {TableName}.{NewColumnPretty}")
        else:
            print(f"  state unclear: {TableName}.{OldColumnLower} / .{NewColumnPretty} -- skipping")

    IndexRollbacks = (
        ('idx_mediafiles_needs_transcode_legacy', 'idx_mediafiles_needs_transcode'),
        ('idx_mediafiles_needs_quick_legacy', 'idx_mediafiles_needs_quick'),
    )

    for OldIdx, NewIdx in IndexRollbacks:
        Existing = DB.ExecuteQuery(
            "SELECT indexname FROM pg_indexes WHERE tablename = 'mediafiles' AND indexname IN (%s, %s)",
            (OldIdx, NewIdx),
        )
        Present = {R['indexname'] for R in Existing}
        if OldIdx in Present and NewIdx not in Present:
            DB.ExecuteNonQuery("ALTER INDEX " + OldIdx + " RENAME TO " + NewIdx)
            print(f"  ROLLED BACK index {OldIdx} -> {NewIdx}")
        elif NewIdx in Present and OldIdx not in Present:
            print(f"  already rolled back: {NewIdx}")
        else:
            print(f"  index state unclear: {OldIdx} / {NewIdx} -- skipping")


if __name__ == '__main__':
    Run()
