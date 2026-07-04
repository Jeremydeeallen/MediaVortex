#!/usr/bin/env python3

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


LEGACY_TO_CANONICAL = {
    'NVENC AV1 P7 CANARY VBR -480p':      'NVENC AV1 P7 CANARY Tier 2 -480p',
    'NVENC AV1 P7 CANARY VBR -720p':      'NVENC AV1 P7 CANARY Tier 2 -720p',
    'NVENC AV1 P7 CANARY VBR -720p HQ':   'NVENC AV1 P7 CANARY Tier 4 -720p',
    'NVENC AV1 P6 CANARY VBR -2160p HQ':  'NVENC AV1 P7 CANARY Tier 4 -720p',
    'QSV AV1 P1 CANARY ICQ q30 -720p':    'QSV AV1 P1 CANARY Tier 2 -720p',
    'QSV AV1 P1 CANARY ICQ q28 -720p HQ': 'QSV AV1 P1 CANARY Tier 3 -720p',
}


ORPHAN_TO_CANONICAL = {
    'NVENC AV1 P7 HQ CQ29 G480 ANIME -720p': 'NVENC AV1 P7 CANARY Tier 3 -720p',
    'QSV AV1 CANARY VBR -720p':              'QSV AV1 P1 CANARY Tier 2 -720p',
    'MediaVortex Near-Lossless 4K NVENC':    'NVENC AV1 P6 CANARY Tier 5 -2160p',
    'MediaVortex Near-Lossless 1080p NVENC': 'NVENC AV1 P7 CANARY Tier 5 -1080p',
}


# directive: transcode-flow-canonical | # see transcode.ST5
def RemapMediaFiles(Db: DatabaseService, mapping: dict, label: str) -> None:
    for LegacyName, CanonicalName in mapping.items():
        Rows = Db.ExecuteQuery(
            "SELECT COUNT(*) AS n FROM MediaFiles WHERE AssignedProfile = %s",
            (LegacyName,),
        )
        Count = int(Rows[0]['n'])
        if Count == 0:
            continue
        Db.ExecuteNonQuery(
            "UPDATE MediaFiles SET AssignedProfile = %s, AssignedProfileSource = 'canary_consolidation_2026_07_04' "
            "WHERE AssignedProfile = %s",
            (CanonicalName, LegacyName),
        )
        print(f"  [{label}] {Count} MediaFiles: {LegacyName!r} -> {CanonicalName!r}")


# directive: transcode-flow-canonical | # see transcode.ST5
def DeleteLegacyCanaryDuplicates(Db: DatabaseService) -> None:
    for LegacyName in LEGACY_TO_CANONICAL.keys():
        RefRows = Db.ExecuteQuery(
            "SELECT COUNT(*) AS n FROM MediaFiles WHERE AssignedProfile = %s",
            (LegacyName,),
        )
        RefCount = int(RefRows[0]['n'])
        if RefCount > 0:
            print(f"  SKIP delete {LegacyName!r}: still has {RefCount} MediaFiles references")
            continue
        IdRows = Db.ExecuteQuery(
            "SELECT Id FROM Profiles WHERE ProfileName = %s",
            (LegacyName,),
        )
        if not IdRows:
            continue
        ProfileId = int(IdRows[0]['id'])
        Db.ExecuteNonQuery("DELETE FROM ProfileThresholds WHERE ProfileId = %s", (ProfileId,))
        Db.ExecuteNonQuery("DELETE FROM Profiles WHERE Id = %s", (ProfileId,))
        print(f"  DELETED legacy CANARY: {LegacyName!r} (Id={ProfileId})")


# directive: transcode-flow-canonical | # see transcode.ST5
def Summary(Db: DatabaseService) -> None:
    print("\n--- Summary ---")
    Rows = Db.ExecuteQuery(
        "SELECT AssignedProfile, COUNT(*) AS n FROM MediaFiles WHERE AssignedProfile IS NOT NULL GROUP BY AssignedProfile ORDER BY n DESC LIMIT 20"
    )
    print("  Top AssignedProfile values on MediaFiles:")
    for R in Rows:
        print(f"    {R['assignedprofile']}: {R['n']}")
    Rows = Db.ExecuteQuery(
        "SELECT AssignedProfile, COUNT(*) AS n FROM MediaFiles WHERE AssignedProfile IS NOT NULL "
        "AND AssignedProfile NOT IN (SELECT ProfileName FROM Profiles WHERE Family IN ('NVENC AV1 CANARY','QSV AV1 CANARY')) "
        "GROUP BY AssignedProfile ORDER BY n DESC"
    )
    print(f"  Remaining orphans (non-CANARY-family references): {len(Rows)}")
    for R in Rows:
        print(f"    {R['assignedprofile']}: {R['n']}")


# directive: transcode-flow-canonical | # see transcode.ST5
def RunMigration() -> None:
    Db = DatabaseService()
    print("Step 1: remap legacy CANARY-named references to canonical Tier names")
    RemapMediaFiles(Db, LEGACY_TO_CANONICAL, "consolidate")
    print("\nStep 2: reassign orphaned (non-CANARY-family) references")
    RemapMediaFiles(Db, ORPHAN_TO_CANONICAL, "orphan-reassign")
    print("\nStep 3: delete legacy CANARY duplicate Profile rows")
    DeleteLegacyCanaryDuplicates(Db)
    Summary(Db)


if __name__ == '__main__':
    RunMigration()
