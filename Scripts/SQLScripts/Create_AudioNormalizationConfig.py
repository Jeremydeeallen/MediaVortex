import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


CREATE_TABLE_SQL = (
    "CREATE TABLE IF NOT EXISTS AudioNormalizationConfig ("
    "Id BIGSERIAL PRIMARY KEY, "
    "Scope TEXT NOT NULL, "
    "ScopeKey TEXT, "
    "Enabled BOOLEAN NOT NULL DEFAULT TRUE, "
    "TargetLra REAL, "
    "LoudnessTolerance REAL NOT NULL DEFAULT 3.0, "
    "EmitTracks JSONB NOT NULL, "
    "UngainablePolicy TEXT NOT NULL DEFAULT 'adaptive', "
    "EnableSpeechLanguageDetection BOOLEAN NOT NULL DEFAULT FALSE, "
    "LanguageDefault TEXT NOT NULL DEFAULT 'eng', "
    "PreVerticalReNormalizePolicy TEXT NOT NULL DEFAULT 'lazy', "
    "MaxAudioChannels INTEGER NOT NULL DEFAULT 2, "
    "LastUpdated TIMESTAMP DEFAULT NOW(), "
    "CONSTRAINT audionormalizationconfig_scope_valid "
    "CHECK (Scope IN ('global', 'library', 'folder', 'item')), "
    "CONSTRAINT audionormalizationconfig_ungainable_valid "
    "CHECK (UngainablePolicy IN ('skip', 'adaptive', 'limiter', 'review')), "
    "CONSTRAINT audionormalizationconfig_scope_key_shape "
    "CHECK ((Scope = 'global' AND ScopeKey IS NULL) "
    "OR (Scope <> 'global' AND ScopeKey IS NOT NULL))"
    ")"
)

CREATE_UNIQUE_INDEX_SQL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_audionormalizationconfig_scope "
    "ON AudioNormalizationConfig (Scope, COALESCE(ScopeKey, ''))"
)

GLOBAL_EMIT_TRACKS = [
    {"Label": "Original", "LanguageFilter": "keep-all", "IsDefaultTrack": False},
    {"Label": "Dialog Boost", "LanguageFilter": "keep-all", "IsDefaultTrack": True},
]

INSERT_GLOBAL_SQL = (
    "INSERT INTO AudioNormalizationConfig ("
    "Scope, ScopeKey, Enabled, TargetLra, LoudnessTolerance, "
    "EmitTracks, UngainablePolicy, EnableSpeechLanguageDetection, "
    "LanguageDefault, PreVerticalReNormalizePolicy, MaxAudioChannels"
    ") VALUES ("
    "'global', NULL, TRUE, NULL, 4.0, "
    "%s::jsonb, 'adaptive', FALSE, 'eng', 'lazy', 8"
    ") ON CONFLICT DO NOTHING"
)


def Main():
    Db = DatabaseService()
    Db.ExecuteNonQuery(CREATE_TABLE_SQL)
    Db.ExecuteNonQuery(CREATE_UNIQUE_INDEX_SQL)
    Db.ExecuteNonQuery(INSERT_GLOBAL_SQL, (json.dumps(GLOBAL_EMIT_TRACKS),))
    print("AudioNormalizationConfig table + UNIQUE index + global default present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(Main())
