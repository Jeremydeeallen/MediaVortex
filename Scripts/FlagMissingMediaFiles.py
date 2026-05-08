"""One-shot cleanup: flag MediaFiles rows whose FilePath does not exist on disk.

Background: the DB-log audit on 2026-05-08 found 271+ "Path does not exist,
cannot normalize" warnings firing every scan against MediaFiles rows that
point at files that have been deleted, renamed, or already transcoded into a
new filename (e.g. *.mkv -> *.mp4 with a different resolution suffix). The
Phase 1 pre-flight check in `ProcessJob` stops new occurrences from creating
attempt rows but does not sweep the existing stale rows. This script does.

Behavior:
1. Iterate every MediaFiles row.
2. Translate the canonical Windows-style path to a local one if running on
   Linux (using a hardcoded T:\\ -> /mnt/media_tv/, M:\\ -> /mnt/movies/,
   Z:\\ -> /mnt/xxx/ map -- override via env vars).
3. Run os.path.exists() on the local path.
4. If missing AND FFprobeFailureCount < 3: bump FFprobeFailureCount to 3,
   set LastFFprobeError = 'Source file missing on disk (flagged by
   FlagMissingMediaFiles.py)', set LastFFprobeAttemptDate = NOW(). The
   queue-population safety guard skips files with FFprobeFailureCount >= 3
   on subsequent scans, so this stops the dead-file retry loop.
5. Skip rows that already have FFprobeFailureCount >= 3 (no-op).
6. Skip rows where the file exists (untouched).

Run with --dry-run first to see what would be flagged.

Usage:
    py Scripts/FlagMissingMediaFiles.py --dry-run
    py Scripts/FlagMissingMediaFiles.py --commit
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


def TranslateToLocal(CanonicalPath: str, PathMap: dict) -> str:
    """Translate canonical (Windows-flavored) path to local mount path."""
    if not CanonicalPath:
        return CanonicalPath
    Upper = CanonicalPath.upper()
    for Prefix, LocalPrefix in PathMap.items():
        if Upper.startswith(Prefix):
            Tail = CanonicalPath[len(Prefix):]
            # On Linux the local prefix uses /, so flip backslashes in the tail
            if "/" in LocalPrefix and "\\" in Tail:
                Tail = Tail.replace("\\", "/")
            return LocalPrefix + Tail
    return CanonicalPath


def Main():
    Parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    Parser.add_argument("--commit", action="store_true", help="Apply changes (default is dry-run)")
    Parser.add_argument("--dry-run", action="store_true", help="Report what would change but do not write")
    Parser.add_argument("--limit", type=int, default=0, help="Process at most N rows (0 = all)")
    Args = Parser.parse_args()

    if not Args.commit and not Args.dry_run:
        print("Specify --dry-run or --commit. Defaulting to --dry-run.")
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
    print()

    Limit = f"LIMIT {Args.limit}" if Args.limit else ""
    Query = f"""
        SELECT Id, FilePath, FFprobeFailureCount, LastFFprobeError
        FROM MediaFiles
        WHERE FilePath IS NOT NULL
          AND (FFprobeFailureCount IS NULL OR FFprobeFailureCount < 3)
        ORDER BY Id
        {Limit}
    """

    Total = 0
    Missing = 0
    Existing = 0
    AlreadyFlagged = 0
    Untranslatable = 0

    with Conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as Cur:
        Cur.execute(Query)
        Rows = Cur.fetchall()
    print(f"Scanning {len(Rows):,} candidate rows (FFprobeFailureCount < 3)...")
    print()

    Updates = []
    for Row in Rows:
        Total += 1
        MediaFileId = Row["id"]
        FilePath = Row["filepath"]

        LocalPath = TranslateToLocal(FilePath, DEFAULT_PATH_MAP)
        if LocalPath == FilePath and FilePath.startswith(("T:", "M:", "Z:")) and os.name != "nt":
            Untranslatable += 1
            continue

        if os.path.exists(LocalPath):
            Existing += 1
        else:
            Missing += 1
            Updates.append((MediaFileId, FilePath, LocalPath))
            if Missing <= 20:
                print(f"  [MISSING] id={MediaFileId} -> {LocalPath}")

        if Total % 5000 == 0:
            print(f"  ...checked {Total:,}/{len(Rows):,}")

    print()
    print(f"Summary:")
    print(f"  Total scanned: {Total:,}")
    print(f"  Existing on disk: {Existing:,}")
    print(f"  Missing: {Missing:,}")
    print(f"  Untranslatable prefix (skipped): {Untranslatable:,}")
    print(f"  Already flagged with FFprobeFailureCount >= 3: {AlreadyFlagged:,} (excluded by query)")

    if not Updates:
        print("Nothing to flag.")
        return

    if Args.dry_run:
        print()
        print(f"DRY-RUN: would flag {len(Updates):,} MediaFiles rows. Re-run with --commit to apply.")
        return

    print()
    print(f"Applying flag to {len(Updates):,} rows...")
    with Conn.cursor() as Cur:
        for MediaFileId, FilePath, LocalPath in Updates:
            Cur.execute(
                """
                UPDATE MediaFiles
                SET FFprobeFailureCount = 3,
                    LastFFprobeError = %s,
                    LastFFprobeAttemptDate = NOW()
                WHERE Id = %s
                """,
                (
                    f"Source file missing on disk (flagged by FlagMissingMediaFiles.py at {LocalPath})",
                    MediaFileId,
                ),
            )
    Conn.commit()
    Conn.close()
    print(f"Done. {len(Updates):,} rows flagged. Queue population will skip these on the next pass.")


if __name__ == "__main__":
    Main()
