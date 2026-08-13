# directive: audio-vertical-dialog-boost-enforcement | # see audio-vertical-dialog-boost-enforcement.C12
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


# directive: audio-vertical-dialog-boost-enforcement
def Main():
    Db = DatabaseService()
    Db.ExecuteNonQuery(
        "ALTER TABLE MediaFiles "
        "ADD COLUMN IF NOT EXISTS HasDialogBoostTrack BOOL NOT NULL DEFAULT FALSE"
    )
    Rows = Db.ExecuteQuery(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'mediafiles' AND column_name = 'hasdialogboosttrack'"
    )
    if not Rows:
        raise RuntimeError("HasDialogBoostTrack column not present after ALTER")
    RowCount = Db.ExecuteNonQuery(
        "UPDATE MediaFiles SET HasDialogBoostTrack = TRUE "
        "WHERE Id IN ("
        "  SELECT DISTINCT MediaFileId FROM TranscodeAttempts "
        "  WHERE Success = TRUE "
        "  AND AudioTracksEmittedJson IS NOT NULL "
        "  AND AudioTracksEmittedJson::jsonb @> %s::jsonb"
        ")",
        ('[{"dialog_boost_emitted": true}]',),
    )
    print(f"Applied. HasDialogBoostTrack column present. Backfilled rows: {RowCount}")


if __name__ == '__main__':
    Main()
