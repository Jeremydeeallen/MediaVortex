import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


NEW_COLUMNS = [
    ("DialogBoostTargetLufs", "NUMERIC(5,2) NOT NULL DEFAULT -20.0"),
    ("DialogBoostTargetLra", "NUMERIC(5,2) NOT NULL DEFAULT 5.0"),
    ("SampleLimitHeadroomDb", "NUMERIC(5,2) NOT NULL DEFAULT 4.0"),
    ("Track0BitratePerChannelKbps", "INT NOT NULL DEFAULT 64"),
    ("Track0MinPerChannelKbps", "INT NOT NULL DEFAULT 48"),
    ("Track1StereoBitrateKbps", "INT NOT NULL DEFAULT 192"),
    ("Track1VocalsRmsFallbackDbfs", "NUMERIC(6,2) NOT NULL DEFAULT -50.0"),
    ("VocalsBoostDb", "NUMERIC(5,2) NOT NULL DEFAULT 5.0"),
    ("InstrumentalAttenDb", "NUMERIC(5,2) NOT NULL DEFAULT 3.0"),
    ("PremixCompressorThreshold", "NUMERIC(5,3) NOT NULL DEFAULT 0.030"),
    ("PremixCompressorRatio", "NUMERIC(4,1) NOT NULL DEFAULT 9.0"),
    ("PremixCompressorMakeupDb", "NUMERIC(4,1) NOT NULL DEFAULT 3.0"),
    ("PremixDynaudnormFrameLen", "INT NOT NULL DEFAULT 150"),
    ("PremixDynaudnormGaussSize", "INT NOT NULL DEFAULT 13"),
]


DEAD_COLUMNS_AUDIO_COMPLIANCE = [
    "MaxOvershootDbForAdaptiveFallback",
    "MaxOvershootDbForReview",
    "EnableDialogBoostTrack",
    "EnableEnglishPreferredDefault",
    "PreferredDefaultLanguageRank",
    "EnableSpeechLanguageDetection",
]


DEAD_COLUMNS_AUDIO_NORMALIZATION_CONFIG = [
    "TargetIntegratedLufs",
    "TargetTruePeakDbtp",
]


def Main():
    Db = DatabaseService()

    for Name, Ddl in NEW_COLUMNS:
        Db.ExecuteNonQuery(
            f"ALTER TABLE AudioComplianceRules ADD COLUMN IF NOT EXISTS {Name} {Ddl}"
        )

    for Name in DEAD_COLUMNS_AUDIO_COMPLIANCE:
        Db.ExecuteNonQuery(
            f"ALTER TABLE AudioComplianceRules DROP COLUMN IF EXISTS {Name}"
        )

    for Name in DEAD_COLUMNS_AUDIO_NORMALIZATION_CONFIG:
        Db.ExecuteNonQuery(
            f"ALTER TABLE AudioNormalizationConfig DROP COLUMN IF EXISTS {Name}"
        )

    print('AudioComplianceRules: 14 knob columns added; 6 legacy columns dropped.')
    print('AudioNormalizationConfig: TargetIntegratedLufs + TargetTruePeakDbtp dropped (moved to AudioComplianceRules global).')
    return 0


if __name__ == '__main__':
    raise SystemExit(Main())
