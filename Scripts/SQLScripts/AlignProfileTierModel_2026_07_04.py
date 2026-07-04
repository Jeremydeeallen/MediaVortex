#!/usr/bin/env python3
"""Profile tier-ladder schema. See directive transcode-flow-canonical C12 + C14."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


# directive: transcode-flow-canonical | # see transcode.ST5
def ColumnExists(Db: DatabaseService, TableName: str, ColumnName: str) -> bool:
    """True if the given column exists on TableName (lowercased)."""
    Rows = Db.ExecuteQuery(
        "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
        (TableName.lower(), ColumnName.lower()),
    )
    return bool(Rows)


# directive: transcode-flow-canonical | # see transcode.ST5
def TableExists(Db: DatabaseService, TableName: str) -> bool:
    """True if TableName exists in current_schema (lowercased)."""
    Rows = Db.ExecuteQuery(
        "SELECT 1 FROM information_schema.tables WHERE table_name = %s AND table_schema = current_schema()",
        (TableName.lower(),),
    )
    return bool(Rows)


# directive: transcode-flow-canonical | # see transcode.ST5
def ConstraintExists(Db: DatabaseService, ConstraintName: str) -> bool:
    """True if a pg_constraint row named ConstraintName exists (lowercased)."""
    Rows = Db.ExecuteQuery(
        "SELECT 1 FROM pg_constraint WHERE conname = %s",
        (ConstraintName.lower(),),
    )
    return bool(Rows)


# directive: transcode-flow-canonical | # see transcode.ST5
def AddProfileTierColumns(Db: DatabaseService) -> None:
    """Profiles gains Family + QualityTier + ContentClass with CHECKs. Not-null enforced after backfill (later migration)."""
    if not ColumnExists(Db, 'Profiles', 'Family'):
        print("Adding Profiles.Family (nullable initially; NOT NULL enforced post-backfill)")
        Db.ExecuteNonQuery("ALTER TABLE Profiles ADD COLUMN Family TEXT NULL")
    if not ColumnExists(Db, 'Profiles', 'QualityTier'):
        print("Adding Profiles.QualityTier (nullable initially)")
        Db.ExecuteNonQuery("ALTER TABLE Profiles ADD COLUMN QualityTier INT NULL")
    if not ConstraintExists(Db, 'profiles_qualitytier_range'):
        Db.ExecuteNonQuery(
            "ALTER TABLE Profiles ADD CONSTRAINT profiles_qualitytier_range "
            "CHECK (QualityTier IS NULL OR QualityTier BETWEEN 1 AND 5)"
        )
    if not ColumnExists(Db, 'Profiles', 'ContentClass'):
        print("Adding Profiles.ContentClass (nullable initially)")
        Db.ExecuteNonQuery("ALTER TABLE Profiles ADD COLUMN ContentClass TEXT NULL")
    if not ConstraintExists(Db, 'profiles_contentclass_enum'):
        Db.ExecuteNonQuery(
            "ALTER TABLE Profiles ADD CONSTRAINT profiles_contentclass_enum "
            "CHECK (ContentClass IS NULL OR ContentClass IN ('live_action','animation','mixed'))"
        )


# directive: transcode-flow-canonical | # see transcode.ST5
def AddProfileThresholdKnobs(Db: DatabaseService) -> None:
    """ProfileThresholds gains TargetKbps (VBR absolute target) + IcqQ (ICQ q value)."""
    if not ColumnExists(Db, 'ProfileThresholds', 'TargetKbps'):
        print("Adding ProfileThresholds.TargetKbps")
        Db.ExecuteNonQuery("ALTER TABLE ProfileThresholds ADD COLUMN TargetKbps INT NULL")
    if not ColumnExists(Db, 'ProfileThresholds', 'IcqQ'):
        print("Adding ProfileThresholds.IcqQ")
        Db.ExecuteNonQuery("ALTER TABLE ProfileThresholds ADD COLUMN IcqQ INT NULL")


# directive: transcode-flow-canonical | # see transcode.ST5 -- AdequacyGate audit
def AddMediaFileAdequacyCols(Db: DatabaseService) -> None:
    """MediaFiles gains AdequacyDecision + AdequacyDecisionAt for admission-adequacy audit trail."""
    if not ColumnExists(Db, 'MediaFiles', 'AdequacyDecision'):
        print("Adding MediaFiles.AdequacyDecision")
        Db.ExecuteNonQuery("ALTER TABLE MediaFiles ADD COLUMN AdequacyDecision TEXT NULL")
    if not ColumnExists(Db, 'MediaFiles', 'AdequacyDecisionAt'):
        print("Adding MediaFiles.AdequacyDecisionAt")
        Db.ExecuteNonQuery("ALTER TABLE MediaFiles ADD COLUMN AdequacyDecisionAt TIMESTAMP NULL")


# directive: transcode-flow-canonical | # see transcode.ST7 -- Smart VMAF sampling
def CreateVmafConfidenceStats(Db: DatabaseService) -> None:
    """Rolling per-bucket stats used by SmartConfidenceSkip. UNIQUE per bucket key."""
    Db.ExecuteNonQuery(
        "CREATE TABLE IF NOT EXISTS VmafConfidenceStats ("
        "  Id BIGSERIAL PRIMARY KEY,"
        "  ProfileId BIGINT NOT NULL REFERENCES Profiles(Id) ON DELETE CASCADE,"
        "  SourceCodec TEXT NOT NULL,"
        "  SourceResolutionTier TEXT NOT NULL,"
        "  BitratePerPixelBucket INT NOT NULL CHECK (BitratePerPixelBucket BETWEEN 1 AND 5),"
        "  ContentClass TEXT NOT NULL CHECK (ContentClass IN ('live_action','animation','mixed')),"
        "  SampleCount INT NOT NULL DEFAULT 0,"
        "  VmafMean NUMERIC(5,2) NULL,"
        "  VmafStdDev NUMERIC(5,2) NULL,"
        "  PassRate NUMERIC(5,4) NULL,"
        "  LastUpdated TIMESTAMP NOT NULL DEFAULT NOW(),"
        "  CONSTRAINT vmafconfidencestats_bucket_unique "
        "    UNIQUE (ProfileId, SourceCodec, SourceResolutionTier, BitratePerPixelBucket, ContentClass)"
        ")"
    )


# directive: transcode-flow-canonical | # see transcode.ST7 -- Smart VMAF confidence knobs
def AddGateConfigConfidenceKnobs(Db: DatabaseService) -> None:
    """PostTranscodeGateConfig gains MinConfidenceSampleCount + MinConfidencePassRate + SigmaMargin for SmartConfidenceSkip."""
    if not ColumnExists(Db, 'PostTranscodeGateConfig', 'MinConfidenceSampleCount'):
        print("Adding PostTranscodeGateConfig.MinConfidenceSampleCount")
        Db.ExecuteNonQuery(
            "ALTER TABLE PostTranscodeGateConfig ADD COLUMN MinConfidenceSampleCount INT NOT NULL DEFAULT 10"
        )
    if not ColumnExists(Db, 'PostTranscodeGateConfig', 'MinConfidencePassRate'):
        print("Adding PostTranscodeGateConfig.MinConfidencePassRate")
        Db.ExecuteNonQuery(
            "ALTER TABLE PostTranscodeGateConfig ADD COLUMN MinConfidencePassRate NUMERIC(5,4) NOT NULL DEFAULT 0.95"
        )
    if not ColumnExists(Db, 'PostTranscodeGateConfig', 'SigmaMargin'):
        print("Adding PostTranscodeGateConfig.SigmaMargin")
        Db.ExecuteNonQuery(
            "ALTER TABLE PostTranscodeGateConfig ADD COLUMN SigmaMargin NUMERIC(4,2) NOT NULL DEFAULT 2.00"
        )


# directive: transcode-flow-canonical | # see transcode.ST5 -- BitratePerPixel bucket boundaries
def SeedBitratePerPixelBoundaries(Db: DatabaseService) -> None:
    """SystemSettings gains BitratePerPixelBoundaries JSON array for bucket assignment. ON CONFLICT DO NOTHING for idempotency."""
    Db.ExecuteNonQuery(
        "INSERT INTO SystemSettings (SettingKey, SettingValue) VALUES (%s, %s) "
        "ON CONFLICT (SettingKey) DO NOTHING",
        ('BitratePerPixelBoundaries', '[0.03, 0.06, 0.10, 0.16]'),
    )


# directive: transcode-flow-canonical | # see transcode.ST5
def Summary(Db: DatabaseService) -> None:
    """Print post-migration invariants for operator verification."""
    print("\n--- Summary ---")
    print(f"  Profiles cols: Family={ColumnExists(Db, 'Profiles', 'Family')} QualityTier={ColumnExists(Db, 'Profiles', 'QualityTier')} ContentClass={ColumnExists(Db, 'Profiles', 'ContentClass')}")
    print(f"  ProfileThresholds cols: TargetKbps={ColumnExists(Db, 'ProfileThresholds', 'TargetKbps')} IcqQ={ColumnExists(Db, 'ProfileThresholds', 'IcqQ')}")
    print(f"  MediaFiles cols: AdequacyDecision={ColumnExists(Db, 'MediaFiles', 'AdequacyDecision')} AdequacyDecisionAt={ColumnExists(Db, 'MediaFiles', 'AdequacyDecisionAt')}")
    print(f"  VmafConfidenceStats exists: {TableExists(Db, 'VmafConfidenceStats')}")
    print(f"  PostTranscodeGateConfig confidence knobs: MinConfidenceSampleCount={ColumnExists(Db, 'PostTranscodeGateConfig', 'MinConfidenceSampleCount')} MinConfidencePassRate={ColumnExists(Db, 'PostTranscodeGateConfig', 'MinConfidencePassRate')} SigmaMargin={ColumnExists(Db, 'PostTranscodeGateConfig', 'SigmaMargin')}")


# directive: transcode-flow-canonical | # see transcode.ST5
def RunMigration() -> None:
    """Entry point."""
    Db = DatabaseService()
    AddProfileTierColumns(Db)
    AddProfileThresholdKnobs(Db)
    AddMediaFileAdequacyCols(Db)
    CreateVmafConfidenceStats(Db)
    AddGateConfigConfidenceKnobs(Db)
    SeedBitratePerPixelBoundaries(Db)
    Summary(Db)


if __name__ == '__main__':
    RunMigration()
