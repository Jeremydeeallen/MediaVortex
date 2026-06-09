import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def Run():
    """Seed SystemSettings fallbacks used by the pipeline test harness (R4 replacements for MEDIAVORTEX_WORKER_NAME + FFMPEG_PATH env vars); also ensures SettingKey unique constraint."""
    DB = DatabaseService()
    DB.ExecuteNonQuery(
        "DELETE FROM SystemSettings WHERE Id NOT IN ("
        "SELECT MIN(Id) FROM SystemSettings GROUP BY SettingKey)"
    )
    DB.ExecuteNonQuery(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_systemsettings_settingkey ON SystemSettings (SettingKey)"
    )
    DB.ExecuteNonQuery(
        "INSERT INTO SystemSettings (SettingKey, SettingValue, Description, DataType, LastModified) "
        "VALUES ('DefaultTestWorkerName', 'I9-2024', 'Worker name used by Tests/Pipeline fixtures when WorkerContext is not initialized.', 'string', NOW()) "
        "ON CONFLICT (SettingKey) DO NOTHING"
    )
    DB.ExecuteNonQuery(
        "INSERT INTO SystemSettings (SettingKey, SettingValue, Description, DataType, LastModified) "
        "VALUES ('DefaultTestFFmpegPath', '', 'ffmpeg binary path used by Tests/Pipeline assertions when WorkerContext lacks FFmpegPath; empty means fail-fast.', 'string', NOW()) "
        "ON CONFLICT (SettingKey) DO NOTHING"
    )
    Rows = DB.ExecuteQuery(
        "SELECT SettingKey, SettingValue FROM SystemSettings "
        "WHERE SettingKey IN ('DefaultTestWorkerName', 'DefaultTestFFmpegPath') "
        "ORDER BY SettingKey"
    )
    for R in Rows:
        print(R['SettingKey'] + "=" + str(R['SettingValue']))


if __name__ == '__main__':
    Run()
