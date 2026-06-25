import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


# from: .claude/directive.md
TARGET_INTEGRATED_LUFS_DEFAULT = -24.0
TARGET_TRUE_PEAK_DBTP_DEFAULT = -2.0
MAX_OVERSHOOT_ADAPTIVE_DEFAULT = 5.0
MAX_OVERSHOOT_REVIEW_DEFAULT = 10.0
ACCEPTABLE_AUDIO_CODECS_DEFAULT = 'aac,ac3,eac3,mp3'
ENABLE_DIALOG_BOOST_DEFAULT = True
ENABLE_ENGLISH_PREFERRED_DEFAULT = True
PREFERRED_LANGUAGE_RANK_DEFAULT = 'eng,en'
ENABLE_SPEECH_LANG_DETECTION_DEFAULT = False


# directive: worker-runtime-state
def Main():
    Db = DatabaseService()

    Db.ExecuteNonQuery(
        "CREATE TABLE IF NOT EXISTS AudioComplianceRules ("
        "Id BIGINT PRIMARY KEY, "
        "TargetIntegratedLufs NUMERIC NOT NULL, "
        "TargetTruePeakDbtp NUMERIC NOT NULL, "
        "MaxOvershootDbForAdaptiveFallback NUMERIC NOT NULL, "
        "MaxOvershootDbForReview NUMERIC NOT NULL, "
        "AcceptableAudioCodecsCsv TEXT NOT NULL, "
        "EnableDialogBoostTrack BOOLEAN NOT NULL, "
        "EnableEnglishPreferredDefault BOOLEAN NOT NULL, "
        "PreferredDefaultLanguageRank TEXT NOT NULL, "
        "EnableSpeechLanguageDetection BOOLEAN NOT NULL, "
        "LastUpdated TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
        "CONSTRAINT chk_audio_compliance_rules_singleton CHECK (Id = 1)"
        ")"
    )

    PreferredFromSettings = Db.ExecuteQuery(
        "SELECT SettingValue FROM SystemSettings WHERE SettingKey = 'PreferredDefaultLanguageRank' LIMIT 1"
    )
    PreferredRank = (PreferredFromSettings[0].get('SettingValue') or PreferredFromSettings[0].get('settingvalue')) if PreferredFromSettings else PREFERRED_LANGUAGE_RANK_DEFAULT

    CodecsFromContainer = Db.ExecuteQuery(
        "SELECT AcceptableAudioCodecsCsv FROM ContainerComplianceRules ORDER BY Id LIMIT 1"
    )
    AcceptableCodecs = (CodecsFromContainer[0].get('AcceptableAudioCodecsCsv') or CodecsFromContainer[0].get('acceptableaudiocodecscsv')) if CodecsFromContainer else ACCEPTABLE_AUDIO_CODECS_DEFAULT

    Db.ExecuteNonQuery(
        "INSERT INTO AudioComplianceRules ("
        "Id, TargetIntegratedLufs, TargetTruePeakDbtp, "
        "MaxOvershootDbForAdaptiveFallback, MaxOvershootDbForReview, "
        "AcceptableAudioCodecsCsv, EnableDialogBoostTrack, "
        "EnableEnglishPreferredDefault, PreferredDefaultLanguageRank, "
        "EnableSpeechLanguageDetection"
        ") VALUES (1, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (Id) DO NOTHING",
        (
            TARGET_INTEGRATED_LUFS_DEFAULT,
            TARGET_TRUE_PEAK_DBTP_DEFAULT,
            MAX_OVERSHOOT_ADAPTIVE_DEFAULT,
            MAX_OVERSHOOT_REVIEW_DEFAULT,
            AcceptableCodecs,
            ENABLE_DIALOG_BOOST_DEFAULT,
            ENABLE_ENGLISH_PREFERRED_DEFAULT,
            PreferredRank,
            ENABLE_SPEECH_LANG_DETECTION_DEFAULT,
        ),
    )

    print('AudioComplianceRules: table + singleton row ensured (idempotent).')
    print('Rollback:')
    print('  DROP TABLE IF EXISTS AudioComplianceRules;')
    return 0


if __name__ == '__main__':
    raise SystemExit(Main())
