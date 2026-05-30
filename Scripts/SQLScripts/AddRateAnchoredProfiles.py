"""Seed VBR + anime production profiles per
Features/Profiles/nvenc-rate-anchored.feature.md C10. Idempotent.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


PROFILES = [
    {
        "ProfileName": "NVENC AV1 P7 VBR 30pct -720p",
        "Description": "Rate-anchored: target 30% of source bitrate, capped [350,2500] kbps. For low/mid-bitrate sources where CQ32 would balloon. Downscale 1080p/2160p -> 720p.",
        "Codec": "av1_nvenc", "Preset": 7, "FilmGrain": 0,
        "UseNvidiaHardware": 1, "RateControlMode": "vbr",
        "Thresholds": [
            ("480p",  "No downscaling", None,   30, 200, 1500, None),
            ("720p",  "No downscaling", None,   30, 350, 2500, None),
            ("1080p", "720p",           None,   30, 350, 2500, None),
            ("2160p", "720p",           None,   30, 350, 2500, None),
        ],
    },
    {
        "ProfileName": "NVENC AV1 P7 VBR 30pct -480p",
        "Description": "Rate-anchored aggressive: 30% of source, capped [200,1500] kbps. Downscale 1080p/2160p -> 480p. Storage-optimized.",
        "Codec": "av1_nvenc", "Preset": 7, "FilmGrain": 0,
        "UseNvidiaHardware": 1, "RateControlMode": "vbr",
        "Thresholds": [
            ("480p",  "No downscaling", None,   30, 150, 1000, None),
            ("720p",  "480p",           None,   30, 200, 1500, None),
            ("1080p", "480p",           None,   30, 200, 1500, None),
            ("2160p", "480p",           None,   30, 200, 1500, None),
        ],
    },
    {
        "ProfileName": "NVENC AV1 P7 HQ CQ29 G480 ANIME -720p",
        "Description": "Anime-tuned: CQ29 (better quality on simple content), tune=hq, long GOP (480) for held-frame sequences.",
        "Codec": "av1_nvenc", "Preset": 7, "FilmGrain": 0,
        "UseNvidiaHardware": 1, "RateControlMode": "cq",
        "Thresholds": [
            ("480p",  "No downscaling", 29,     None, None, None, 480),
            ("720p",  "No downscaling", 29,     None, None, None, 480),
            ("1080p", "720p",           29,     None, None, None, 480),
            ("2160p", "720p",           29,     None, None, None, 480),
        ],
    },
]


def Run() -> int:
    Db = DatabaseService()
    Inserted = 0
    for P in PROFILES:
        Existing = Db.ExecuteQuery(
            "SELECT Id FROM Profiles WHERE ProfileName = %s",
            (P["ProfileName"],),
        )
        if Existing:
            ProfileId = Existing[0]["Id"]
            print(f"  Exists: {P['ProfileName']} (Id={ProfileId})")
            continue
        Db.ExecuteNonQuery(
            "INSERT INTO Profiles "
            "(ProfileName, Description, Codec, Preset, FilmGrain, UseNvidiaHardware, RateControlMode) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (P["ProfileName"], P["Description"], P["Codec"], P["Preset"],
             P["FilmGrain"], P["UseNvidiaHardware"], P["RateControlMode"]),
        )
        ProfileRow = Db.ExecuteQuery(
            "SELECT Id FROM Profiles WHERE ProfileName = %s",
            (P["ProfileName"],),
        )
        ProfileId = ProfileRow[0]["Id"]
        for (Res, Tdt, Qual, Pct, MinK, MaxK, Gop) in P["Thresholds"]:
            Db.ExecuteNonQuery(
                "INSERT INTO ProfileThresholds "
                "(ProfileId, Resolution, TranscodeDownTo, Quality, ContainerType, "
                " SourceBitratePercent, MinBitrateKbps, MaxBitrateKbps, Gop) "
                "VALUES (%s, %s, %s, %s, 'mp4', %s, %s, %s, %s)",
                (ProfileId, Res, Tdt, Qual, Pct, MinK, MaxK, Gop),
            )
        Inserted += 1
        print(f"  Inserted: {P['ProfileName']} (Id={ProfileId}, 4 thresholds)")
    print(f"\nDone. {Inserted} new profile(s).")
    return 0


if __name__ == "__main__":
    sys.exit(Run())
