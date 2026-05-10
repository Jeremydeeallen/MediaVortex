#!/usr/bin/env python3
"""
AddQueueAdmissionTables.py
Migration: data-driven queue-admission gate.

Owns: Features/TranscodeQueue/marginal-savings-gate.feature.md criteria 8-12.

Creates three normalized tables (NOT new SystemSettings KV rows -- this feature
intentionally moves config out of the legacy key-value pattern):

  - QueueAdmissionConfig: single-row scalar config (Id=1 CHECK)
        MinTranscodeSavingsMB INT NOT NULL DEFAULT 150
        MissingEstimatePolicy TEXT NOT NULL DEFAULT 'admit'

  - CrfBitrateEstimates: lookup keyed on (Codec, Resolution, Crf)
        EstimatedKbps INT NOT NULL
        Source TEXT (e.g. 'HistoricalSeed', 'OperatorOverride')
        Seeded from observed TranscodeAttempts averages where >= 10 samples.

  - CodecCompatibility: lookup keyed on (Kind, Name)
        Kind in ('VideoCodec', 'AudioCodecMp4', 'Container')
        IsAcceptable BOOLEAN
        Replaces hardcoded class constants in QueueManagementBusinessService.

Idempotent. Safe to run multiple times.
"""

import os
import psycopg2


def GetConnection():
    return psycopg2.connect(
        host=os.environ.get('MEDIAVORTEX_DB_HOST', 'localhost'),
        port=int(os.environ.get('MEDIAVORTEX_DB_PORT', '5432')),
        database=os.environ.get('MEDIAVORTEX_DB_NAME', 'mediavortex'),
        user=os.environ.get('MEDIAVORTEX_DB_USER', 'mediavortex'),
        password=os.environ.get('MEDIAVORTEX_DB_PASSWORD', 'mediavortex'),
    )


def TableExists(Cursor, TableName):
    Cursor.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_name = %s AND table_schema = current_schema()
        """,
        (TableName.lower(),),
    )
    return Cursor.fetchone() is not None


def CreateQueueAdmissionConfig(Cursor):
    if TableExists(Cursor, 'QueueAdmissionConfig'):
        print("Table 'QueueAdmissionConfig' already exists -- skipping CREATE")
        return False
    print("Creating table QueueAdmissionConfig (single-row scalar config) ...")
    Cursor.execute("""
        CREATE TABLE QueueAdmissionConfig (
            Id INT PRIMARY KEY DEFAULT 1,
            MinTranscodeSavingsMB INT NOT NULL DEFAULT 150,
            MissingEstimatePolicy TEXT NOT NULL DEFAULT 'admit',
            LastUpdated TIMESTAMP DEFAULT NOW(),
            CONSTRAINT queueadmissionconfig_singlerow CHECK (Id = 1),
            CONSTRAINT queueadmissionconfig_policy_valid
                CHECK (MissingEstimatePolicy IN ('admit', 'block'))
        )
    """)
    print("  table created.")
    return True


def CreateCrfBitrateEstimates(Cursor):
    if TableExists(Cursor, 'CrfBitrateEstimates'):
        print("Table 'CrfBitrateEstimates' already exists -- skipping CREATE")
        return False
    print("Creating table CrfBitrateEstimates (Codec, Resolution, Crf -> kbps) ...")
    Cursor.execute("""
        CREATE TABLE CrfBitrateEstimates (
            Id BIGSERIAL PRIMARY KEY,
            Codec TEXT NOT NULL,
            Resolution TEXT NOT NULL,
            Crf INTEGER NOT NULL,
            EstimatedKbps INTEGER NOT NULL,
            LastUpdated TIMESTAMP DEFAULT NOW(),
            Source TEXT,
            CONSTRAINT crfbitrateestimates_unique UNIQUE (Codec, Resolution, Crf)
        )
    """)
    print("  table created.")
    return True


def CreateCodecCompatibility(Cursor):
    if TableExists(Cursor, 'CodecCompatibility'):
        print("Table 'CodecCompatibility' already exists -- skipping CREATE")
        return False
    print("Creating table CodecCompatibility (Kind, Name -> IsAcceptable) ...")
    Cursor.execute("""
        CREATE TABLE CodecCompatibility (
            Id BIGSERIAL PRIMARY KEY,
            Kind TEXT NOT NULL,
            Name TEXT NOT NULL,
            IsAcceptable BOOLEAN NOT NULL DEFAULT true,
            Description TEXT,
            LastUpdated TIMESTAMP DEFAULT NOW(),
            Source TEXT,
            CONSTRAINT codeccompatibility_unique UNIQUE (Kind, Name),
            CONSTRAINT codeccompatibility_kind_valid
                CHECK (Kind IN ('VideoCodec', 'AudioCodecMp4', 'Container'))
        )
    """)
    print("  table created.")
    return True


def SeedQueueAdmissionConfig(Cursor):
    Cursor.execute("SELECT 1 FROM QueueAdmissionConfig WHERE Id = 1")
    if Cursor.fetchone() is not None:
        print("QueueAdmissionConfig row already seeded -- skipping")
        return
    print("Seeding QueueAdmissionConfig defaults (Id=1, MinTranscodeSavingsMB=150, MissingEstimatePolicy='admit') ...")
    Cursor.execute("""
        INSERT INTO QueueAdmissionConfig (Id, MinTranscodeSavingsMB, MissingEstimatePolicy)
        VALUES (1, 150, 'admit')
    """)
    print("  seeded.")


def SeedCodecCompatibility(Cursor):
    Cursor.execute("SELECT COUNT(*) FROM CodecCompatibility")
    if Cursor.fetchone()[0] > 0:
        print("CodecCompatibility already has rows -- skipping seed")
        return
    print("Seeding CodecCompatibility from current class constants ...")
    SeedRows = [
        # Containers (was COMPATIBLE_CONTAINERS = {'mp4', 'mov', 'm4v'})
        ('Container', 'mp4', True, 'MP4 container, native Jellyfin direct-play'),
        ('Container', 'mov', True, 'QuickTime container, MP4-family'),
        ('Container', 'm4v', True, 'iTunes/MP4-family container'),
        # Video codecs (was ACCEPTABLE_VIDEO_CODECS = {'h264', 'hevc', 'av1'})
        ('VideoCodec', 'h264', True, 'H.264/AVC -- universal device support'),
        ('VideoCodec', 'hevc', True, 'H.265/HEVC -- modern device support'),
        ('VideoCodec', 'av1', True, 'AV1 -- modern device support, highest efficiency'),
        # Audio codecs in MP4 (was MP4_COMPATIBLE_AUDIO_CODECS = {'aac', 'ac3', 'eac3', 'mp3'})
        ('AudioCodecMp4', 'aac', True, 'AAC -- baseline MP4 audio'),
        ('AudioCodecMp4', 'ac3', True, 'AC-3 / Dolby Digital'),
        ('AudioCodecMp4', 'eac3', True, 'E-AC-3 / Dolby Digital Plus'),
        ('AudioCodecMp4', 'mp3', True, 'MP3 -- legacy MP4-compatible audio'),
    ]
    for Kind, Name, IsAcceptable, Description in SeedRows:
        Cursor.execute(
            """
            INSERT INTO CodecCompatibility (Kind, Name, IsAcceptable, Description, Source)
            VALUES (%s, %s, %s, %s, 'InitialSeed')
            """,
            (Kind, Name, IsAcceptable, Description),
        )
    print(f"  seeded {len(SeedRows)} rows.")


def SeedCrfBitrateEstimatesFromHistory(Cursor):
    """Compute (Codec, Resolution, CRF) -> EstimatedKbps from TranscodeAttempts.

    Strategy:
      - Parse FFpmpegCommand to extract -c:v <codec>, -crf <n>, scale=W:H.
      - When scale=W:H present, output resolution is derived from the height
        (852:480 -> 480p, 1280:720 -> 720p, 1920:1080 -> 1080p, 3840:2160 -> 2160p).
      - When no scale filter present, output resolution equals the source from
        MediaFiles.ResolutionCategory or a derived bucket from the Resolution string.
      - Compute EstimatedKbps = AVG((NewSizeBytes * 8) / 1024 / (DurationMinutes * 60))
        across rows joined to MediaFiles for DurationMinutes (falls back to
        MediaFilesArchive when MediaFiles row is gone post-replacement).
      - Require >= 10 samples per (codec, resolution, crf) triple.

    Idempotent: only inserts rows that don't already exist (UNIQUE constraint).
    """
    Cursor.execute("SELECT COUNT(*) FROM CrfBitrateEstimates")
    if Cursor.fetchone()[0] > 0:
        print("CrfBitrateEstimates already has rows -- skipping seed")
        return
    print("Computing CrfBitrateEstimates seed rows from TranscodeAttempts history ...")
    # Postgres regex extraction. Output resolution is taken from the scale=W:H
    # filter if present; otherwise NULL (we exclude those rows from the seed
    # because we cannot reliably derive output resolution without the source).
    # NOTE: MediaFilesArchive may have multiple snapshot rows per FilePath
    # (one per replacement event), so we cannot LEFT JOIN it directly without
    # row-multiplying the TranscodeAttempt. Pre-aggregate the duration source
    # tables to one row per FilePath before joining to TranscodeAttempts.
    Cursor.execute("""
        WITH duration_lookup AS (
            SELECT FilePath, MAX(DurationMinutes) AS duration_min
            FROM (
                SELECT FilePath, DurationMinutes FROM MediaFiles WHERE DurationMinutes > 0
                UNION ALL
                SELECT FilePath, DurationMinutes FROM MediaFilesArchive WHERE DurationMinutes > 0
            ) AS combined
            GROUP BY FilePath
        ),
        parsed AS (
            SELECT
                ta.Id,
                LOWER((regexp_match(ta.FFpmpegCommand, '-c:v\\s+(\\S+)'))[1]) AS codec,
                CAST((regexp_match(ta.FFpmpegCommand, '-crf\\s+(\\d+)'))[1] AS INT) AS crf,
                (regexp_match(ta.FFpmpegCommand, 'scale=(\\d+):(\\d+)'))[2] AS scale_h,
                ta.NewSizeBytes,
                dl.duration_min
            FROM TranscodeAttempts ta
            LEFT JOIN duration_lookup dl ON dl.FilePath = ta.FilePath
            WHERE ta.Success = true
              AND ta.NewSizeBytes IS NOT NULL
              AND ta.NewSizeBytes > 0
              AND ta.FFpmpegCommand LIKE '%-c:v%'
              AND ta.FFpmpegCommand LIKE '%-crf%'
              AND ta.FFpmpegCommand NOT LIKE '%-c:v copy%'
        ),
        with_resolution AS (
            SELECT
                codec,
                crf,
                CASE
                    WHEN scale_h::INT = 480 THEN '480p'
                    WHEN scale_h::INT = 720 THEN '720p'
                    WHEN scale_h::INT = 1080 THEN '1080p'
                    WHEN scale_h::INT = 2160 THEN '2160p'
                    ELSE NULL
                END AS resolution,
                NewSizeBytes,
                duration_min
            FROM parsed
            WHERE scale_h IS NOT NULL
              AND duration_min IS NOT NULL
              AND duration_min > 0
              AND codec IS NOT NULL
              AND crf IS NOT NULL
        ),
        aggregated AS (
            SELECT
                codec,
                resolution,
                crf,
                COUNT(*) AS n,
                ROUND(AVG((NewSizeBytes::numeric * 8.0 / 1024.0) / (duration_min * 60.0))) AS estimated_kbps
            FROM with_resolution
            WHERE resolution IS NOT NULL
            GROUP BY codec, resolution, crf
            HAVING COUNT(*) >= 10
        )
        INSERT INTO CrfBitrateEstimates (Codec, Resolution, Crf, EstimatedKbps, Source)
        SELECT codec, resolution, crf, estimated_kbps::INTEGER, 'HistoricalSeed'
        FROM aggregated
        ORDER BY codec, resolution, crf
    """)
    Cursor.execute("SELECT COUNT(*) FROM CrfBitrateEstimates WHERE Source='HistoricalSeed'")
    print(f"  seeded {Cursor.fetchone()[0]} rows from history.")


def Summary(Cursor):
    print("\n--- Summary ---")
    for Table in ('QueueAdmissionConfig', 'CrfBitrateEstimates', 'CodecCompatibility'):
        Cursor.execute(f"SELECT COUNT(*) FROM {Table}")
        print(f"  {Table}: {Cursor.fetchone()[0]} rows")
    Cursor.execute("SELECT MinTranscodeSavingsMB, MissingEstimatePolicy FROM QueueAdmissionConfig WHERE Id=1")
    Row = Cursor.fetchone()
    if Row:
        print(f"  QueueAdmissionConfig row: MinTranscodeSavingsMB={Row[0]}, MissingEstimatePolicy='{Row[1]}'")
    Cursor.execute("SELECT Codec, Resolution, Crf, EstimatedKbps FROM CrfBitrateEstimates ORDER BY Codec, Resolution, Crf")
    Rows = Cursor.fetchall()
    if Rows:
        print(f"  CrfBitrateEstimates seed sample (first 10):")
        for Row in Rows[:10]:
            print(f"    {Row[0]:<12} {Row[1]:<6} crf={Row[2]:<3} -> {Row[3]} kbps")


def RunMigration():
    Conn = GetConnection()
    Cur = Conn.cursor()
    try:
        CreateQueueAdmissionConfig(Cur)
        CreateCrfBitrateEstimates(Cur)
        CreateCodecCompatibility(Cur)
        Conn.commit()

        SeedQueueAdmissionConfig(Cur)
        SeedCodecCompatibility(Cur)
        SeedCrfBitrateEstimatesFromHistory(Cur)
        Conn.commit()

        Summary(Cur)
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
