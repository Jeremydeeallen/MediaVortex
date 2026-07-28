import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


CREATE_TABLE_SQL = (
    "CREATE TABLE IF NOT EXISTS MediaFileLanguageDetections ("
    "MediaFileId BIGINT NOT NULL REFERENCES MediaFiles(Id) ON DELETE CASCADE, "
    "StreamIndex INTEGER NOT NULL, "
    "Language TEXT NOT NULL, "
    "Confidence NUMERIC(5,4) NOT NULL, "
    "DetectedAt TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
    "BackendName TEXT NOT NULL, "
    "PRIMARY KEY (MediaFileId, StreamIndex)"
    ")"
)

CREATE_LOOKUP_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS ix_mediafilelangdet_language "
    "ON MediaFileLanguageDetections (Language)"
)

WORKERS_COLUMN_SQL = (
    "ALTER TABLE Workers ADD COLUMN IF NOT EXISTS LanguageEnabled BOOLEAN NOT NULL DEFAULT FALSE"
)

SYSTEM_SETTING_SQL = (
    "INSERT INTO SystemSettings (SettingKey, SettingValue, DataType, Description) "
    "VALUES (%s, %s, %s, %s) ON CONFLICT (SettingKey) DO NOTHING"
)

DROP_LEGACY_COLUMN_SQL = (
    "ALTER TABLE MediaFiles DROP COLUMN IF EXISTS AudioStreamLanguageDetectionsJson"
)


# directive: audio-language-detection
def Main():
    Db = DatabaseService()
    Db.ExecuteNonQuery(CREATE_TABLE_SQL)
    Db.ExecuteNonQuery(CREATE_LOOKUP_INDEX_SQL)
    Db.ExecuteNonQuery(WORKERS_COLUMN_SQL)
    Db.ExecuteNonQuery(
        SYSTEM_SETTING_SQL,
        ('MinDetectionConfidence', '0.85', 'float',
         'Whisper confidence threshold; English detections at or above this stamp the container.'),
    )
    Db.ExecuteNonQuery(DROP_LEGACY_COLUMN_SQL)
    print("MediaFileLanguageDetections + Workers.LanguageEnabled + MinDetectionConfidence present. Legacy AudioStreamLanguageDetectionsJson dropped.")
    return 0


if __name__ == '__main__':
    raise SystemExit(Main())
