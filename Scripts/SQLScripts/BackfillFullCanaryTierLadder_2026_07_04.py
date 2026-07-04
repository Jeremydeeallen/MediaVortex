#!/usr/bin/env python3

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


NVENC_CANARY = 'NVENC AV1 CANARY'
QSV_CANARY = 'QSV AV1 CANARY'
LIVE_ACTION = 'live_action'
RESOLUTIONS = ['480p', '720p', '1080p', '2160p']
TIERS = [1, 2, 3, 4, 5]


NVENC_TARGETKBPS = {
    '480p':  {1:  400, 2:  550, 3:  700, 4:   900, 5:  1200},
    '720p':  {1:  900, 2: 1400, 3: 1900, 4:  2500, 5:  3200},
    '1080p': {1: 1800, 2: 2400, 3: 3200, 4:  4200, 5:  5500},
    '2160p': {1: 4000, 2: 6000, 3: 8500, 4: 12000, 5: 18000},
}


QSV_ICQ = {1: 34, 2: 30, 3: 28, 4: 26, 5: 22}


RES_RANK = {'480p': 1, '720p': 2, '1080p': 3, '2160p': 4}


# directive: transcode-flow-canonical | # see transcode.ST5
def BuildProfileName(Family: str, Tier: int, TargetRes: str) -> str:
    if Family == NVENC_CANARY:
        Preset = 'P6' if TargetRes == '2160p' else 'P7'
        return f'NVENC AV1 {Preset} CANARY Tier {Tier} -{TargetRes}'
    return f'QSV AV1 P1 CANARY Tier {Tier} -{TargetRes}'


# directive: transcode-flow-canonical | # see transcode.ST5
def UpsertProfile(Db: DatabaseService, Family: str, Tier: int, TargetRes: str) -> int:
    ProfileName = BuildProfileName(Family, Tier, TargetRes)
    IsNvenc = (Family == NVENC_CANARY)
    Preset = 6 if (IsNvenc and TargetRes == '2160p') else (7 if IsNvenc else 1)
    Codec = 'av1_nvenc' if IsNvenc else 'av1_qsv'
    RateControlMode = 'vbr' if IsNvenc else 'icq'
    Tune = 'hq' if IsNvenc else None
    Multipass = 'fullres' if IsNvenc else None
    UseNvidia = 1 if IsNvenc else 0
    UseIntel = 0 if IsNvenc else 1
    Db.ExecuteNonQuery(
        "INSERT INTO Profiles ("
        "  ProfileName, Codec, Preset, FilmGrain, YadifMode, YadifParity, YadifDeint, UseNvidiaHardware, "
        "  RateControlMode, Tune, Multipass, PixelFormat, Container, FastStart, QualityTestRequired, "
        "  Draft, Active, StreamCodecName, TargetResolutionCategory, AllowUpscale, TargetAudioKbps, "
        "  UseIntelHardware, Family, QualityTier, ContentClass, SortOrder"
        ") VALUES ("
        "  %s, %s, %s, 0, 1, 1, 1, %s, %s, %s, %s, 'p010le', 'mp4', TRUE, TRUE, TRUE, TRUE, 'av1', %s, FALSE, 128, %s, %s, %s, %s, 0"
        ") ON CONFLICT (ProfileName) DO NOTHING",
        (ProfileName, Codec, Preset, UseNvidia, RateControlMode, Tune, Multipass, TargetRes, UseIntel, Family, Tier, LIVE_ACTION),
    )
    Rows = Db.ExecuteQuery(
        "SELECT Id FROM Profiles WHERE ProfileName = %s LIMIT 1",
        (ProfileName,),
    )
    return int(Rows[0]['id'])


# directive: transcode-flow-canonical | # see transcode.ST5
def _ResolveKnobsForSource(Family: str, Tier: int, TargetRes: str, SourceRes: str):
    TargetRank = RES_RANK[TargetRes]
    SourceRank = RES_RANK[SourceRes]
    if SourceRank > TargetRank:
        return (TargetRes, NVENC_TARGETKBPS[TargetRes][Tier], QSV_ICQ[Tier] if Family == QSV_CANARY else None)
    if SourceRank == TargetRank:
        return ('No downscaling', NVENC_TARGETKBPS[TargetRes][Tier], QSV_ICQ[Tier] if Family == QSV_CANARY else None)
    return ('No downscaling', NVENC_TARGETKBPS[SourceRes][Tier], QSV_ICQ[Tier] if Family == QSV_CANARY else None)


# directive: transcode-flow-canonical | # see transcode.ST5
def UpsertProfileThresholds(Db: DatabaseService, ProfileId: int, Family: str, Tier: int, TargetRes: str) -> None:
    for SourceRes in RESOLUTIONS:
        TranscodeDownTo, TargetKbps, IcqQ = _ResolveKnobsForSource(Family, Tier, TargetRes, SourceRes)
        TargetVideoKbps = TargetKbps if Family == NVENC_CANARY else 0
        Db.ExecuteNonQuery(
            "INSERT INTO ProfileThresholds ("
            "  ProfileId, Resolution, Under30MinMB, Under65MinMB, Over65MinMB, VideoBitrateKbps, AudioBitrateKbps, "
            "  FallbackVideoBitrateKbps, FallbackAudioBitrateKbps, TranscodeDownTo, Quality, KeepSource, ContainerType, "
            "  MaxBitrateMultiplier, TargetKbps, IcqQ"
            ") VALUES ("
            "  %s, %s, 0, 0, 0, %s, 128, 0, 0, %s, NULL, FALSE, 'mp4', 2.00, %s, %s"
            ") ON CONFLICT (ProfileId, Resolution) DO UPDATE SET "
            "  TranscodeDownTo = EXCLUDED.TranscodeDownTo, TargetKbps = EXCLUDED.TargetKbps, IcqQ = EXCLUDED.IcqQ",
            (ProfileId, SourceRes, TargetVideoKbps, TranscodeDownTo, TargetKbps, IcqQ),
        )


# directive: transcode-flow-canonical | # see transcode.ST5
def Summary(Db: DatabaseService) -> None:
    print("\n--- Summary ---")
    Rows = Db.ExecuteQuery(
        "SELECT Family, ContentClass, COUNT(*) AS n FROM Profiles WHERE Family IN (%s, %s) GROUP BY Family, ContentClass ORDER BY Family, ContentClass",
        (NVENC_CANARY, QSV_CANARY),
    )
    for R in Rows:
        print(f"  {R['family']} / {R['contentclass']}: {R['n']} profiles")
    Rows = Db.ExecuteQuery(
        "SELECT COUNT(*) AS n FROM ProfileThresholds pt JOIN Profiles p ON p.Id = pt.ProfileId WHERE p.Family IN (%s, %s)",
        (NVENC_CANARY, QSV_CANARY),
    )
    print(f"  ProfileThresholds rows on CANARY families: {int(Rows[0]['n'])}")


# directive: transcode-flow-canonical | # see transcode.ST5
def RunMigration() -> None:
    Db = DatabaseService()
    for Family in (NVENC_CANARY, QSV_CANARY):
        for Tier in TIERS:
            for TargetRes in RESOLUTIONS:
                ProfileId = UpsertProfile(Db, Family, Tier, TargetRes)
                UpsertProfileThresholds(Db, ProfileId, Family, Tier, TargetRes)
    Summary(Db)


if __name__ == '__main__':
    RunMigration()
