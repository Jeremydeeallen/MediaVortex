import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C1
def Run():
    DB = DatabaseService()

    DB.ExecuteNonQuery(
        "CREATE TABLE IF NOT EXISTS TranscodeRules ("
        "Id INT PRIMARY KEY DEFAULT 1, "
        "ResolutionExceedsProfileTarget BOOLEAN NOT NULL DEFAULT TRUE, "
        "AcceptableVideoCodecsCsv TEXT NOT NULL DEFAULT 'h264,hevc,av1', "
        "EstimatedSavingsMBThreshold INT NOT NULL DEFAULT 150, "
        "PreventUpscale BOOLEAN NOT NULL DEFAULT TRUE, "
        "LastUpdated TIMESTAMP DEFAULT NOW(), "
        "CHECK (Id = 1))"
    )
    DB.ExecuteNonQuery("INSERT INTO TranscodeRules (Id) VALUES (1) ON CONFLICT DO NOTHING")

    DB.ExecuteNonQuery(
        "CREATE TABLE IF NOT EXISTS RemuxRules ("
        "Id INT PRIMARY KEY DEFAULT 1, "
        "AcceptableContainersCsv TEXT NOT NULL DEFAULT 'mp4,mov,m4v', "
        "AcceptableAudioCodecsMp4Csv TEXT NOT NULL DEFAULT 'aac,ac3,eac3,mp3', "
        "RequireAudioNormalized BOOLEAN NOT NULL DEFAULT TRUE, "
        "LastUpdated TIMESTAMP DEFAULT NOW(), "
        "CHECK (Id = 1))"
    )
    DB.ExecuteNonQuery("INSERT INTO RemuxRules (Id) VALUES (1) ON CONFLICT DO NOTHING")

    DB.ExecuteNonQuery(
        "CREATE TABLE IF NOT EXISTS AudioFixRules ("
        "Id INT PRIMARY KEY DEFAULT 1, "
        "TargetLoudnessLufs INT NOT NULL DEFAULT -23, "
        "ToleranceLufs DOUBLE PRECISION NOT NULL DEFAULT 1.0, "
        "RequireLufsMeasured BOOLEAN NOT NULL DEFAULT TRUE, "
        "LastUpdated TIMESTAMP DEFAULT NOW(), "
        "CHECK (Id = 1))"
    )
    DB.ExecuteNonQuery("INSERT INTO AudioFixRules (Id) VALUES (1) ON CONFLICT DO NOTHING")

    DB.ExecuteNonQuery(
        "CREATE TABLE IF NOT EXISTS SubtitleFixRules ("
        "Id INT PRIMARY KEY DEFAULT 1, "
        "Enabled BOOLEAN NOT NULL DEFAULT FALSE, "
        "MovTextRequiredForMp4 BOOLEAN NOT NULL DEFAULT TRUE, "
        "NonNativeSubtitleFormatsCsv TEXT NOT NULL DEFAULT 'ass,ssa,vobsub', "
        "RequireForcedSubtitlesPresent BOOLEAN NOT NULL DEFAULT TRUE, "
        "LastUpdated TIMESTAMP DEFAULT NOW(), "
        "CHECK (Id = 1))"
    )
    DB.ExecuteNonQuery("INSERT INTO SubtitleFixRules (Id) VALUES (1) ON CONFLICT DO NOTHING")

    DB.ExecuteNonQuery(
        "CREATE TABLE IF NOT EXISTS ComplianceGates ("
        "Id INT PRIMARY KEY DEFAULT 1, "
        "RequireExplicitEnglishAudio BOOLEAN NOT NULL DEFAULT TRUE, "
        "BlockOnAudioCorruptSuspect BOOLEAN NOT NULL DEFAULT TRUE, "
        "RequireAudioStream BOOLEAN NOT NULL DEFAULT TRUE, "
        "RequireLoudnessMeasurements BOOLEAN NOT NULL DEFAULT TRUE, "
        "RequireProbeMetadata BOOLEAN NOT NULL DEFAULT TRUE, "
        "RequireEffectiveProfile BOOLEAN NOT NULL DEFAULT TRUE, "
        "RequireResolutionCategory BOOLEAN NOT NULL DEFAULT TRUE, "
        "RequireProfileThresholds BOOLEAN NOT NULL DEFAULT TRUE, "
        "LastUpdated TIMESTAMP DEFAULT NOW(), "
        "CHECK (Id = 1))"
    )
    DB.ExecuteNonQuery("INSERT INTO ComplianceGates (Id) VALUES (1) ON CONFLICT DO NOTHING")

    for TableName in ('TranscodeRules', 'RemuxRules', 'AudioFixRules', 'SubtitleFixRules', 'ComplianceGates'):
        Rows = DB.ExecuteQuery("SELECT COUNT(*) AS N FROM " + TableName)
        print("  " + TableName + ": " + str(Rows[0]['n']) + " row(s)")


if __name__ == '__main__':
    Run()
