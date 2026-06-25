import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


# from: .claude/directive.md
PREFERRED_DEFAULT_LANGUAGE_RANK_DEFAULT = 'eng,en'


# directive: audio-pipeline-fail-loud
def Main():
    """Phase A: TranscodeAudioPolicyVerdicts + TranscodeAttempts.AudioPolicyResolved + SystemSettings row."""
    Db = DatabaseService()

    Db.ExecuteNonQuery(
        "CREATE TABLE IF NOT EXISTS TranscodeAudioPolicyVerdicts ("
        "Id BIGSERIAL PRIMARY KEY, "
        "TranscodeAttemptId BIGINT NOT NULL, "
        "TrackIndex INT NOT NULL, "
        "PolicyName TEXT NOT NULL, "
        "PolicyReason TEXT NOT NULL, "
        "PlanText TEXT NULL, "
        "CreatedAt TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
        "CONSTRAINT fk_tapv_attempt FOREIGN KEY (TranscodeAttemptId) REFERENCES TranscodeAttempts(Id) ON DELETE SET NULL"
        ")"
    )

    Db.ExecuteNonQuery(
        "CREATE INDEX IF NOT EXISTS ix_tapv_attempt ON TranscodeAudioPolicyVerdicts (TranscodeAttemptId)"
    )

    Db.ExecuteNonQuery(
        "ALTER TABLE TranscodeAttempts ADD COLUMN IF NOT EXISTS AudioPolicyResolved TEXT NULL"
    )

    Db.ExecuteNonQuery(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_systemsettings_settingkey ON SystemSettings (SettingKey)"
    )
    Db.ExecuteNonQuery(
        "INSERT INTO SystemSettings (SettingKey, SettingValue, DataType, Description) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT (SettingKey) DO NOTHING",
        (
            'PreferredDefaultLanguageRank',
            PREFERRED_DEFAULT_LANGUAGE_RANK_DEFAULT,
            'csv',
            'Ordered language-tag rank for the default-disposition pick. RankPreferredDefaultPolicy reads this per call. see audio-pipeline-fail-loud INV-2.',
        ),
    )

    print('TranscodeAudioPolicyVerdicts table + TranscodeAttempts.AudioPolicyResolved + SystemSettings row applied (idempotent).')
    print('Rollback:')
    print("  ALTER TABLE TranscodeAttempts DROP COLUMN IF EXISTS AudioPolicyResolved;")
    print("  DROP TABLE IF EXISTS TranscodeAudioPolicyVerdicts;")
    print("  DELETE FROM SystemSettings WHERE SettingKey = 'PreferredDefaultLanguageRank';")
    return 0


if __name__ == '__main__':
    raise SystemExit(Main())
