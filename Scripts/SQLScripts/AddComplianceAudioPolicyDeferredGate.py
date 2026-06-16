import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


ADD_COLUMN_SQL = (
    "ALTER TABLE ComplianceGates "
    "ADD COLUMN IF NOT EXISTS BlockOnAudioPolicyDeferred BOOLEAN NOT NULL DEFAULT TRUE"
)


# directive: audio-vertical-compliance-and-activity | # see audio-normalization.C12
def Main():
    """Idempotent migration: ComplianceGates.BlockOnAudioPolicyDeferred for the new audio compliance gate."""
    Db = DatabaseService()
    Db.ExecuteNonQuery(ADD_COLUMN_SQL)
    print("ComplianceGates.BlockOnAudioPolicyDeferred present.")
    print("Rollback: ALTER TABLE ComplianceGates DROP COLUMN BlockOnAudioPolicyDeferred;")
    return 0


if __name__ == "__main__":
    raise SystemExit(Main())
