#!/usr/bin/env python3
"""Backfill Family + QualityTier + ContentClass + TargetKbps + IcqQ on the two CANARY families. See directive transcode-flow-canonical C12."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


NVENC_CANARY = 'NVENC AV1 CANARY'
QSV_CANARY = 'QSV AV1 CANARY'


# Live-action AV1 bitrate table (kbps), per directive C12 Q1 2026-07-04.
NVENC_TARGETKBPS = {
    '480p':  {1:  400, 2:  550, 3:  700, 4:   900, 5:  1200},
    '720p':  {1:  900, 2: 1400, 3: 1900, 4:  2500, 5:  3200},
    '1080p': {1: 1800, 2: 2400, 3: 3200, 4:  4200, 5:  5500},
    '2160p': {1: 4000, 2: 6000, 3: 8500, 4: 12000, 5: 18000},
}

# QSV ICQ q value ladder per tier.
QSV_ICQ = {1: 34, 2: 30, 3: 28, 4: 26, 5: 22}


# directive: transcode-flow-canonical | # see transcode.ST5
def UpdateExistingCanaryTagging(Db: DatabaseService) -> None:
    """Tag existing CANARY profiles with (Family, QualityTier, ContentClass) inferred from ProfileName. Live-action default."""
    Rows = Db.ExecuteQuery(
        "SELECT Id, ProfileName, RateControlMode, UseNvidiaHardware, UseIntelHardware "
        "FROM Profiles WHERE Active = TRUE AND ProfileName ILIKE %s",
        ('%CANARY%',),
    )
    for R in Rows:
        Name = R['profilename']
        Family = None
        Tier = None
        if int(R.get('usenvidiahardware') or 0) == 1 and (R.get('ratecontrolmode') or '').lower() == 'vbr':
            Family = NVENC_CANARY
            Tier = 4 if ' HQ' in Name else 2
        elif int(R.get('useintelhardware') or 0) == 1 and (R.get('ratecontrolmode') or '').lower() == 'icq':
            Family = QSV_CANARY
            Tier = 3 if ' HQ' in Name else 2
        if not Family:
            continue
        print(f"Tagging Profile {R['id']} ({Name}) -> Family={Family}, QualityTier={Tier}, ContentClass=live_action")
        Db.ExecuteNonQuery(
            "UPDATE Profiles SET Family = %s, QualityTier = %s, ContentClass = %s WHERE Id = %s",
            (Family, Tier, 'live_action', R['id']),
        )


# directive: transcode-flow-canonical | # see transcode.ST5
def BackfillProfileThresholdKnobs(Db: DatabaseService) -> None:
    """Populate ProfileThresholds.TargetKbps + IcqQ from the calibrated table based on the profile's Family + QualityTier + row Resolution."""
    Rows = Db.ExecuteQuery(
        "SELECT pt.Id AS pt_id, pt.ProfileId, pt.Resolution, p.Family, p.QualityTier "
        "FROM ProfileThresholds pt "
        "JOIN Profiles p ON p.Id = pt.ProfileId "
        "WHERE p.Family IN (%s, %s) AND p.QualityTier IS NOT NULL",
        (NVENC_CANARY, QSV_CANARY),
    )
    for R in Rows:
        Family = R['family']
        Tier = int(R['qualitytier'])
        Res = R['resolution']
        TargetKbps = NVENC_TARGETKBPS.get(Res, {}).get(Tier) if Family == NVENC_CANARY else None
        IcqQ = QSV_ICQ.get(Tier) if Family == QSV_CANARY else None
        Db.ExecuteNonQuery(
            "UPDATE ProfileThresholds SET TargetKbps = %s, IcqQ = %s WHERE Id = %s",
            (TargetKbps, IcqQ, R['pt_id']),
        )
    print(f"Backfilled TargetKbps + IcqQ on {len(Rows)} ProfileThresholds rows")


# directive: transcode-flow-canonical | # see transcode.ST5
def Summary(Db: DatabaseService) -> None:
    """Print post-backfill invariants."""
    print("\n--- Summary ---")
    Rows = Db.ExecuteQuery(
        "SELECT Family, ContentClass, COUNT(*) AS n FROM Profiles "
        "WHERE Family IS NOT NULL GROUP BY Family, ContentClass ORDER BY Family, ContentClass"
    )
    print("  Profiles tagged with (Family, ContentClass):")
    for R in Rows:
        print(f"    {R['family']} / {R['contentclass']}: {R['n']}")
    Rows = Db.ExecuteQuery(
        "SELECT p.Family, pt.Resolution, p.QualityTier, pt.TargetKbps, pt.IcqQ "
        "FROM ProfileThresholds pt JOIN Profiles p ON p.Id = pt.ProfileId "
        "WHERE p.Family IN ('NVENC AV1 CANARY','QSV AV1 CANARY') "
        "ORDER BY p.Family, pt.Resolution, p.QualityTier"
    )
    print(f"  ProfileThresholds rows on CANARY families ({len(Rows)}):")
    for R in Rows:
        print(f"    {R['family']:22s} {R['resolution']:6s} Tier={R['qualitytier']} TargetKbps={R['targetkbps']} IcqQ={R['icqq']}")


# directive: transcode-flow-canonical | # see transcode.ST5
def RunMigration() -> None:
    """Entry point."""
    Db = DatabaseService()
    UpdateExistingCanaryTagging(Db)
    BackfillProfileThresholdKnobs(Db)
    Summary(Db)


if __name__ == '__main__':
    RunMigration()
