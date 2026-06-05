import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


PROFILE_NAME = "NVENC AV1 P7 CANARY VBR -720p"


# directive: nvenc-rate-anchored-remediation
def Run() -> int:
    Db = DatabaseService()

    Existing = Db.ExecuteQuery(
        "SELECT Id FROM Profiles WHERE ProfileName = %s",
        (PROFILE_NAME,),
    )
    if Existing:
        ProfileId = Existing[0]["Id"]
        print(f"Profile exists: {PROFILE_NAME} (Id={ProfileId}) -- idempotent no-op")
        return 0

    # allow: R11 -- no UNIQUE on Profiles.ProfileName; pre-check at line 16 provides idempotency, matches AddRateAnchoredProfiles.py convention
    Db.ExecuteNonQuery(
        "INSERT INTO Profiles "
        "(ProfileName, Description, Codec, Preset, FilmGrain, UseNvidiaHardware, "
        " RateControlMode, Tune, Multipass, PixelFormat, "
        " AudioCodec, AudioBitrateKbps, AudioChannels, AudioFilter, "
        " Container, FastStart) "
        # from: Scripts/CodecAnalysis/NvidiaOptimization1.ps1 (lines 123-142 verbatim canary args)
        "VALUES (%s, %s, 'av1_nvenc', 7, 0, 1, "
        "        'vbr', 'hq', 'fullres', 'p010le', "
        "        'aac', 96, 2, 'loudnorm=I=-23:LRA=15.00:TP=-2:linear=true', "
        "        'mp4', TRUE)",
        (
            PROFILE_NAME,
            "Canary VBR profile reproducing NvidiaOptimization1.ps1 verbatim. "
            "AAC stereo 96kbps + single-pass linear loudnorm. Source of truth: "
            "Scripts/CodecAnalysis/NvidiaOptimization1.ps1. Operator-validated VMAF 92.92.",
        ),
    )

    Row = Db.ExecuteQuery(
        "SELECT Id FROM Profiles WHERE ProfileName = %s",
        (PROFILE_NAME,),
    )
    ProfileId = Row[0]["Id"]

    Thresholds = [
        ("480p",  "No downscaling", 480),
        ("720p",  "No downscaling", 720),
        ("1080p", "720p",           720),
        ("2160p", "720p",           720),
    ]

    for (Res, TranscodeDownTo, ScaleHeight) in Thresholds:
        # allow: R11 -- no UNIQUE on (ProfileId, Resolution); pre-check at line 16 short-circuits if profile exists, matches AddRateAnchoredProfiles.py convention
        Db.ExecuteNonQuery(
            "INSERT INTO ProfileThresholds "
            "(ProfileId, Resolution, TranscodeDownTo, Quality, ContainerType, "
            " SourceBitratePercent, MinBitrateKbps, MaxBitrateKbps, MaxBitrateMultiplier, "
            " RcLookahead, BFrames, BRefMode, ScaleHeight) "
            "VALUES (%s, %s, %s, NULL, 'mp4', "
            "        30, 350, 600, 2.0, "
            "        20, 4, 'middle', %s)",
            (ProfileId, Res, TranscodeDownTo, ScaleHeight),
        )

    print(f"Inserted: {PROFILE_NAME} (Id={ProfileId}) + 4 threshold rows")

    Verify = Db.ExecuteQuery(
        "SELECT p.ProfileName, p.Tune, p.Multipass, p.PixelFormat, "
        "       p.AudioCodec, p.AudioBitrateKbps, p.AudioChannels, p.AudioFilter, "
        "       p.Container, p.FastStart, "
        "       pt.Resolution, pt.SourceBitratePercent, pt.MinBitrateKbps, "
        "       pt.MaxBitrateKbps, pt.MaxBitrateMultiplier, pt.RcLookahead, "
        "       pt.BFrames, pt.BRefMode, pt.ScaleHeight "
        "FROM Profiles p JOIN ProfileThresholds pt ON pt.ProfileId = p.Id "
        "WHERE p.ProfileName = %s ORDER BY pt.Resolution",
        (PROFILE_NAME,),
    )
    for R in Verify:
        print(f"  {R.get('resolution')}: bitrate={R.get('sourcebitratepercent')}%/"
              f"[{R.get('minbitratekbps')},{R.get('maxbitratekbps')}]k x{R.get('maxbitratemultiplier')}, "
              f"la={R.get('rclookahead')} bf={R.get('bframes')} brm={R.get('brefmode')}, "
              f"scale={R.get('scaleheight')}")

    return 0


if __name__ == "__main__":
    sys.exit(Run())
