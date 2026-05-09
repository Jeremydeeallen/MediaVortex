"""Recompute Priority on every Pending TranscodeQueue row using the new
impact-based formula (queue-priority.feature.md). Existing items keep their
stored priority by default -- run this script when you want to rebalance
the queue against the new scoring without re-populating from scratch.

Defaults to --dry-run; pass --commit to apply changes.

Usage:
    py Scripts/SQLScripts/RecalculateQueuePriorities.py            # dry-run, list-only
    py Scripts/SQLScripts/RecalculateQueuePriorities.py --commit   # apply

Skipped rows:
- Rows with Priority >= 195 (manual override window) are NEVER touched.
- Rows where the corresponding MediaFile is missing are reported and skipped.
"""

import argparse
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

import psycopg2
import psycopg2.extras


def Main():
    Parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    Parser.add_argument("--commit", action="store_true", help="Apply changes (default is dry-run)")
    Parser.add_argument("--dry-run", action="store_true", help="Report what would change but do not write")
    Args = Parser.parse_args()
    DryRun = Args.dry_run or not Args.commit

    from Repositories.DatabaseManager import DatabaseManager
    from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
    from Models.MediaFileModel import MediaFileModel

    Db = DatabaseManager()
    Svc = QueueManagementBusinessService()

    Conn = psycopg2.connect(
        host=os.environ.get("MEDIAVORTEX_DB_HOST", "localhost"),
        port=int(os.environ.get("MEDIAVORTEX_DB_PORT", 5432)),
        dbname=os.environ.get("MEDIAVORTEX_DB_NAME", "mediavortex"),
        user=os.environ.get("MEDIAVORTEX_DB_USER", "mediavortex"),
        password=os.environ.get("MEDIAVORTEX_DB_PASSWORD", "mediavortex"),
    )
    Conn.autocommit = False

    print(f"Mode: {'COMMIT' if not DryRun else 'DRY-RUN'}")
    print()

    Query = """
        SELECT q.Id AS QueueId, q.Priority AS OldPriority, q.MediaFileId,
               mf.Id AS MfId, mf.FileName, mf.SizeMB, mf.DurationMinutes,
               mf.AssignedProfile, mf.Resolution
        FROM TranscodeQueue q
        LEFT JOIN MediaFiles mf ON mf.Id = q.MediaFileId
        WHERE q.Status = 'Pending'
          AND COALESCE(q.Priority, 0) < 195
        ORDER BY q.Id
    """

    with Conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as Cur:
        Cur.execute(Query)
        Rows = Cur.fetchall()

    print(f"Scanning {len(Rows):,} Pending queue rows (manual-override 195-200 excluded)...")
    print()

    Updates = []
    SkippedNoMediaFile = 0
    Unchanged = 0

    for Row in Rows:
        if Row["mfid"] is None:
            SkippedNoMediaFile += 1
            continue

        Mf = MediaFileModel()
        Mf.Id = Row["mfid"]
        Mf.FileName = Row["filename"]
        Mf.SizeMB = Row["sizemb"]
        Mf.DurationMinutes = Row["durationminutes"]
        Mf.AssignedProfile = Row["assignedprofile"]
        Mf.Resolution = Row["resolution"]

        TargetVideoKbps = None
        TargetAudioKbps = None
        if Mf.AssignedProfile and Mf.Resolution:
            try:
                Settings = Db.GetProfileSettingsForTargetResolution(Mf.AssignedProfile, Mf.Resolution)
                if Settings:
                    TargetVideoKbps = Settings.get("VideoBitrateKbps")
                    TargetAudioKbps = Settings.get("AudioBitrateKbps")
            except Exception:
                pass

        NewPriority = Svc.CalculatePriority(Mf, TargetVideoKbps=TargetVideoKbps, TargetAudioKbps=TargetAudioKbps)
        OldPriority = Row["oldpriority"] or 0
        if NewPriority == OldPriority:
            Unchanged += 1
            continue
        Updates.append((Row["queueid"], OldPriority, NewPriority, Mf.FileName))

    print("Sample of planned changes (up to 30):")
    for QId, Old, New, Name in Updates[:30]:
        Direction = "+" if New > Old else " "
        print(f"  Queue {QId:6d}  {Old:4d} -> {New:4d}  {Direction} {Name}")
    if len(Updates) > 30:
        print(f"  ... and {len(Updates) - 30} more")

    print()
    print(f"Summary:")
    print(f"  Total scanned:                      {len(Rows):,}")
    print(f"  Skipped (no MediaFile linkage):     {SkippedNoMediaFile:,}")
    print(f"  Unchanged (same priority):          {Unchanged:,}")
    print(f"  Would update:                       {len(Updates):,}")

    if not Updates:
        print("Nothing to update.")
        Conn.close()
        return

    if DryRun:
        print()
        print(f"DRY-RUN: {len(Updates):,} rows would change. Re-run with --commit to apply.")
        Conn.close()
        return

    print()
    print(f"Applying {len(Updates):,} updates...")
    with Conn.cursor() as Cur:
        for QId, _Old, New, _Name in Updates:
            Cur.execute("UPDATE TranscodeQueue SET Priority = %s WHERE Id = %s", (New, QId))
    Conn.commit()
    Conn.close()
    print(f"Done. {len(Updates):,} queue rows rebalanced.")


if __name__ == "__main__":
    Main()
