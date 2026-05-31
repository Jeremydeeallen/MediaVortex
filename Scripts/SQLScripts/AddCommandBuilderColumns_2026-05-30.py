import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


# directive: nvenc-rate-anchored-remediation
def Run() -> int:
    Db = DatabaseService()

    ProfileColumns = [
        ("Tune", "TEXT"),
        ("Multipass", "TEXT"),
        ("PixelFormat", "TEXT"),
        ("AudioCodec", "TEXT"),
        ("AudioBitrateKbps", "INTEGER"),
        ("AudioChannels", "INTEGER"),
        ("AudioFilter", "TEXT"),
        ("Container", "TEXT"),
        ("FastStart", "BOOLEAN"),
        ("AqStrength", "INTEGER"),
    ]
    for Name, Type in ProfileColumns:
        Db.ExecuteNonQuery(
            f"ALTER TABLE Profiles ADD COLUMN IF NOT EXISTS {Name} {Type}",
            (),
        )

    ThresholdColumns = [
        ("RcLookahead", "INTEGER"),
        ("BFrames", "INTEGER"),
        ("BRefMode", "TEXT"),
        ("ScaleHeight", "INTEGER"),
        ("PreserveAspect", "BOOLEAN"),
        ("MaxBitrateMultiplier", "NUMERIC(3,2) DEFAULT 2.0"),
    ]
    for Name, Type in ThresholdColumns:
        Db.ExecuteNonQuery(
            f"ALTER TABLE ProfileThresholds ADD COLUMN IF NOT EXISTS {Name} {Type}",
            (),
        )

    Db.ExecuteNonQuery(
        "UPDATE Profiles SET "
        "Tune = COALESCE(Tune, CASE WHEN COALESCE(RateControlMode, 'cq') = 'vbr' THEN 'hq' ELSE 'uhq' END), "
        # from: Models/CommandBuilder.py (legacy line 334: 'uhq' if cq else 'hq')
        "Multipass = COALESCE(Multipass, 'fullres'), "
        # from: Features/Profiles/nvenc-profiles.feature.md (criterion 4 legacy CQ branch)
        "PixelFormat = COALESCE(PixelFormat, 'p010le'), "
        # from: Features/Profiles/nvenc-profiles.feature.md (criterion 5 NVENC pix_fmt)
        "Container = COALESCE(Container, 'mp4'), "
        "FastStart = COALESCE(FastStart, TRUE) "
        "WHERE UseNvidiaHardware = 1",
        (),
    )

    Db.ExecuteNonQuery(
        "UPDATE Profiles SET Tune = 'hq' "
        # from: Models/CommandBuilder.py (legacy line 334: 'hq' branch for vbr)
        "WHERE UseNvidiaHardware = 1 AND RateControlMode = 'vbr' AND Tune = 'uhq'",
        (),
    )

    Db.ExecuteNonQuery(
        "UPDATE Profiles SET AqStrength = 15 "
        # from: Models/CommandBuilder.py (legacy line 374: '-aq-strength', '15' literal for NVENC CQ)
        "WHERE UseNvidiaHardware = 1 AND RateControlMode = 'cq' AND AqStrength IS NULL",
        (),
    )

    Db.ExecuteNonQuery(
        "UPDATE Profiles SET "
        "PixelFormat = COALESCE(PixelFormat, 'yuv420p10le'), "
        # from: Features/Profiles/nvenc-profiles.feature.md (criterion 5 software pix_fmt)
        "Container = COALESCE(Container, 'mp4'), "
        "FastStart = COALESCE(FastStart, TRUE) "
        "WHERE UseNvidiaHardware IS DISTINCT FROM 1",
        (),
    )

    Db.ExecuteNonQuery(
        "UPDATE ProfileThresholds pt SET "
        "RcLookahead = COALESCE(pt.RcLookahead, 32), "
        # from: Features/Profiles/nvenc-profiles.feature.md (criterion 4 rc-lookahead literal)
        "BFrames = COALESCE(pt.BFrames, 7), "
        # from: Features/Profiles/nvenc-profiles.feature.md (criterion 4 bf literal)
        "BRefMode = COALESCE(pt.BRefMode, 'middle') "
        # from: Features/Profiles/nvenc-profiles.feature.md (criterion 4 b_ref_mode literal)
        "FROM Profiles p WHERE pt.ProfileId = p.Id AND p.UseNvidiaHardware = 1",
        (),
    )

    Db.ExecuteNonQuery(
        "UPDATE ProfileThresholds SET MaxBitrateMultiplier = 2.0 "
        # from: Scripts/CodecAnalysis/NvidiaOptimization1.ps1 (CalcMaxRate = CalcBitrate * 2.0)
        "WHERE MaxBitrateMultiplier IS NULL",
        (),
    )

    Db.ExecuteNonQuery(
        "UPDATE ProfileThresholds SET "
        "ScaleHeight = CASE TranscodeDownTo "
        "  WHEN '480p' THEN 480 "
        "  WHEN '720p' THEN 720 "
        "  WHEN '1080p' THEN 1080 "
        "  WHEN '2160p' THEN 2160 "
        "  ELSE NULL END, "
        "PreserveAspect = COALESCE(PreserveAspect, FALSE) "
        "WHERE TranscodeDownTo IS NOT NULL AND TranscodeDownTo <> 'No downscaling'",
        (),
    )

    print("Profiles new columns:")
    for R in Db.ExecuteQuery(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name='profiles' "
        "AND column_name IN ('tune','multipass','pixelformat','audiocodec',"
        "'audiobitratekbps','audiochannels','audiofilter','container','faststart') "
        "ORDER BY column_name",
        (),
    ):
        print(f"  {R.get('column_name')}: {R.get('data_type')}")

    print("ProfileThresholds new columns:")
    for R in Db.ExecuteQuery(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name='profilethresholds' "
        "AND column_name IN ('rclookahead','bframes','brefmode','scaleheight',"
        "'preserveaspect','maxbitratemultiplier') "
        "ORDER BY column_name",
        (),
    ):
        print(f"  {R.get('column_name')}: {R.get('data_type')}")

    Backfilled = Db.ExecuteQuery(
        "SELECT COUNT(*) AS Cnt FROM Profiles WHERE Tune IS NOT NULL",
        (),
    )
    print(f"\nNVENC profiles backfilled (Tune NOT NULL): {Backfilled[0].get('cnt')}")

    return 0


if __name__ == "__main__":
    sys.exit(Run())
