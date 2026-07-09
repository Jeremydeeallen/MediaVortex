# directive: transcode-flow-canonical | # see transcode-flow-canonical.C25
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


# from: Scripts/SQLScripts/CollapseProfilesToTierLadder_2026_07_09.py
TARGET_KBPS = {
    ('480p', 1): 350,   ('480p', 2): 500,   ('480p', 3): 650,   ('480p', 4): 800,    ('480p', 5): 1100,
    ('720p', 1): 800,   ('720p', 2): 1250,  ('720p', 3): 1700,  ('720p', 4): 2300,   ('720p', 5): 3000,
    ('1080p', 1): 1600, ('1080p', 2): 2200, ('1080p', 3): 3000, ('1080p', 4): 4000,  ('1080p', 5): 5200,
    ('2160p', 1): 3600, ('2160p', 2): 5500, ('2160p', 3): 8000, ('2160p', 4): 11000, ('2160p', 5): 16500,
}


# from: Scripts/SQLScripts/CollapseProfilesToTierLadder_2026_07_09.py
ICQ_LADDER = {1: 34, 2: 30, 3: 28, 4: 26, 5: 22}


RESOLUTIONS = ('480p', '720p', '1080p', '2160p')


# directive: transcode-flow-canonical
def Main():
    Db = DatabaseService()
    Rows = Db.ExecuteQuery(
        "SELECT Id, QualityTier FROM Profiles WHERE Family = 'ANY' AND QualityLabel IS NOT NULL "
        "ORDER BY QualityTier"
    )
    TierToProfileId = {int(R['QualityTier']): int(R['Id']) for R in Rows}
    if len(TierToProfileId) != 5:
        print(f"ERROR: expected 5 tier profiles; got {len(TierToProfileId)}. Migration aborted.")
        sys.exit(2)
    Inserted = 0
    Updated = 0
    for Tier, ProfileId in TierToProfileId.items():
        for Res in RESOLUTIONS:
            Kbps = TARGET_KBPS[(Res, Tier)]
            IcqQ = ICQ_LADDER[Tier]
            Existing = Db.ExecuteQuery(
                "SELECT Id FROM ProfileThresholds WHERE ProfileId = %s AND Resolution = %s AND ContentClass = 'animation'",
                (ProfileId, Res),
            )
            if Existing:
                Db.ExecuteNonQuery(
                    "UPDATE ProfileThresholds SET TargetKbps = %s, IcqQ = %s, "
                    "  VideoBitrateKbps = %s, FallbackVideoBitrateKbps = %s, "
                    "  TranscodeDownTo = %s, ContainerType = 'mp4' "
                    "WHERE Id = %s",
                    (Kbps, IcqQ, Kbps, Kbps, Res, Existing[0]['Id']),
                )
                Updated += 1
                continue
            # from: Scripts/SQLScripts/CollapseProfilesToTierLadder_2026_07_09.py
            InsertSql = (
                "INSERT INTO ProfileThresholds (ProfileId, Resolution, ContentClass, Under30MinMB, "
                "Under65MinMB, Over65MinMB, VideoBitrateKbps, AudioBitrateKbps, FallbackVideoBitrateKbps, "
                "FallbackAudioBitrateKbps, TranscodeDownTo, Quality, KeepSource, ContainerType, TargetKbps, IcqQ) "
                # from: Scripts/SQLScripts/CollapseProfilesToTierLadder_2026_07_09.py
                "VALUES (%s, %s, 'animation', 0, 0, 0, %s, 192, %s, 192, %s, 0, FALSE, 'mp4', %s, %s) "
                "ON CONFLICT DO NOTHING"
            )
            Db.ExecuteNonQuery(InsertSql, (ProfileId, Res, Kbps, Kbps, Res, Kbps, IcqQ))
            Inserted += 1
    print(f"animation ContentClass thresholds: inserted={Inserted}, updated={Updated}")
    Total = Db.ExecuteQuery(
        "SELECT COUNT(*) AS n FROM ProfileThresholds pt "
        "JOIN Profiles p ON p.Id = pt.ProfileId "
        "WHERE p.Family = 'ANY' AND p.QualityLabel IS NOT NULL AND pt.ContentClass = 'animation'"
    )
    print(f"post-migration animation-class row count: {Total[0]['n']}")


if __name__ == '__main__':
    Main()
