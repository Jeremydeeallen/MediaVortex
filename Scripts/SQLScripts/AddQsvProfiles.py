# Seeds two av1_qsv production profiles + per-resolution thresholds. # from: Docs/superpowers/specs/2026-06-29-wakko-arc-b580-onboarding-design.md ; BUG-0071 (extbrc+look_ahead crashes Arc B580 libmfx-gen 2.16)
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


QSV_PROFILE_PARITY = "QSV AV1 CANARY VBR -720p"
QSV_PROFILE_HQ = "QSV AV1 CANARY VBR -720p HQ"

LOUDNORM_LINEAR = "loudnorm=I=-23:LRA=15.00:TP=-2:linear=true"

# Profile rows starting params per design spec. # from: Docs/superpowers/specs/2026-06-29-wakko-arc-b580-onboarding-design.md
PROFILE_DEFS = [
    (QSV_PROFILE_PARITY, "Arc B580 AV1 QSV; filesize parity with NVENC P7 -720p; +15% bitrate envelope vs NVENC for VMAF parity.", 480, 900),
    (QSV_PROFILE_HQ,     "Arc B580 AV1 QSV; HQ tier; mirrors NVENC P6 -720p HQ envelope ceiling.",                                   480, 1200),
]

# Per-source-resolution thresholds.
THRESHOLD_TIERS = [
    ("2160p", "720p",            720),
    ("1080p", "720p",            720),
    ("720p",  "No downscaling",  720),
    ("480p",  "No downscaling",  480),
]


def UpsertProfile(Db, Name, Description):
    Existing = Db.ExecuteQuery("SELECT Id FROM Profiles WHERE ProfileName = %s", (Name,))
    if Existing:
        Db.ExecuteNonQuery(
            "UPDATE Profiles SET "
            " Description=%s, Codec='av1_qsv', Preset=%s, FilmGrain=%s, "
            " UseNvidiaHardware=0, UseIntelHardware=1, "
            " Tune=NULL, Multipass=NULL, PixelFormat=%s, "
            " AudioCodec=%s, AudioBitrateKbps=%s, AudioChannels=%s, AudioFilter=%s, "
            " Container=%s, FastStart=TRUE, RateControlMode='vbr', "
            " LowPower=%s, "
            " Draft=FALSE, Active=TRUE "
            "WHERE ProfileName=%s",
            (Description, 1, 0, 'p010le', 'aac', 96, 2, LOUDNORM_LINEAR, 'mp4', 0, Name),
        )
        return Existing[0]['id']
    Db.ExecuteNonQuery(
        "INSERT INTO Profiles "
        "(ProfileName, Description, Codec, Preset, FilmGrain, "
        " UseNvidiaHardware, UseIntelHardware, "
        " Tune, Multipass, PixelFormat, "
        " AudioCodec, AudioBitrateKbps, AudioChannels, AudioFilter, "
        " Container, FastStart, RateControlMode, LowPower, "
        " Draft, Active, SortOrder) "
        "VALUES (%s, %s, 'av1_qsv', %s, %s, 0, 1, NULL, NULL, %s, "
        "        %s, %s, %s, %s, %s, TRUE, 'vbr', %s, FALSE, TRUE, "
        "        (SELECT COALESCE(MAX(SortOrder),0)+1 FROM Profiles)) "
        "ON CONFLICT (ProfileName) DO NOTHING",
        (Name, Description, 1, 0, 'p010le', 'aac', 96, 2, LOUDNORM_LINEAR, 'mp4', 0),
    )
    Inserted = Db.ExecuteQuery("SELECT Id FROM Profiles WHERE ProfileName = %s", (Name,))
    return Inserted[0]['id'] if Inserted else None


def UpsertThreshold(Db, ProfileId, Resolution, TranscodeDownTo, ScaleHeight, MinKbps, MaxKbps):
    # BUG-0071: qsvextbrc, qsvlookaheaddepth, qsvbstrategy must stay NULL (crash on long encodes).
    Existing = Db.ExecuteQuery(
        "SELECT Id FROM ProfileThresholds WHERE ProfileId=%s AND Resolution=%s",
        (ProfileId, Resolution),
    )
    if Existing:
        Db.ExecuteNonQuery(
            "UPDATE ProfileThresholds SET "
            " TranscodeDownTo=%s, ScaleHeight=%s, "
            " SourceBitratePercent=%s, MinBitrateKbps=%s, MaxBitrateKbps=%s, MaxBitrateMultiplier=%s, "
            " VideoBitrateKbps=%s, AudioBitrateKbps=%s, "
            " FallbackVideoBitrateKbps=%s, FallbackAudioBitrateKbps=%s, "
            " Under30MinMB=%s, Under65MinMB=%s, Over65MinMB=%s, "
            " BFrames=%s, ContainerType=%s, "
            " QsvExtBrc=NULL, QsvAdaptiveI=%s, QsvAdaptiveB=%s, QsvLookaheadDepth=NULL, "
            " QsvBStrategy=NULL, QsvTileCols=%s, QsvTileRows=%s "
            "WHERE Id=%s",
            (TranscodeDownTo, ScaleHeight, 30, MinKbps, MaxKbps, 2.0,
             0, 0, 0, 0, 0, 0, 0,
             7, 'mp4',
             1, 1, 1, 1,
             Existing[0]['id']),
        )
        return Existing[0]['id']
    Db.ExecuteNonQuery(
        "INSERT INTO ProfileThresholds "
        "(ProfileId, Resolution, TranscodeDownTo, ScaleHeight, "
        " SourceBitratePercent, MinBitrateKbps, MaxBitrateKbps, MaxBitrateMultiplier, "
        " VideoBitrateKbps, AudioBitrateKbps, "
        " FallbackVideoBitrateKbps, FallbackAudioBitrateKbps, "
        " Under30MinMB, Under65MinMB, Over65MinMB, "
        " BFrames, ContainerType, "
        " QsvAdaptiveI, QsvAdaptiveB, QsvTileCols, QsvTileRows) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT DO NOTHING",
        (ProfileId, Resolution, TranscodeDownTo, ScaleHeight,
         30, MinKbps, MaxKbps, 2.0,
         0, 0, 0, 0, 0, 0, 0,
         7, 'mp4',
         1, 1, 1, 1),
    )


def Main():
    Db = DatabaseService()
    for (Name, Description, MinKbps, MaxKbps) in PROFILE_DEFS:
        print(f"=== {Name} ===")
        Pid = UpsertProfile(Db, Name, Description)
        if Pid is None:
            print(f"  ERROR -- profile id not resolved for '{Name}'.")
            sys.exit(1)
        for (Resolution, TDownTo, ScaleH) in THRESHOLD_TIERS:
            UpsertThreshold(Db, Pid, Resolution, TDownTo, ScaleH, MinKbps, MaxKbps)
            print(f"  threshold {Resolution} -> {TDownTo} (scale={ScaleH}, min={MinKbps}, max={MaxKbps})")
    print()
    Verify = Db.ExecuteQuery(
        "SELECT p.ProfileName, COUNT(pt.Id) AS thresholds "
        "FROM Profiles p LEFT JOIN ProfileThresholds pt ON pt.ProfileId=p.Id "
        "WHERE p.ProfileName IN (%s, %s) "
        "GROUP BY p.ProfileName ORDER BY p.ProfileName",
        (QSV_PROFILE_PARITY, QSV_PROFILE_HQ),
    )
    for Row in Verify:
        print(f"  {Row['profilename']}: {Row['thresholds']} thresholds")


if __name__ == "__main__":
    Main()
