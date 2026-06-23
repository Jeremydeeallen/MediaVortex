import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


# from: Features/Admin/Workers/admin-workers.feature.md
SEEDS = [
    ('WorkerIntentDivergenceSec', '60', 'int',
     'Admin/Workers: amber-border divergence threshold between Workers.Status (operator intent) and Workers.RuntimeState (worker truth). see admin-workers.C6'),
]


# directive: worker-runtime-state
def Main():
    """Idempotent: adds RuntimeState + CurrentAttemptId + LastRuntimeStateUpdate worker-authored columns; seeds WorkerIntentDivergenceSec."""
    Db = DatabaseService()
    Db.ExecuteNonQuery(
        "ALTER TABLE Workers ADD COLUMN IF NOT EXISTS RuntimeState TEXT"
    )
    Db.ExecuteNonQuery(
        "ALTER TABLE Workers ADD COLUMN IF NOT EXISTS CurrentAttemptId BIGINT"
    )
    Db.ExecuteNonQuery(
        "ALTER TABLE Workers ADD COLUMN IF NOT EXISTS LastRuntimeStateUpdate TIMESTAMP"
    )
    Db.ExecuteNonQuery(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_systemsettings_settingkey ON SystemSettings (SettingKey)"
    )
    for Key, Val, DType, Desc in SEEDS:
        Db.ExecuteNonQuery(
            "INSERT INTO SystemSettings (SettingKey, SettingValue, DataType, Description) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (SettingKey) DO NOTHING",
            (Key, Val, DType, Desc),
        )
    print("Workers RuntimeState/CurrentAttemptId/LastRuntimeStateUpdate columns ensured.")
    print("Seeded " + str(len(SEEDS)) + " SystemSettings row(s).")
    print("Rollback (4 statements):")
    print("  ALTER TABLE Workers DROP COLUMN IF EXISTS RuntimeState;")
    print("  ALTER TABLE Workers DROP COLUMN IF EXISTS CurrentAttemptId;")
    print("  ALTER TABLE Workers DROP COLUMN IF EXISTS LastRuntimeStateUpdate;")
    print("  DELETE FROM SystemSettings WHERE SettingKey = 'WorkerIntentDivergenceSec';")
    return 0


if __name__ == "__main__":
    raise SystemExit(Main())
