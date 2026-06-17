import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


ADD_COLUMN_SQL = (
    "ALTER TABLE AudioNormalizationConfig "
    "ADD COLUMN IF NOT EXISTS LanguageDefault TEXT NOT NULL DEFAULT 'eng'"
)


# directive: audio-vertical-live-encode-gaps | # see audio-normalization.C11
def Main():
    """Idempotent migration: AudioNormalizationConfig.LanguageDefault for und fallback (L4)."""
    Db = DatabaseService()
    Db.ExecuteNonQuery(ADD_COLUMN_SQL)
    print("AudioNormalizationConfig.LanguageDefault present (default 'eng').")
    print("Rollback: ALTER TABLE AudioNormalizationConfig DROP COLUMN LanguageDefault;")
    return 0


if __name__ == "__main__":
    raise SystemExit(Main())
