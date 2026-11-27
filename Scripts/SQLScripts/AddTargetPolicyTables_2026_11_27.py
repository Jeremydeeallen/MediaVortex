# directive: target-policy-1a-tables | # see policy.S1 -- additive only: policy tables seeded from today's values, the MediaFileTargets view, overrides migrated; nothing reads the view until target-policy-1b-verticals
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService

CheckSql = (
    "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{Name}') THEN "
    "ALTER TABLE {Table} ADD CONSTRAINT {Name} CHECK ({Expr}); END IF; END $$;"
)

TierProfiles = "p.Family = 'ANY' AND p.QualityLabel IS NOT NULL AND p.QualityTier IS NOT NULL"


# directive: target-policy-1a-tables | # see policy.S1
def _Count(Db, Sql):
    return int(Db.ExecuteScalar(Sql) or 0)


# directive: target-policy-1a-tables | # see policy.S1
def CreateTables(Db):
    Db.ExecuteNonQuery(
        "CREATE TABLE IF NOT EXISTS FrameRateClasses ("
        " Name TEXT PRIMARY KEY,"
        " MaxFps NUMERIC NOT NULL UNIQUE CHECK (MaxFps > 0))"
    )
    Db.ExecuteNonQuery(
        "CREATE TABLE IF NOT EXISTS TargetOverrides ("
        " Id BIGSERIAL PRIMARY KEY,"
        " StorageRootId INT NOT NULL REFERENCES StorageRoots(Id),"
        " Scope TEXT NOT NULL CHECK (Scope IN ('series', 'file')),"
        " Key TEXT NOT NULL,"
        " QualityTier INT NOT NULL CHECK (QualityTier BETWEEN 1 AND 5),"
        " SetBy TEXT NOT NULL,"
        " SetAt TIMESTAMP NOT NULL DEFAULT NOW(),"
        " UNIQUE (StorageRootId, Scope, Key))"
    )
    Db.ExecuteNonQuery(
        "CREATE TABLE IF NOT EXISTS EncoderSettings ("
        " Id BIGSERIAL PRIMARY KEY,"
        " Encoder TEXT NOT NULL CHECK (Encoder IN ('av1_nvenc', 'av1_qsv', 'libsvtav1')),"
        " QualityTier INT NOT NULL CHECK (QualityTier BETWEEN 1 AND 5),"
        " Preset TEXT NULL, Tune TEXT NULL, Multipass TEXT NULL, RateControl TEXT NOT NULL,"
        " MaxRateMultiplier NUMERIC NULL, BufSizeMultiplier NUMERIC NULL,"
        " SpatialAq INT NULL, TemporalAq INT NULL, PixelFormat TEXT NULL,"
        " Gop INT NULL, RcLookahead INT NULL, BFrames INT NULL, BRefMode TEXT NULL,"
        " QsvExtBrc INT NULL, QsvAdaptiveI INT NULL, QsvAdaptiveB INT NULL, QsvLookAheadDepth INT NULL,"
        " QsvBStrategy INT NULL, QsvTileCols INT NULL, QsvTileRows INT NULL,"
        " Crf INT NULL, FilmGrain INT NULL,"
        " UNIQUE (Encoder, QualityTier))"
    )
    Db.ExecuteNonQuery(
        "CREATE TABLE IF NOT EXISTS LadderCells ("
        " Id BIGSERIAL PRIMARY KEY,"
        " QualityTier INT NOT NULL CHECK (QualityTier BETWEEN 1 AND 5),"
        " ContentClass TEXT NOT NULL CHECK (ContentClass IN ('live_action', 'animation')),"
        " SourceResolution TEXT NOT NULL,"
        " FrameRateClass TEXT NOT NULL REFERENCES FrameRateClasses(Name),"
        " TargetResolution TEXT NOT NULL,"
        " TargetKbps INT NOT NULL CHECK (TargetKbps > 0),"
        " IcqQ INT NULL,"
        " UNIQUE (QualityTier, ContentClass, SourceResolution, FrameRateClass))"
    )


# directive: target-policy-1a-tables | # see policy.C7
def SeedFrameRateClasses(Db):
    # from: Docs/superpowers/audits/2026-11-26-knob-inventory.md
    Db.ExecuteNonQuery(
        "INSERT INTO FrameRateClasses (Name, MaxFps) VALUES ('standard', 30.0), ('high', 120.0) "
        "ON CONFLICT (Name) DO NOTHING"
    )


# directive: target-policy-1a-tables | # see policy.C6
def SeedEncoderSettings(Db):
    # from: Features/TranscodeJob/Worker/WorkerEncoderResolver.py
    Db.ExecuteNonQuery(
        "INSERT INTO EncoderSettings (Encoder, QualityTier, Preset, Tune, Multipass, RateControl, MaxRateMultiplier, BufSizeMultiplier,"
        " SpatialAq, TemporalAq, PixelFormat, Gop, RcLookahead, BFrames, BRefMode) "
        "SELECT 'av1_nvenc', p.QualityTier, '7', 'hq', 'fullres', 'vbr', 2.0, 2.0, 1, 1, 'p010le',"
        " MIN(pt.Gop), MIN(pt.RcLookahead), MIN(pt.BFrames), MIN(pt.BRefMode) "
        "FROM Profiles p JOIN ProfileThresholds pt ON pt.ProfileId = p.Id "
        f"WHERE {TierProfiles} GROUP BY p.QualityTier "
        "ON CONFLICT (Encoder, QualityTier) DO NOTHING"
    )
    # from: Features/TranscodeJob/Worker/WorkerEncoderResolver.py
    Db.ExecuteNonQuery(
        "INSERT INTO EncoderSettings (Encoder, QualityTier, Preset, RateControl, MaxRateMultiplier, BufSizeMultiplier, PixelFormat,"
        " Gop, RcLookahead, BFrames, BRefMode, QsvExtBrc, QsvAdaptiveI, QsvAdaptiveB, QsvLookAheadDepth, QsvBStrategy, QsvTileCols, QsvTileRows) "
        "SELECT 'av1_qsv', p.QualityTier, '1', 'vbr', 2.0, 2.0, 'p010le',"
        " MIN(pt.Gop), MIN(pt.RcLookahead), MIN(pt.BFrames), MIN(pt.BRefMode),"
        " MIN(pt.QsvExtBrc), MIN(pt.QsvAdaptiveI), MIN(pt.QsvAdaptiveB), MIN(pt.QsvLookAheadDepth), MIN(pt.QsvBStrategy), MIN(pt.QsvTileCols), MIN(pt.QsvTileRows) "
        "FROM Profiles p JOIN ProfileThresholds pt ON pt.ProfileId = p.Id "
        f"WHERE {TierProfiles} GROUP BY p.QualityTier "
        "ON CONFLICT (Encoder, QualityTier) DO NOTHING"
    )
    Db.ExecuteNonQuery(
        "INSERT INTO EncoderSettings (Encoder, QualityTier, Preset, RateControl, Crf, FilmGrain) "
        "SELECT 'libsvtav1', p.QualityTier, cf.PresetDefault::text, 'crf', cp.DefaultValue::int, cf.FilmGrainDefault "
        "FROM Profiles p CROSS JOIN CodecFlags cf JOIN CodecParameters cp ON cp.CodecFlagsId = cf.Id AND cp.ParameterName = 'crf' "
        f"WHERE cf.CodecName = 'libsvtav1' AND {TierProfiles} "
        "ON CONFLICT (Encoder, QualityTier) DO NOTHING"
    )


# directive: target-policy-1a-tables | # see policy.C7 -- a cell's TargetKbps is the kbps at its TargetResolution (today's encode row), so the dead 900 on downscaling source rows does not migrate
def SeedLadderCells(Db):
    Target = "CASE WHEN src.TranscodeDownTo IS NULL OR src.TranscodeDownTo IN ('', 'No downscaling') THEN src.Resolution ELSE src.TranscodeDownTo END"
    Db.ExecuteNonQuery(
        "INSERT INTO LadderCells (QualityTier, ContentClass, SourceResolution, FrameRateClass, TargetResolution, TargetKbps, IcqQ) "
        f"SELECT p.QualityTier, src.ContentClass, src.Resolution, 'standard', {Target}, enc.TargetKbps, enc.IcqQ "
        "FROM ProfileThresholds src JOIN Profiles p ON p.Id = src.ProfileId "
        f"JOIN ProfileThresholds enc ON enc.ProfileId = src.ProfileId AND enc.ContentClass = src.ContentClass AND enc.Resolution = {Target} "
        f"WHERE {TierProfiles} AND enc.TargetKbps IS NOT NULL "
        "ON CONFLICT (QualityTier, ContentClass, SourceResolution, FrameRateClass) DO NOTHING"
    )
    # from: Docs/superpowers/audits/2026-11-26-knob-inventory.md
    Db.ExecuteNonQuery(
        "INSERT INTO LadderCells (QualityTier, ContentClass, SourceResolution, FrameRateClass, TargetResolution, TargetKbps, IcqQ) "
        "SELECT QualityTier, ContentClass, SourceResolution, 'high', TargetResolution, ROUND(TargetKbps * 1.5)::int, IcqQ "
        "FROM LadderCells WHERE FrameRateClass = 'standard' "
        "ON CONFLICT (QualityTier, ContentClass, SourceResolution, FrameRateClass) DO NOTHING"
    )


# directive: target-policy-1a-tables | # see policy.S4 -- held-frame thresholds have no live source yet; target-policy-verification seeds them with the decider
def AddAcceptanceColumns(Db):
    for Column in ('VmafMin', 'VmafMax', 'HeldFrameDetectionThreshold', 'HeldFrameP25Min', 'HeldFrameMeanMin', 'LiveActionP10Min'):
        Db.ExecuteNonQuery(f"ALTER TABLE Profiles ADD COLUMN IF NOT EXISTS {Column} NUMERIC NULL")
    Db.ExecuteNonQuery(
        "UPDATE Profiles p SET VmafMin = g.VmafAutoReplaceMinThreshold, VmafMax = g.VmafAutoReplaceMaxThreshold "
        "FROM PostTranscodeGateConfig g "
        f"WHERE {TierProfiles} AND p.VmafMin IS NULL"
    )


# directive: target-policy-1a-tables | # see policy.S1
def AddLibraryAndContainerColumns(Db):
    Db.ExecuteNonQuery("ALTER TABLE StorageRoots ADD COLUMN IF NOT EXISTS ReviewBeforeReplace BOOLEAN NOT NULL DEFAULT FALSE")
    Db.ExecuteNonQuery("ALTER TABLE ContainerComplianceRules ADD COLUMN IF NOT EXISTS OutputContainer TEXT NOT NULL DEFAULT 'mp4'")


# directive: target-policy-1a-tables | # see policy.W2 -- an override is a tier: only assignments naming a tier profile migrate; profile-level choices have no representation
def MigrateOverrides(Db):
    Db.ExecuteNonQuery(
        "INSERT INTO TargetOverrides (StorageRootId, Scope, Key, QualityTier, SetBy, SetAt) "
        "SELECT sp.StorageRootId, 'series', sp.RelativePath, p.QualityTier, 'migrate:SeriesProfiles:' || sp.Id, sp.LastModifiedDate "
        "FROM SeriesProfiles sp JOIN Profiles p ON p.ProfileName = sp.AssignedProfile "
        f"WHERE {TierProfiles} "
        "ON CONFLICT (StorageRootId, Scope, Key) DO NOTHING"
    )
    SkippedSeries = Db.ExecuteQuery(
        "SELECT sp.StorageRootId, sp.RelativePath, sp.AssignedProfile FROM SeriesProfiles sp "
        "WHERE NOT EXISTS (SELECT 1 FROM TargetOverrides t WHERE t.StorageRootId = sp.StorageRootId AND t.Scope = 'series' AND t.Key = sp.RelativePath) "
        "ORDER BY sp.Id"
    )
    for R in SkippedSeries:
        print(f"  series override NOT migrated (no tier profile): root={R.get('StorageRootId')} {R.get('RelativePath')!r} -> {R.get('AssignedProfile')!r}")
    Db.ExecuteNonQuery(
        "INSERT INTO TargetOverrides (StorageRootId, Scope, Key, QualityTier, SetBy, SetAt) "
        "SELECT mf.StorageRootId, 'file', mf.Id::text, p.QualityTier, 'migrate:AssignedProfile:' || mf.AssignedProfileSource, NOW() "
        "FROM MediaFiles mf JOIN StorageRoots sr ON sr.Id = mf.StorageRootId AND sr.DefaultQualityTier IS NOT NULL "
        "JOIN Profiles p ON p.ProfileName = mf.AssignedProfile "
        f"WHERE {TierProfiles} AND mf.AssignedProfileSource IN ('operator', 'manual_sql') "
        "AND NOT EXISTS (SELECT 1 FROM TargetOverrides so WHERE so.StorageRootId = mf.StorageRootId AND so.Scope = 'series'"
        "  AND so.Key = split_part(mf.RelativePath, '/', 1) AND so.QualityTier = p.QualityTier) "
        "ON CONFLICT (StorageRootId, Scope, Key) DO NOTHING"
    )
    Untiered = Db.ExecuteQuery(
        "SELECT sr.Name, mf.AssignedProfile, COUNT(*) AS Files FROM MediaFiles mf JOIN StorageRoots sr ON sr.Id = mf.StorageRootId "
        "WHERE sr.DefaultQualityTier IS NULL AND mf.AssignedProfileSource IN ('operator', 'manual_sql') GROUP BY 1, 2 ORDER BY 1, 2"
    )
    for R in Untiered:
        print(f"  file assignments NOT migrated (library {R.get('Name')!r} has no default tier; its tier is the operator's Phase 6 decision): {R.get('Files')} x {R.get('AssignedProfile')!r}")


# directive: target-policy-1a-tables | # see policy.S1 -- the one definition of a file's target; column list = policy.feature.md S1
def CreateView(Db):
    Db.ExecuteNonQuery("DROP VIEW IF EXISTS MediaFileTargets")
    Db.ExecuteNonQuery(' '.join([
        "CREATE VIEW MediaFileTargets AS",
        "WITH Base AS (",
        " SELECT mf.Id AS MediaFileId, mf.StorageRootId, mf.ResolutionCategory AS SourceResolution,",
        "  COALESCE(fo.QualityTier, so.QualityTier, ga.GenreTier, sr.DefaultQualityTier) AS Tier,",
        "  CASE WHEN fo.QualityTier IS NOT NULL THEN 'file_override'",
        "       WHEN so.QualityTier IS NOT NULL THEN 'series_override'",
        "       WHEN ga.GenreTier IS NOT NULL THEN 'genre=' || ga.GenreTierName",
        "       WHEN sr.DefaultQualityTier IS NOT NULL THEN 'library' END AS TierOrigin,",
        "  CASE WHEN ga.ClassCount > 1 THEN NULL WHEN ga.ClassCount = 1 THEN ga.GenreClass ELSE sr.DefaultContentClass END AS ContentClass,",
        "  CASE WHEN ga.ClassCount > 1 THEN NULL WHEN ga.ClassCount = 1 THEN 'genre=' || ga.GenreClassName",
        "       WHEN sr.DefaultContentClass IS NOT NULL THEN 'library' END AS ClassOrigin,",
        "  COALESCE(ga.ClassCount, 0) > 1 AS ClassConflict,",
        "  frc.Name AS FrameRateClass,",
        "  sr.ReviewBeforeReplace",
        " FROM MediaFiles mf",
        " JOIN StorageRoots sr ON sr.Id = mf.StorageRootId",
        " LEFT JOIN TargetOverrides fo ON fo.StorageRootId = mf.StorageRootId AND fo.Scope = 'file' AND fo.Key = mf.Id::text",
        " LEFT JOIN TargetOverrides so ON so.StorageRootId = mf.StorageRootId AND so.Scope = 'series' AND so.Key = split_part(mf.RelativePath, '/', 1)",
        " LEFT JOIN LATERAL (",
        "   SELECT MAX(g.QualityTier) AS GenreTier,",
        "          (ARRAY_AGG(g.Genre ORDER BY g.QualityTier DESC, g.Genre) FILTER (WHERE g.QualityTier IS NOT NULL))[1] AS GenreTierName,",
        "          COUNT(DISTINCT g.ContentClass) AS ClassCount,",
        "          MIN(g.ContentClass) AS GenreClass,",
        "          (ARRAY_AGG(g.Genre ORDER BY g.Genre) FILTER (WHERE g.ContentClass IS NOT NULL))[1] AS GenreClassName",
        "   FROM unnest(string_to_array(mf.Genres, ',')) AS gn(Name)",
        "   JOIN GenreQualityTiers g ON g.Genre = btrim(gn.Name)) ga ON TRUE",
        " LEFT JOIN LATERAL (SELECT f.Name FROM FrameRateClasses f WHERE mf.FrameRate IS NOT NULL AND mf.FrameRate <= f.MaxFps ORDER BY f.MaxFps LIMIT 1) frc ON TRUE",
        ")",
        "SELECT b.MediaFileId, b.StorageRootId, b.Tier, b.TierOrigin, b.ContentClass, b.ClassOrigin, b.FrameRateClass, b.SourceResolution,",
        " lc.TargetResolution, lc.TargetKbps, lc.IcqQ,",
        " p.QualityLabel, p.QualityTestRequired, p.VmafMin, p.VmafMax, p.HeldFrameDetectionThreshold, p.HeldFrameP25Min, p.HeldFrameMeanMin, p.LiveActionP10Min,",
        " ap.Id AS AudioPolicyId,",
        " cr.OutputContainer, cr.AcceptableContainersCsv, ar.AcceptableAudioCodecsCsv,",
        " vct.Multiplier AS CeilingMultiplier, b.ReviewBeforeReplace,",
        " CASE WHEN b.Tier IS NULL THEN 'Tier'",
        "      WHEN b.ClassConflict THEN 'ContentClassConflict'",
        "      WHEN b.ContentClass IS NULL THEN 'ContentClass'",
        "      WHEN b.FrameRateClass IS NULL THEN 'FrameRateClass'",
        "      WHEN b.SourceResolution IS NULL THEN 'SourceResolution'",
        "      WHEN lc.Id IS NULL THEN 'LadderCell'",
        "      WHEN p.Id IS NULL THEN 'Profile'",
        "      WHEN p.VmafMin IS NULL THEN 'VmafMin'",
        "      WHEN ap.Id IS NULL THEN 'AudioPolicy'",
        "      WHEN cr.Id IS NULL THEN 'ContainerRules'",
        "      WHEN ar.Id IS NULL THEN 'AudioRules'",
        "      WHEN vct.Id IS NULL THEN 'CeilingMultiplier' END AS Undecided",
        "FROM Base b",
        "LEFT JOIN LadderCells lc ON lc.QualityTier = b.Tier AND lc.ContentClass = b.ContentClass AND lc.SourceResolution = b.SourceResolution AND lc.FrameRateClass = b.FrameRateClass",
        "LEFT JOIN Profiles p ON p.Family = 'ANY' AND p.QualityLabel IS NOT NULL AND p.QualityTier = b.Tier",
        "LEFT JOIN LATERAL (SELECT a.Id FROM AudioNormalizationConfig a",
        "  WHERE (a.Scope = 'item' AND a.ScopeKey = b.MediaFileId::text) OR (a.Scope = 'library' AND a.ScopeKey = b.StorageRootId::text) OR a.Scope = 'global'",
        "  ORDER BY CASE a.Scope WHEN 'item' THEN 0 WHEN 'library' THEN 1 ELSE 2 END LIMIT 1) ap ON TRUE",
        "LEFT JOIN LATERAL (SELECT c.Id, c.OutputContainer, c.AcceptableContainersCsv FROM ContainerComplianceRules c ORDER BY c.Id LIMIT 1) cr ON TRUE",
        "LEFT JOIN LATERAL (SELECT r.Id, r.AcceptableAudioCodecsCsv FROM AudioComplianceRules r ORDER BY r.Id LIMIT 1) ar ON TRUE",
        "LEFT JOIN VideoComplianceThresholds vct ON vct.ResolutionCategory = b.SourceResolution",
    ]))


# directive: target-policy-1a-tables | # see policy.S1
def Run():
    Db = DatabaseService()
    CreateTables(Db)
    SeedFrameRateClasses(Db)
    SeedEncoderSettings(Db)
    SeedLadderCells(Db)
    AddAcceptanceColumns(Db)
    AddLibraryAndContainerColumns(Db)
    MigrateOverrides(Db)
    CreateView(Db)
    print(f"  FrameRateClasses: {_Count(Db, 'SELECT COUNT(*) FROM FrameRateClasses')} rows")
    print(f"  EncoderSettings:  {_Count(Db, 'SELECT COUNT(*) FROM EncoderSettings')} rows")
    print(f"  LadderCells:      {_Count(Db, 'SELECT COUNT(*) FROM LadderCells')} rows")
    Series = _Count(Db, "SELECT COUNT(*) FROM TargetOverrides WHERE Scope = 'series'")
    Files = _Count(Db, "SELECT COUNT(*) FROM TargetOverrides WHERE Scope = 'file'")
    print(f"  TargetOverrides:  {Series} series, {Files} file")
    print(f"  Profiles tiers with VmafMin: {_Count(Db, 'SELECT COUNT(*) FROM Profiles WHERE VmafMin IS NOT NULL')}")
    for R in Db.ExecuteQuery("SELECT Undecided, COUNT(*) AS Files FROM MediaFileTargets GROUP BY Undecided ORDER BY 2 DESC"):
        print(f"  MediaFileTargets Undecided={R.get('Undecided')!r}: {R.get('Files')}")
    return 0


if __name__ == '__main__':
    raise SystemExit(Run())
