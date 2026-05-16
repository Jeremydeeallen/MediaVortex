"""One-shot remediation: reset FFprobeFailureCount on MediaFiles that wakko-worker-1
falsely flagged as source-missing during the 2026-05-14 broken-NFS incident.

Background: wakko-worker-1 came up with /mnt/media_tv pointing at the local NVMe
instead of the NAS NFS share. For ~4.5 hours it claimed queue items, found the
"source file missing" (the share wasn't mounted), bumped FFprobeFailureCount,
and deleted the queue items. 154 MediaFiles ended up with FFprobeFailureCount >= 2
and LastFFprobeError starting with "Source file missing on disk:" -- all in a
narrow window on 2026-05-14. See KNOWN-ISSUES.md:109.

The mount-validation fix in WorkerService/Main.py (worker-lifecycle criteria 20, 21,
shipped 2026-05-15) prevents recurrence. This script unwinds the historical damage.

Behavior:
1. Find every MediaFiles row with LastFFprobeError LIKE 'Source file missing on disk:%'
   AND LastFFprobeAttemptDate in the wakko window (2026-05-14).
2. For each, check whether the FilePath exists on disk NOW (from this host's
   perspective, using the same path-translation map as FlagMissingMediaFiles.py).
3. If the file exists: this was a false positive -- reset FFprobeFailureCount=0,
   clear LastFFprobeError, leave LastFFprobeAttemptDate alone.
4. If the file does not exist: leave the row alone. The "missing" flag is now
   correct (whether because the file truly is gone or because this host can't
   see it -- either way, not safe to reset blindly).

Run with --dry-run first to see what would be reset.

Usage:
    py Scripts/ResetWakkoMountFailureCounts.py --dry-run
    py Scripts/ResetWakkoMountFailureCounts.py --commit
"""
import argparse
import os
import sys

import psycopg2
import psycopg2.extras


DEFAULT_PATH_MAP = {
    "T:\\": os.environ.get("MEDIAVORTEX_T_LOCAL", "T:\\" if os.name == "nt" else "/mnt/media_tv/"),
    "M:\\": os.environ.get("MEDIAVORTEX_M_LOCAL", "M:\\" if os.name == "nt" else "/mnt/movies/"),
    "Z:\\": os.environ.get("MEDIAVORTEX_Z_LOCAL", "Z:\\" if os.name == "nt" else "/mnt/xxx/"),
}

WAKKO_WINDOW_START = "2026-05-14 00:00:00"
WAKKO_WINDOW_END = "2026-05-15 00:00:00"


def TranslateToLocal(CanonicalPath: str, PathMap: dict) -> str:
    if not CanonicalPath:
        return CanonicalPath
    Upper = CanonicalPath.upper()
    for Prefix, LocalPrefix in PathMap.items():
        if Upper.startswith(Prefix):
            Tail = CanonicalPath[len(Prefix):]
            if "/" in LocalPrefix and "\\" in Tail:
                Tail = Tail.replace("\\", "/")
            return LocalPrefix + Tail
    return CanonicalPath


def Main():
    Parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    Parser.add_argument("--commit", action="store_true", help="Apply changes (default is dry-run)")
    Parser.add_argument("--dry-run", action="store_true", help="Report what would change but do not write")
    Args = Parser.parse_args()

    if not Args.commit and not Args.dry_run:
        Args.dry_run = True

    Conn = psycopg2.connect(
        host=os.environ.get("MEDIAVORTEX_DB_HOST", "localhost"),
        port=int(os.environ.get("MEDIAVORTEX_DB_PORT", 5432)),
        dbname=os.environ.get("MEDIAVORTEX_DB_NAME", "mediavortex"),
        user=os.environ.get("MEDIAVORTEX_DB_USER", "mediavortex"),
        password=os.environ.get("MEDIAVORTEX_DB_PASSWORD", "mediavortex"),
    )
    Conn.autocommit = False

    print(f"Path map in effect: {DEFAULT_PATH_MAP}")
    print(f"Mode: {'COMMIT' if Args.commit else 'DRY-RUN'}")
    print(f"Window: {WAKKO_WINDOW_START} -> {WAKKO_WINDOW_END}")
    print()

    Query = """
        SELECT Id, FilePath, FFprobeFailureCount, LastFFprobeError, LastFFprobeAttemptDate
        FROM MediaFiles
        WHERE LastFFprobeError LIKE 'Source file missing on disk:%%'
          AND LastFFprobeAttemptDate >= %s
          AND LastFFprobeAttemptDate < %s
        ORDER BY Id
    """

    with Conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as Cur:
        Cur.execute(Query, (WAKKO_WINDOW_START, WAKKO_WINDOW_END))
        Rows = Cur.fetchall()

    print(f"Candidate rows in window: {len(Rows):,}")

    Resets = []
    StillMissing = []
    for Row in Rows:
        MediaFileId = Row["id"]
        FilePath = Row["filepath"]
        LocalPath = TranslateToLocal(FilePath, DEFAULT_PATH_MAP)
        if os.path.exists(LocalPath):
            Resets.append((MediaFileId, FilePath, LocalPath, Row["ffprobefailurecount"]))
        else:
            StillMissing.append((MediaFileId, LocalPath))

    print(f"  File exists on disk now (will reset): {len(Resets):,}")
    print(f"  File still missing (left alone): {len(StillMissing):,}")
    print()

    if Resets:
        print("Sample of rows to reset (first 10):")
        for MediaFileId, _, LocalPath, OldCount in Resets[:10]:
            print(f"  id={MediaFileId} count={OldCount} -> 0  ({LocalPath})")
        print()

    if StillMissing:
        print("Sample of rows left alone (first 5):")
        for MediaFileId, LocalPath in StillMissing[:5]:
            print(f"  id={MediaFileId} not found at {LocalPath}")
        print()

    if not Resets:
        print("Nothing to reset.")
        return

    if Args.dry_run:
        print(f"DRY-RUN: would reset {len(Resets):,} rows. Re-run with --commit to apply.")
        return

    print(f"Applying reset to {len(Resets):,} rows...")
    with Conn.cursor() as Cur:
        for MediaFileId, _, _, _ in Resets:
            Cur.execute(
                """
                UPDATE MediaFiles
                SET FFprobeFailureCount = 0,
                    LastFFprobeError = NULL
                WHERE Id = %s
                """,
                (MediaFileId,),
            )
    Conn.commit()
    Conn.close()
    print(f"Done. {len(Resets):,} rows reset.")


if __name__ == "__main__":
    Main()
