import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


# from: Features/Admin/Workers/admin-workers.feature.md
SEEDS = [
    ('HungEncodeThresholdSec', '600', 'int',
     'Hung-encode detector: RuntimeState=Encoding on same AttemptId for > N seconds with stale TranscodeProgress = auto-reset. see admin-workers.C9'),
]


# directive: worker-runtime-state
def Main():
    """Idempotent seed of HungEncodeThresholdSec for the hung-encode detector."""
    Db = DatabaseService()
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
    print("Seeded " + str(len(SEEDS)) + " SystemSettings row(s).")
    print("Rollback:")
    print("  DELETE FROM SystemSettings WHERE SettingKey = 'HungEncodeThresholdSec';")
    return 0


if __name__ == "__main__":
    raise SystemExit(Main())
