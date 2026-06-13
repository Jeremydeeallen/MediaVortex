import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


SEEDS = [
    ('StaleProgressThresholdSec', '15', 'int',
     'Activity dashboard: TranscodeProgress samples older than this render FPS/Speed as `--`. see activity-dashboard-solid.C2'),
    ('HeartbeatStaleThresholdSec', '300', 'int',
     'Activity dashboard: Worker connectivity dot turns red beyond this many seconds since LastHeartbeat (activity-dashboard-solid C5).'),
]


# directive: activity-dashboard-solid | # see activity-dashboard-solid.C13
def Main():
    """Idempotent seed of activity-dashboard SystemSettings rows. Adds UNIQUE(SettingKey) first so ON CONFLICT works -- pre-checked zero duplicates."""
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
    print("Seeded " + str(len(SEEDS)) + " SystemSettings row(s); unique-key index ensured.")
    print("Rollback (2 statements):")
    print("  DELETE FROM SystemSettings WHERE SettingKey IN ('StaleProgressThresholdSec','HeartbeatStaleThresholdSec');")
    print("  DROP INDEX IF EXISTS ux_systemsettings_settingkey;")
    return 0


if __name__ == "__main__":
    raise SystemExit(Main())
