"""Add NVENC AV1 production support.

Idempotent. Safe to re-run.

Adds:
1. Workers.nvenccapable boolean column (default FALSE).
2. Marks I9-2024 as NvencCapable=TRUE (the operator's RTX 4060 Ti host).
3. Two new Profiles for NVENC AV1 production routing:
   - "NVENC AV1 P7 UHQ CQ32 -480p"  -- downscales to 480p (storage-optimized)
   - "NVENC AV1 P7 UHQ CQ32 -720p"  -- downscales to 720p (quality-optimized)
   Both have UseNvidiaHardware=1. The CommandBuilder NVENC branch consumes
   Preset + Quality from the profile and hardcodes the rest of the
   shootout-winner knob set (tune=uhq, multipass=fullres, rc=vbr+cq,
   spatial-aq=1, temporal-aq=1, aq-strength=15, rc-lookahead=32, bf=7,
   b_ref_mode=middle, pix_fmt=p010le).

Source of variant choice: Scripts/Smoke/NvencKnobSweep-1080pTo480p-2026-05-28.shootout.json
Decision evidence: cross-source rollup, nv_cq32_sink variant -- median 14% smaller
than SVT P6 CRF26 reference at -0.47 VMAF Mean, ~1.6x faster wall encode.

Worker routing: queue claim filter (DatabaseManager.ClaimNextPendingTranscodeJob)
gates jobs whose assigned profile has UseNvidiaHardware=1 to workers with
Workers.nvenccapable=TRUE. Non-NVENC profiles still claim normally on any
TranscodeEnabled worker.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


NVENC_PROFILE_480P = "NVENC AV1 P7 UHQ CQ32 -480p"
NVENC_PROFILE_720P = "NVENC AV1 P7 UHQ CQ32 -720p"

# Each tuple: (resolution, quality, transcodedownto)
PROFILE_480P_THRESHOLDS = [
    ("2160p", 32, "480p"),
    ("1080p", 32, "480p"),
    ("720p",  32, "480p"),
    ("480p",  32, "No downscaling"),
]
PROFILE_720P_THRESHOLDS = [
    ("2160p", 32, "720p"),
    ("1080p", 32, "720p"),
    ("720p",  32, "No downscaling"),
    ("480p",  32, "No downscaling"),
]


def AddNvencCapableColumn(Db: DatabaseService) -> None:
    print("[1/4] Adding Workers.nvenccapable column (idempotent)...")
    Db.ExecuteNonQuery(
        "ALTER TABLE Workers ADD COLUMN IF NOT EXISTS nvenccapable boolean DEFAULT FALSE"
    )
    print("       done.")


def MarkI9NvencCapable(Db: DatabaseService) -> None:
    print("[2/4] Marking I9-2024 as NvencCapable=TRUE...")
    Result = Db.ExecuteNonQuery(
        "UPDATE Workers SET nvenccapable = TRUE WHERE workername = %s",
        ("I9-2024",),
    )
    Check = Db.ExecuteQuery(
        "SELECT workername, nvenccapable FROM Workers WHERE workername = %s",
        ("I9-2024",),
    )
    if not Check:
        print("       WARNING: Worker 'I9-2024' not found. Skipping capability mark.")
        return
    print(f"       I9-2024 nvenccapable = {Check[0]['nvenccapable']}")


def UpsertProfile(Db: DatabaseService, ProfileName: str, Codec: str, Preset: int,
                  FilmGrain: int, UseNvidiaHardware: int, Description: str) -> int:
    """Upsert a profile by name. Returns profile id."""
    Existing = Db.ExecuteQuery(
        "SELECT id FROM Profiles WHERE profilename = %s",
        (ProfileName,),
    )
    if Existing:
        Pid = Existing[0]["id"]
        Db.ExecuteNonQuery(
            """UPDATE Profiles
               SET codec=%s, preset=%s, filmgrain=%s, usenvidiahardware=%s,
                   description=%s, lastmodified=CURRENT_TIMESTAMP
               WHERE id=%s""",
            (Codec, Preset, FilmGrain, UseNvidiaHardware, Description, Pid),
        )
        print(f"       updated existing profile id={Pid} '{ProfileName}'")
        return Pid
    Db.ExecuteNonQuery(
        """INSERT INTO Profiles (profilename, codec, preset, filmgrain,
                                 usenvidiahardware, description)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (ProfileName, Codec, Preset, FilmGrain, UseNvidiaHardware, Description),
    )
    Created = Db.ExecuteQuery(
        "SELECT id FROM Profiles WHERE profilename = %s",
        (ProfileName,),
    )
    Pid = Created[0]["id"]
    print(f"       inserted new profile id={Pid} '{ProfileName}'")
    return Pid


def UpsertProfileThresholds(Db: DatabaseService, ProfileId: int,
                            Thresholds: list) -> None:
    """Replace ProfileThresholds rows for the profile. Idempotent."""
    Db.ExecuteNonQuery(
        "DELETE FROM ProfileThresholds WHERE profileid = %s",
        (ProfileId,),
    )
    for Resolution, Quality, TranscodeDownTo in Thresholds:
        Db.ExecuteNonQuery(
            """INSERT INTO ProfileThresholds
               (profileid, resolution, under30minmb, under65minmb, over65minmb,
                videobitratekbps, audiobitratekbps, fallbackvideobitratekbps,
                fallbackaudiobitratekbps, transcodedownto, quality, keepsource,
                containertype)
               VALUES (%s, %s, 0, 0, 0, 0, 0, 0, 0, %s, %s, FALSE, 'mp4')""",
            (ProfileId, Resolution, TranscodeDownTo, Quality),
        )
    print(f"       wrote {len(Thresholds)} ProfileThresholds rows for profile {ProfileId}")


def UpsertAv1NvencCodecFlags(Db: DatabaseService) -> int:
    """Upsert CodecFlags row for av1_nvenc. Worker's GetTranscodingSettings
    requires a CodecFlags row per codec name AND at least one CodecParameters
    row per CodecFlags id, or it returns 'Failed to get transcoding settings'
    without even reaching CommandBuilder. Returns the codecflags id.
    """
    Existing = Db.ExecuteQuery(
        "SELECT id FROM CodecFlags WHERE codecname = %s",
        ("av1_nvenc",),
    )
    if Existing:
        Cid = Existing[0]["id"]
        Db.ExecuteNonQuery(
            """UPDATE CodecFlags SET displayname=%s, presettype='numeric',
                   presetmin=1, presetmax=7, presetdefault=7, presetoptions='',
                   filmgraintype='none', filmgrainmin=0, filmgrainmax=0,
                   filmgraindefault=0, tuneoptions='hq,uhq,ll,ull,lossless',
                   lastmodified=CURRENT_TIMESTAMP
               WHERE id=%s""",
            ("AV1 (NVENC NVIDIA hardware)", Cid),
        )
        print(f"       updated CodecFlags id={Cid} 'av1_nvenc'")
    else:
        Db.ExecuteNonQuery(
            """INSERT INTO CodecFlags (codecname, displayname, presettype,
                   presetmin, presetmax, presetdefault, presetoptions,
                   filmgraintype, filmgrainmin, filmgrainmax, filmgraindefault,
                   tuneoptions)
               VALUES ('av1_nvenc', 'AV1 (NVENC NVIDIA hardware)', 'numeric',
                       1, 7, 7, '', 'none', 0, 0, 0,
                       'hq,uhq,ll,ull,lossless')""",
        )
        Created = Db.ExecuteQuery("SELECT id FROM CodecFlags WHERE codecname='av1_nvenc'")
        Cid = Created[0]["id"]
        print(f"       inserted CodecFlags id={Cid} 'av1_nvenc'")

    # Replace CodecParameters rows for this codec (idempotent).
    Db.ExecuteNonQuery("DELETE FROM CodecParameters WHERE codecflagsid=%s", (Cid,))
    Db.ExecuteNonQuery(
        """INSERT INTO CodecParameters (codecflagsid, parametername, parametertype,
               minvalue, maxvalue, defaultvalue, description, ffmpegflag)
           VALUES
               (%s, 'cq', 'numeric', 0, 63, '32',
                'NVENC quality-anchored VBR target (0-63, lower is higher quality)', '-cq'),
               (%s, 'preset', 'enum', 1, 7, '7',
                'NVENC speed/quality preset p1-p7', '-preset')""",
        (Cid, Cid),
    )
    print(f"       wrote 2 CodecParameters rows for CodecFlags {Cid}")
    return Cid


def AddNvencProfiles(Db: DatabaseService) -> None:
    print(f"[4/5] Upserting profile '{NVENC_PROFILE_480P}'...")
    P480 = UpsertProfile(
        Db, NVENC_PROFILE_480P,
        Codec="av1_nvenc", Preset=7, FilmGrain=0, UseNvidiaHardware=1,
        Description="NVENC AV1 hardware encode, all sources downscaled to 480p. "
                    "CommandBuilder hardcodes: tune=uhq, multipass=fullres, rc=vbr+cq, "
                    "aq-strength=15, rc-lookahead=32, bf=7, b_ref_mode=middle, p010le. "
                    "Source: NvencKnobSweep 2026-05-28 (nv_cq32_sink, -14% size vs SVT P6 CRF26 reference).",
    )
    UpsertProfileThresholds(Db, P480, PROFILE_480P_THRESHOLDS)

    print(f"[5/5] Upserting profile '{NVENC_PROFILE_720P}'...")
    P720 = UpsertProfile(
        Db, NVENC_PROFILE_720P,
        Codec="av1_nvenc", Preset=7, FilmGrain=0, UseNvidiaHardware=1,
        Description="NVENC AV1 hardware encode, sources downscaled to 720p (480p sources stay). "
                    "Same hardcoded knob set as the -480p variant.",
    )
    UpsertProfileThresholds(Db, P720, PROFILE_720P_THRESHOLDS)


def Main():
    Db = DatabaseService()
    AddNvencCapableColumn(Db)
    MarkI9NvencCapable(Db)
    print("[3/5] Upserting CodecFlags + CodecParameters for av1_nvenc...")
    UpsertAv1NvencCodecFlags(Db)
    AddNvencProfiles(Db)
    print()
    print("Done. Verify with:")
    print("  py Scripts/SQLScripts/QueryDatabase.py sql \"SELECT profilename, codec, preset, usenvidiahardware FROM Profiles WHERE usenvidiahardware=1 ORDER BY profilename\"")
    print("  py Scripts/SQLScripts/QueryDatabase.py sql \"SELECT workername, nvenccapable FROM Workers ORDER BY workername\"")


if __name__ == "__main__":
    Main()
