import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Features.MediaFiles.MediaFilesRepository import MediaFilesRepository


STORAGE_ROOT_ID_XXX = 3
CATEGORIES = ["480p", "720p"]
EXCLUDE_FILENAME_PREFIXES = ["c1", "cute"]


def UnlinkDiskFiles(paths):
    ok = 0
    missing = 0
    errors = []
    for p in paths:
        try:
            if os.path.isfile(p):
                os.remove(p)
                ok += 1
            else:
                missing += 1
        except OSError as e:
            errors.append((p, str(e)))
    return ok, missing, errors


def Main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--delete-disk", action="store_true")
    args = ap.parse_args()

    if args.delete_disk and not args.commit:
        print("ERROR: --delete-disk requires --commit", file=sys.stderr)
        sys.exit(2)

    mode = "COMMIT" if args.commit else "DRY-RUN"
    print(f"=== PurgeXxxLandscapeLe720p [{mode}] ===")

    repo = MediaFilesRepository()

    rows = repo.SelectPurgeCandidates(
        STORAGE_ROOT_ID_XXX,
        CATEGORIES,
        LandscapeOnly=True,
        ExcludeFilenamePrefixes=EXCLUDE_FILENAME_PREFIXES,
    )
    ids = [int(r["Id"]) for r in rows]
    paths = [r["CanonicalPath"] for r in rows]
    total_mb = sum((r["SizeMb"] or 0) for r in rows)

    print(f"Target rows: {len(ids)}")
    print(f"Total size:  {total_mb / 1024.0:.2f} GB")
    print()

    if not ids:
        print("Nothing to do.")
        return

    counts = repo.CountMediaFileReferences(ids)
    print("Per-table row counts:")
    for table, n in counts.items():
        print(f"  {table:<32} rows={n}")
    print()

    if not args.commit:
        print("DRY-RUN complete. No changes made. Re-run with --commit to execute.")
        return

    print("Executing DB deletes in a single transaction...")
    try:
        purged = repo.PurgeMediaFilesById(ids)
        for table, n in purged.items():
            print(f"  DELETE {table:<32} rows={n}")
        print("DB transaction committed.")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        print("Transaction rolled back.", file=sys.stderr)
        sys.exit(1)

    if args.delete_disk:
        print()
        print(f"Unlinking {len(paths)} files on disk...")
        ok, missing, errors = UnlinkDiskFiles(paths)
        print(f"  deleted: {ok}")
        print(f"  missing: {missing}")
        print(f"  errors:  {len(errors)}")
        for p, msg in errors[:20]:
            print(f"    {p}: {msg}")
        if len(errors) > 20:
            print(f"    ... and {len(errors) - 20} more")


if __name__ == "__main__":
    Main()
