import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


NVENC_CANARY = 'NVENC AV1 CANARY'
QSV_CANARY = 'QSV AV1 CANARY'
# from: C:\Code\MediaVortex\.claude\directive.md -- directive C12 live-action Tier 1 kbps
NVENC_TIER1_TARGETKBPS = {'480p': 400, '720p': 900, '1080p': 1800, '2160p': 4000}
QSV_TIER1_ICQ = 34


# directive: transcode-flow-canonical | # see transcode.ST5
def EnsureProfileNameUnique(Db: DatabaseService) -> None:
    Rows = Db.ExecuteQuery(
        "SELECT 1 FROM pg_constraint WHERE conname = %s",
        ('profiles_profilename_unique',),
    )
    if not Rows:
        Db.ExecuteNonQuery(
            "ALTER TABLE Profiles ADD CONSTRAINT profiles_profilename_unique UNIQUE (ProfileName)"
        )


# directive: transcode-flow-canonical | # see transcode.ST5
def EnsureProfileThresholdsUnique(Db: DatabaseService) -> None:
    Rows = Db.ExecuteQuery(
        "SELECT 1 FROM pg_constraint WHERE conname = %s",
        ('profilethresholds_profile_res_unique',),
    )
    if not Rows:
        Db.ExecuteNonQuery(
            "ALTER TABLE ProfileThresholds ADD CONSTRAINT profilethresholds_profile_res_unique "
            "UNIQUE (ProfileId, Resolution)"
        )


# directive: transcode-flow-canonical | # see transcode.ST5
def UpsertTier1Profile(Db: DatabaseService, Family: str, ProfileName: str, Codec: str,
                      UseNvidia: int, UseIntel: int, Preset: int) -> int:
    Db.ExecuteNonQuery(
        "INSERT INTO Profiles (ProfileName, Codec, Preset, RateControlMode, "
        "  UseNvidiaHardware, UseIntelHardware, Tune, Multipass, PixelFormat, "
        "  Container, FastStart, StreamCodecName, TargetResolutionCategory, "
        "  AllowUpscale, FilmGrain, YadifMode, TargetAudioKbps, "
        "  Family, QualityTier, ContentClass, Active) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (ProfileName) DO NOTHING",
        (
            ProfileName, Codec, Preset,
            'vbr' if Family == NVENC_CANARY else 'icq',
            UseNvidia, UseIntel,
            'hq' if Family == NVENC_CANARY else None,
            'fullres' if Family == NVENC_CANARY else None,
            'p010le', 'mp4', True, 'av1', '480p',
            False, 0, 1, 128,
            Family, 1, 'live_action', True,
        ),
    )
    Row = Db.ExecuteQuery("SELECT Id FROM Profiles WHERE ProfileName = %s", (ProfileName,))
    Id = int(Row[0]['id'])
    print(f"Ensured Profile Id={Id} ({ProfileName})")
    return Id


# directive: transcode-flow-canonical | # see transcode.ST5
def UpsertThresholdRow(Db: DatabaseService, ProfileId: int, Resolution: str,
                     TargetKbps, IcqQ) -> None:
    Db.ExecuteNonQuery(
        "INSERT INTO ProfileThresholds (ProfileId, Resolution, TargetKbps, IcqQ, MaxBitrateMultiplier) "
        "VALUES (%s, %s, %s, %s, %s) "
        "ON CONFLICT (ProfileId, Resolution) DO UPDATE SET TargetKbps = EXCLUDED.TargetKbps, IcqQ = EXCLUDED.IcqQ",
        (ProfileId, Resolution, TargetKbps, IcqQ, 2.0),
    )
    print(f"  Ensured PT for ProfileId={ProfileId} Res={Resolution} TargetKbps={TargetKbps} IcqQ={IcqQ}")


# directive: transcode-flow-canonical | # see transcode.ST5
def AddNvencTier1(Db: DatabaseService) -> None:
    Id = UpsertTier1Profile(
        Db, NVENC_CANARY, 'NVENC AV1 P7 CANARY Tier 1 -480p', 'av1_nvenc',
        UseNvidia=1, UseIntel=0, Preset=7,
    )
    for Res, Kbps in NVENC_TIER1_TARGETKBPS.items():
        UpsertThresholdRow(Db, Id, Res, TargetKbps=Kbps, IcqQ=None)


# directive: transcode-flow-canonical | # see transcode.ST5
def AddQsvTier1(Db: DatabaseService) -> None:
    Id = UpsertTier1Profile(
        Db, QSV_CANARY, 'QSV AV1 P1 CANARY Tier 1 -480p', 'av1_qsv',
        UseNvidia=0, UseIntel=1, Preset=1,
    )
    for Res in NVENC_TIER1_TARGETKBPS.keys():
        UpsertThresholdRow(Db, Id, Res, TargetKbps=None, IcqQ=QSV_TIER1_ICQ)


# directive: transcode-flow-canonical | # see transcode.ST5
def Summary(Db: DatabaseService) -> None:
    print("\n--- Summary ---")
    Rows = Db.ExecuteQuery(
        "SELECT p.Family, p.QualityTier, COUNT(*) AS n "
        "FROM Profiles p "
        "WHERE p.Family IN (%s, %s) "
        "GROUP BY p.Family, p.QualityTier ORDER BY p.Family, p.QualityTier",
        (NVENC_CANARY, QSV_CANARY),
    )
    for R in Rows:
        print(f"  {R['family']} Tier {R['qualitytier']}: {R['n']} profile(s)")


# directive: transcode-flow-canonical | # see transcode.ST5
def RunMigration() -> None:
    Db = DatabaseService()
    EnsureProfileNameUnique(Db)
    EnsureProfileThresholdsUnique(Db)
    AddNvencTier1(Db)
    AddQsvTier1(Db)
    Summary(Db)


if __name__ == '__main__':
    RunMigration()
