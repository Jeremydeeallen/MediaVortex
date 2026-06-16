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
    "TargetIntegratedLufs REAL NOT NULL DEFAULT -23.0, "
    "TargetTruePeakDbtp REAL NOT NULL DEFAULT -2.0, "
    "TargetLra REAL, "
    "LoudnessTolerance REAL NOT NULL DEFAULT 4.0, "
    "EmitTracks JSONB NOT NULL, "
    "UngainablePolicy TEXT NOT NULL DEFAULT 'adaptive', "
    "LanguageKeepPolicy JSONB, "
    "KeepCommentaryTracks BOOLEAN NOT NULL DEFAULT TRUE, "
    "EnableSpeechLanguageDetection BOOLEAN NOT NULL DEFAULT FALSE, "
    "AudioDelayMs INTEGER NOT NULL DEFAULT 0, "
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
    {
        "Label": "Original",
        "TargetLufs": -23.0,
        "TargetLra": None,
        "Channels": "source",
        "Codec": "eac3",
        "Bitrate": 384,
        "SampleRateHz": 48000,
        "BitDepth": 16,
        "LanguageFilter": "keep-all",
        "IsDefaultTrack": False,
    },
    {
        "Label": "Dialog Boost",
        "TargetLufs": -23.0,
        "TargetLra": 11.0,
        "Channels": "source",
        "Codec": "eac3",
        "Bitrate": 384,
        "SampleRateHz": 48000,
        "BitDepth": 16,
        "LanguageFilter": "keep-all",
        "IsDefaultTrack": True,
    },
]

INSERT_GLOBAL_SQL = (
    "INSERT INTO AudioNormalizationConfig ("
    "Scope, ScopeKey, Enabled, "
    "TargetIntegratedLufs, TargetTruePeakDbtp, TargetLra, LoudnessTolerance, "
    "EmitTracks, UngainablePolicy, LanguageKeepPolicy, "
    "KeepCommentaryTracks, EnableSpeechLanguageDetection, AudioDelayMs"
    ") VALUES ("
    "'global', NULL, TRUE, "
    "-23.0, -2.0, NULL, 4.0, "
    "%s::jsonb, 'adaptive', NULL, "
    "TRUE, FALSE, 0"
    ") ON CONFLICT DO NOTHING"
)


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C9
def Main():
    """Idempotent migration: AudioNormalizationConfig table + UNIQUE scope index + global default row."""
    Db = DatabaseService()
    Db.ExecuteNonQuery(CREATE_TABLE_SQL)
    Db.ExecuteNonQuery(CREATE_UNIQUE_INDEX_SQL)
    Db.ExecuteNonQuery(INSERT_GLOBAL_SQL, (json.dumps(GLOBAL_EMIT_TRACKS),))
    print("AudioNormalizationConfig table + UNIQUE index + global default present.")
    print("Rollback (1 statement): DROP TABLE IF EXISTS AudioNormalizationConfig;")
    return 0


if __name__ == "__main__":
    raise SystemExit(Main())
