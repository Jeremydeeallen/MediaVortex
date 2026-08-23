# directive: dialog-boost-marker-unify | # see dialog-boost-marker-unify.C1
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


# directive: dialog-boost-marker-unify
def Main():
    Db = DatabaseService()
    Db.ExecuteNonQuery(
        "ALTER TABLE TranscodeAttempts "
        "ADD COLUMN IF NOT EXISTS DialogBoostEmitted BOOL NOT NULL DEFAULT FALSE"
    )
    Rows = Db.ExecuteQuery(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'transcodeattempts' AND column_name = 'dialogboostemitted'"
    )
    if not Rows:
        raise RuntimeError("DialogBoostEmitted column not present after ALTER")
    FlagCount = Db.ExecuteNonQuery(
        "UPDATE TranscodeAttempts SET DialogBoostEmitted = TRUE "
        "WHERE AudioTracksEmittedJson IS NOT NULL "
        "AND (AudioTracksEmittedJson::jsonb @> %s::jsonb "
        "     OR AudioTracksEmittedJson::jsonb @> %s::jsonb)",
        ('[{"dialog_boost_emitted": true}]', '[{"Label": "Dialog Boost"}]'),
    )
    print(f"Applied. DialogBoostEmitted column present. Backfilled attempts: {FlagCount}")


if __name__ == '__main__':
    Main()
