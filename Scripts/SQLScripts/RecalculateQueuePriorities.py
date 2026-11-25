# directive: profile-row-lookup
"""Rebalance Priority on every Pending TranscodeQueue row below the manual-override window (195) with the current formula; dry-run by default, --commit applies."""

import argparse
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)


# directive: profile-row-lookup | # see profile-tier-ladder.C9 -- priority rates come from the file's encode row through the one lookup; DB access through DatabaseService
def Main():
    Parser = argparse.ArgumentParser(description=__doc__)
    Parser.add_argument("--commit", action="store_true", help="Apply changes (default is dry-run)")
    Parser.add_argument("--dry-run", action="store_true", help="Report what would change but do not write")
    Args = Parser.parse_args()
    DryRun = Args.dry_run or not Args.commit

    from Core.Database.DatabaseService import DatabaseService
    from Features.Profiles.ContentClassResolver import ContentClassResolver
    from Features.Profiles.TierLadderRepository import TierLadderRepository
    from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
    from Models.MediaFileModel import MediaFileModel

    Db = DatabaseService()
    Svc = QueueManagementBusinessService()
    Tiers = TierLadderRepository(Db)
    Classes = ContentClassResolver(Db)

    print(f"Mode: {'COMMIT' if not DryRun else 'DRY-RUN'}")
    print()

    Rows = Db.ExecuteQuery(
        "SELECT q.Id AS QueueId, q.Priority AS OldPriority, q.MediaFileId, "
        "       mf.Id AS MfId, mf.StorageRootId, mf.FileName, mf.SizeMB, mf.DurationMinutes, mf.AssignedProfile, mf.Resolution "
        "FROM TranscodeQueue q LEFT JOIN MediaFiles mf ON mf.Id = q.MediaFileId "
        "WHERE q.Status = 'Pending' AND COALESCE(q.Priority, 0) < 195 ORDER BY q.Id"
    )

    print(f"Scanning {len(Rows):,} Pending queue rows (manual-override 195-200 excluded)...")
    print()

    Updates = []
    SkippedNoMediaFile = 0
    Unchanged = 0

    for Row in Rows:
        if Row["MfId"] is None:
            SkippedNoMediaFile += 1
            continue

        Mf = MediaFileModel()
        Mf.Id = Row["MfId"]
        Mf.FileName = Row["FileName"]
        Mf.SizeMB = Row["SizeMB"]
        Mf.DurationMinutes = Row["DurationMinutes"]
        Mf.AssignedProfile = Row["AssignedProfile"]
        Mf.Resolution = Row["Resolution"]

        TargetVideoKbps = None
        TargetAudioKbps = None
        if Mf.AssignedProfile and Mf.Resolution:
            ContentClass = Classes.Resolve(Row["StorageRootId"], Mf.Id)
            Encode = Tiers.GetEncodeRow(Mf.AssignedProfile, ContentClass, Mf.Resolution) if ContentClass else None
            if Encode:
                TargetVideoKbps = Encode.TargetKbps
                TargetAudioKbps = Encode.AudioBitrateKbps

        NewPriority = Svc.CalculatePriority(Mf, TargetVideoKbps=TargetVideoKbps, TargetAudioKbps=TargetAudioKbps)
        OldPriority = Row["OldPriority"] or 0
        if NewPriority == OldPriority:
            Unchanged += 1
            continue
        Updates.append((Row["QueueId"], OldPriority, NewPriority, Mf.FileName))

    print("Sample of planned changes (up to 30):")
    for QId, Old, New, Name in Updates[:30]:
        Direction = "+" if New > Old else " "
        print(f"  Queue {QId:6d}  {Old:4d} -> {New:4d}  {Direction} {Name}")
    if len(Updates) > 30:
        print(f"  ... and {len(Updates) - 30} more")

    print()
    print("Summary:")
    print(f"  Total scanned:                      {len(Rows):,}")
    print(f"  Skipped (no MediaFile linkage):     {SkippedNoMediaFile:,}")
    print(f"  Unchanged (same priority):          {Unchanged:,}")
    print(f"  Would update:                       {len(Updates):,}")

    if not Updates:
        print("Nothing to update.")
        return

    if DryRun:
        print()
        print(f"DRY-RUN: {len(Updates):,} rows would change. Re-run with --commit to apply.")
        return

    print()
    print(f"Applying {len(Updates):,} updates...")
    for QId, _Old, New, _Name in Updates:
        Db.ExecuteNonQuery("UPDATE TranscodeQueue SET Priority = %s WHERE Id = %s", (New, QId))
    print(f"Done. {len(Updates):,} queue rows rebalanced.")


if __name__ == "__main__":
    Main()
