import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


# from: Features/SystemSettings/SystemSettings.feature.md
SEEDS = [
    ('FfmpegLogLevel', 'error', 'string',
     'ffmpeg -loglevel value; suppresses warning floods that fill stderr pipe. Values: quiet|fatal|error|warning|info|verbose|debug. see systemsettings.C14'),
]


# directive: ffmpeg-stderr-deadlock
def Main():
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
    print("  DELETE FROM SystemSettings WHERE SettingKey = 'FfmpegLogLevel';")
    return 0


if __name__ == "__main__":
    raise SystemExit(Main())
