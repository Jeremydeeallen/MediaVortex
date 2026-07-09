# directive: transcode-flow-canonical | # see profile-tier-ladder.C1
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


TIER_LABELS = {
    1: 'Efficient',
    2: 'Good',
    3: 'Better',
    4: 'Best',
    5: 'Reference',
}


TARGET_KBPS = {
    ('480p', 1): 400,   ('480p', 2): 550,   ('480p', 3): 700,   ('480p', 4): 900,    ('480p', 5): 1200,
    ('720p', 1): 900,   ('720p', 2): 1400,  ('720p', 3): 1900,  ('720p', 4): 2500,   ('720p', 5): 3200,
    ('1080p', 1): 1800, ('1080p', 2): 2400, ('1080p', 3): 3200, ('1080p', 4): 4200,  ('1080p', 5): 5500,
    ('2160p', 1): 4000, ('2160p', 2): 6000, ('2160p', 3): 8500, ('2160p', 4): 12000, ('2160p', 5): 18000,
}


ICQ_LADDER = {1: 34, 2: 30, 3: 28, 4: 26, 5: 22}


RESOLUTIONS = ('480p', '720p', '1080p', '2160p')


LEGACY_FAMILIES = ('NVENC AV1 CANARY', 'QSV AV1 CANARY')


SNAPSHOT_SUFFIX = '_snapshot_20260709'


def _NewProfileName(Tier: int) -> str:
    return f"AV1 CANARY Tier {Tier} {TIER_LABELS[Tier]}"


# directive: transcode-flow-canonical
def _Snapshot(Db: DatabaseService, Table: str) -> None:
    SnapTable = Table + SNAPSHOT_SUFFIX
    Db.ExecuteNonQuery(
        f"CREATE TABLE IF NOT EXISTS {SnapTable} AS SELECT * FROM {Table} WHERE FALSE",
        (),
    )
    Existing = Db.ExecuteQuery(f"SELECT count(*) AS n FROM {SnapTable}", ())
    if Existing and Existing[0]['n'] > 0:
        print(f"  {SnapTable}: already populated ({Existing[0]['n']} rows) -- skip")
        return
    Db.ExecuteNonQuery(f"INSERT INTO {SnapTable} SELECT * FROM {Table}", ())
    Rows = Db.ExecuteQuery(f"SELECT count(*) AS n FROM {SnapTable}", ())
    print(f"  {SnapTable}: snapshot populated ({Rows[0]['n']} rows)")


# directive: transcode-flow-canonical
def _AddColumnIfMissing(Db: DatabaseService, Table: str, Column: str, TypeDef: str) -> None:
    Exists = Db.ExecuteQuery(
        "SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name=%s",
        (Table, Column.lower()),
    )
    if Exists:
        print(f"  {Table}.{Column}: exists (skip)")
        return
    Db.ExecuteNonQuery(f"ALTER TABLE {Table} ADD COLUMN {Column} {TypeDef}", ())
    print(f"  {Table}.{Column}: added ({TypeDef})")


# directive: transcode-flow-canonical
def _InsertNewTierProfiles(Db: DatabaseService) -> dict:
    Result = {}
    for Tier in range(1, 6):
        Name = _NewProfileName(Tier)
        Label = TIER_LABELS[Tier]
        Existing = Db.ExecuteQuery(
            "SELECT id FROM profiles WHERE profilename = %s", (Name,)
        )
        if Existing:
            Result[Tier] = Existing[0]['id']
            print(f"  {Name}: exists id={Existing[0]['id']} (skip)")
            continue
        Db.ExecuteNonQuery(
            "INSERT INTO profiles "
            "(profilename, description, codec, preset, ratecontrolmode, "
            " usenvidiahardware, useintelhardware, "
            " qualitytestrequired, draft, active, "
            " family, qualitytier, contentclass, qualitylabel, "
            " targetresolutioncategory, container, faststart) "
            "VALUES (%s, %s, 'av1', 6, 'vbr', "
            " 0, 0, TRUE, FALSE, TRUE, "
            " 'ANY', %s, 'live_action', %s, "
            " NULL, 'mp4', TRUE) "
            "ON CONFLICT (profilename) DO NOTHING",
            (Name, f"Family-agnostic tier-ladder AV1 profile (encoder resolved at claim). Quality label: {Label}.", Tier, Label),
        )
        Rows = Db.ExecuteQuery("SELECT id FROM profiles WHERE profilename = %s", (Name,))
        Result[Tier] = Rows[0]['id']
        print(f"  {Name}: inserted id={Rows[0]['id']}")
    return Result


# directive: transcode-flow-canonical
def _InsertNewThresholds(Db: DatabaseService, TierToProfileId: dict) -> None:
    for Tier, ProfileId in TierToProfileId.items():
        for Res in RESOLUTIONS:
            Kbps = TARGET_KBPS[(Res, Tier)]
            IcqQ = ICQ_LADDER[Tier]
            Existing = Db.ExecuteQuery(
                "SELECT id FROM profilethresholds WHERE profileid=%s AND resolution=%s AND contentclass='live_action'",
                (ProfileId, Res),
            )
            if Existing:
                Db.ExecuteNonQuery(
                    "UPDATE profilethresholds SET targetkbps=%s, icqq=%s, "
                    "under30minmb=0, under65minmb=0, over65minmb=0, "
                    "videobitratekbps=%s, audiobitratekbps=192, "
                    "fallbackvideobitratekbps=%s, fallbackaudiobitratekbps=192, "
                    "transcodedownto=%s, quality=0, keepsource=FALSE, containertype='mp4' "
                    "WHERE id=%s",
                    (Kbps, IcqQ, Kbps, Kbps, Res, Existing[0]['id']),
                )
                print(f"  threshold ProfileId={ProfileId} Res={Res} live_action: UPDATED (kbps={Kbps}, icq={IcqQ})")
                continue
            Db.ExecuteNonQuery(
                "INSERT INTO profilethresholds "
                "(profileid, resolution, contentclass, "
                " under30minmb, under65minmb, over65minmb, "
                " videobitratekbps, audiobitratekbps, "
                " fallbackvideobitratekbps, fallbackaudiobitratekbps, "
                " transcodedownto, quality, keepsource, containertype, "
                " targetkbps, icqq) "
                "VALUES (%s, %s, 'live_action', 0, 0, 0, %s, 192, %s, 192, %s, 0, FALSE, 'mp4', %s, %s) "
                "ON CONFLICT DO NOTHING",
                (ProfileId, Res, Kbps, Kbps, Res, Kbps, IcqQ),
            )
            print(f"  threshold ProfileId={ProfileId} Res={Res} live_action: INSERTED (kbps={Kbps}, icq={IcqQ})")


# directive: transcode-flow-canonical
def _MapOldToNew(Db: DatabaseService, TierToProfileId: dict) -> list:
    Rows = Db.ExecuteQuery(
        "SELECT profilename, qualitytier FROM profiles WHERE family IN %s ORDER BY qualitytier",
        (LEGACY_FAMILIES,),
    )
    Pairs = []
    for R in Rows or []:
        Tier = R.get('qualitytier')
        if Tier is None or Tier not in TierToProfileId:
            print(f"  WARN old profile {R['profilename']} has tier={Tier} outside 1..5; skipping")
            continue
        NewName = _NewProfileName(Tier)
        Pairs.append((R['profilename'], NewName))
    return Pairs


# directive: transcode-flow-canonical
def _RewriteFks(Db: DatabaseService, Pairs: list) -> None:
    for OldName, NewName in Pairs:
        Mf = Db.ExecuteNonQuery(
            "UPDATE mediafiles SET assignedprofile=%s WHERE assignedprofile=%s",
            (NewName, OldName),
        )
        Ta = Db.ExecuteNonQuery(
            "UPDATE transcodeattempts SET profilename=%s WHERE profilename=%s",
            (NewName, OldName),
        )
        print(f"  {OldName} -> {NewName}: mediafiles={Mf}, transcodeattempts={Ta}")


# directive: transcode-flow-canonical
def _DeleteOldProfiles(Db: DatabaseService) -> None:
    Thr = Db.ExecuteNonQuery(
        "DELETE FROM profilethresholds WHERE profileid IN ("
        "SELECT id FROM profiles WHERE family IN %s)",
        (LEGACY_FAMILIES,),
    )
    Pr = Db.ExecuteNonQuery(
        "DELETE FROM profiles WHERE family IN %s",
        (LEGACY_FAMILIES,),
    )
    print(f"  Deleted profilethresholds: {Thr}; profiles: {Pr}")


# directive: transcode-flow-canonical
def _RewriteConstraints(Db: DatabaseService) -> None:
    Existing = Db.ExecuteQuery(
        "SELECT conname FROM pg_constraint WHERE conname='profilethresholds_profile_res_unique'"
    )
    if Existing:
        Db.ExecuteNonQuery(
            "ALTER TABLE profilethresholds DROP CONSTRAINT profilethresholds_profile_res_unique",
            (),
        )
        print("  Dropped constraint profilethresholds_profile_res_unique")
    New = Db.ExecuteQuery(
        "SELECT conname FROM pg_constraint WHERE conname='profilethresholds_profile_content_res_unique'"
    )
    if not New:
        Db.ExecuteNonQuery(
            "ALTER TABLE profilethresholds ADD CONSTRAINT profilethresholds_profile_content_res_unique "
            "UNIQUE (profileid, contentclass, resolution)",
            (),
        )
        print("  Added constraint profilethresholds_profile_content_res_unique UNIQUE (profileid, contentclass, resolution)")
    Ql = Db.ExecuteQuery(
        "SELECT conname FROM pg_constraint WHERE conname='profiles_qualitylabel_unique'"
    )
    if not Ql:
        Db.ExecuteNonQuery(
            "ALTER TABLE profiles ADD CONSTRAINT profiles_qualitylabel_unique UNIQUE (qualitylabel)",
            (),
        )
        print("  Added constraint profiles_qualitylabel_unique UNIQUE (qualitylabel)")


# directive: transcode-flow-canonical
def Main(DryRun: bool = False):
    Db = DatabaseService()
    print(f"=== CollapseProfilesToTierLadder ({'DRY-RUN' if DryRun else 'LIVE'}) ===\n")

    print("Step 1: Snapshot tables")
    for T in ('profiles', 'profilethresholds', 'mediafiles', 'transcodeattempts', 'transcodequeue'):
        _Snapshot(Db, T)

    print("\nStep 2: Add profiles.qualitylabel + profilethresholds.contentclass columns")
    _AddColumnIfMissing(Db, 'profiles', 'qualitylabel', "TEXT")
    _AddColumnIfMissing(Db, 'profilethresholds', 'contentclass', "TEXT NOT NULL DEFAULT 'live_action'")

    print("\nStep 3: Insert 5 tier-ladder profiles")
    TierToProfileId = _InsertNewTierProfiles(Db)

    print("\nStep 4: Insert threshold rows for new tier profiles")
    _InsertNewThresholds(Db, TierToProfileId)

    print("\nStep 5: Rewrite FKs (mediafiles.assignedprofile + transcodeattempts.profilename)")
    Pairs = _MapOldToNew(Db, TierToProfileId)
    if DryRun:
        for O, N in Pairs:
            print(f"  DRY-RUN would map {O} -> {N}")
    else:
        _RewriteFks(Db, Pairs)

    print("\nStep 6: Delete old per-Family CANARY profiles + their thresholds")
    if DryRun:
        Count = Db.ExecuteQuery(
            "SELECT count(*) AS n FROM profiles WHERE family IN %s", (LEGACY_FAMILIES,)
        )
        print(f"  DRY-RUN would delete {Count[0]['n']} profiles + their thresholds")
    else:
        _DeleteOldProfiles(Db)

    print("\nStep 7: Rewrite constraints")
    if not DryRun:
        _RewriteConstraints(Db)

    print("\nStep 8: Verify shape")
    ProfileCount = Db.ExecuteQuery(
        "SELECT count(*) AS n FROM profiles WHERE family='ANY' OR qualitylabel IS NOT NULL"
    )
    ThreshCount = Db.ExecuteQuery(
        "SELECT count(*) AS n FROM profilethresholds pt "
        "JOIN profiles p ON p.id=pt.profileid WHERE p.family='ANY'"
    )
    Orphans = Db.ExecuteQuery(
        "SELECT count(*) AS n FROM mediafiles WHERE assignedprofile IS NOT NULL "
        "AND assignedprofile NOT IN (SELECT profilename FROM profiles)"
    )
    print(f"  New tier profiles: {ProfileCount[0]['n']}")
    print(f"  New threshold rows: {ThreshCount[0]['n']}")
    print(f"  Orphaned mediafiles.assignedprofile: {Orphans[0]['n']}")
    print("\nDone.")


if __name__ == '__main__':
    Main(DryRun='--dry-run' in sys.argv)
