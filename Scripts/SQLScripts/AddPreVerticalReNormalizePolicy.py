import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


ADD_COLUMN_SQL = (
    "ALTER TABLE AudioNormalizationConfig "
    "ADD COLUMN IF NOT EXISTS PreVerticalReNormalizePolicy TEXT NOT NULL DEFAULT 'lazy'"
)


ADD_CHECK_SQL = (
    "ALTER TABLE AudioNormalizationConfig "
    "DROP CONSTRAINT IF EXISTS preverticalrenormalizepolicy_check; "
    "ALTER TABLE AudioNormalizationConfig "
    "ADD CONSTRAINT preverticalrenormalizepolicy_check "
    "CHECK (PreVerticalReNormalizePolicy IN ('aggressive', 'lazy', 'none'))"
)


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.O2
def Main():
    """Idempotent migration: PreVerticalReNormalizePolicy column on AudioNormalizationConfig."""
    Db = DatabaseService()
    Db.ExecuteNonQuery(ADD_COLUMN_SQL)
    Db.ExecuteNonQuery(ADD_CHECK_SQL)
    print("AudioNormalizationConfig.PreVerticalReNormalizePolicy column + check constraint present.")
    print("Rollback: ALTER TABLE AudioNormalizationConfig DROP COLUMN IF EXISTS PreVerticalReNormalizePolicy;")
    return 0


if __name__ == "__main__":
    raise SystemExit(Main())
