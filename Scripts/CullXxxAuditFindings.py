#!/usr/bin/env python3
"""Cull xxx files flagged by the infrastructure repo's read-only audit.

Input: the four CSVs written by `infrastructure/porky/scripts/xxx-audit.py`
(identical, release-dups, masquerade, starved). This script decides which
copy of each duplicate pair to drop, then on --commit purges the MediaFiles
rows (where they exist; `_uncategorized/` is excluded from MediaVortex scans
so most have none), unlinks the file on X:\\, and sends one batched Jellyfin
Deleted notify. Same shape as PurgeXxxLandscapeLe720p.py.

Usage:
    py Scripts/CullXxxAuditFindings.py --audit-dir <dir>                    # dry run
    py Scripts/CullXxxAuditFindings.py --audit-dir <dir> --commit --delete-disk
    py Scripts/CullXxxAuditFindings.py --audit-dir <dir> --only identical,release-dups

Keep rule for a duplicate pair (first difference wins):
    1. a categorised copy beats `_uncategorized/`
    2. a copy with the operator prefix (C1..C5 / Cute) beats one without
    3. higher ffprobe height, then higher bitrate (release-dups only)
    4. otherwise keep the first path alphabetically and flag the pair REVIEW
"""
import argparse
import csv
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Features.MediaFiles.MediaFilesRepository import MediaFilesRepository
from Services.JellyfinNotifyService import NotifyJellyfin

STORAGE_ROOT_ID_XXX = 3
STASH_PREFIX = "/mnt/xxx/Videos/"
CANONICAL_PREFIX = "X:\\Videos\\"
OPERATOR_PREFIX = re.compile(r"^(c[1-5]|cute)[.\-]?", re.I)
CATEGORIES = ("identical", "release-dups", "masquerade", "starved")


def ToRelative(StashPath):
    """/mnt/xxx/Videos/a/b.mp4 -> Videos/a/b.mp4 (MediaFiles.RelativePath shape)."""
    if not StashPath.startswith(STASH_PREFIX):
        raise ValueError(f"unexpected path root: {StashPath}")
    return "Videos/" + StashPath[len(STASH_PREFIX):]


def ToCanonical(RelativePath):
    return CANONICAL_PREFIX + RelativePath[len("Videos/"):].replace("/", "\\")


def PairScore(RelativePath):
    Parts = RelativePath.split("/")
    Uncategorised = Parts[1] == "_uncategorized"
    HasPrefix = bool(OPERATOR_PREFIX.match(Parts[-1]))
    return (0 if Uncategorised else 1, 1 if HasPrefix else 0)


def ChooseDrops(Group, WithQuality):
    """Group: list of dicts with Rel (+ Height/Kbps when WithQuality). Returns (drops, review_flag)."""
    def Key(Row):
        Score = PairScore(Row["Rel"])
        if WithQuality:
            Score = Score + (int(Row.get("Height") or 0), int(Row.get("Kbps") or 0))
        return Score
    Ranked = sorted(Group, key=lambda R: (Key(R), R["Rel"]), reverse=False)
    Best = max(Ranked, key=Key)
    Ties = [R for R in Ranked if Key(R) == Key(Best)]
    Review = len(Ties) > 1
    Keep = min(Ties, key=lambda R: R["Rel"]) if Review else Best
    return [R for R in Group if R is not Keep], Review


def LoadFindings(AuditDir, Only):
    """Return list of (category, relative_path, note)."""
    Out = []
    if "identical" in Only:
        Groups = defaultdict(list)
        with open(os.path.join(AuditDir, "xxx-audit-identical.csv"), newline="", encoding="utf-8") as F:
            for Row in csv.DictReader(F):
                Groups[Row["scene"]].append({"Rel": ToRelative(Row["path"]), "Size": int(Row["size"])})
        for Scene, Group in Groups.items():
            Drops, Review = ChooseDrops(Group, WithQuality=False)
            for D in Drops:
                Out.append(("identical", D["Rel"], D["Size"], "REVIEW" if Review else ""))
    if "release-dups" in Only:
        Groups = defaultdict(list)
        with open(os.path.join(AuditDir, "xxx-audit-release-dups.csv"), newline="", encoding="utf-8") as F:
            for Row in csv.DictReader(F):
                Groups[Row["release_key"]].append({
                    "Rel": "Videos/" + Row["path"], "Size": int(Row["size"]),
                    "Height": Row["height"], "Kbps": Row["kbps"]})
        for Key, Group in Groups.items():
            Drops, Review = ChooseDrops(Group, WithQuality=True)
            for D in Drops:
                Out.append(("release-dups", D["Rel"], D["Size"], "REVIEW" if Review else ""))
    if "masquerade" in Only:
        with open(os.path.join(AuditDir, "xxx-audit-masquerade.csv"), newline="", encoding="utf-8") as F:
            for Row in csv.DictReader(F):
                Out.append(("masquerade", ToRelative(Row["path"]), int(Row["size"]),
                            f"claims {Row['claimed']}p actual {Row['actual_w']}x{Row['actual_h']}"))
    if "starved" in Only:
        with open(os.path.join(AuditDir, "xxx-audit-starved.csv"), newline="", encoding="utf-8") as F:
            for Row in csv.DictReader(F):
                Out.append(("starved", ToRelative(Row["path"]), int(Row["size"]),
                            f"claims {Row['claimed']}p at {Row['kbps']} kbps"))
    return Out


def UnlinkDiskFiles(Paths):
    Ok, Missing, Errors = 0, 0, []
    for P in Paths:
        try:
            if os.path.isfile(P):
                os.remove(P)
                Ok += 1
            else:
                Missing += 1
        except OSError as E:
            Errors.append((P, str(E)))
    return Ok, Missing, Errors


def Main():
    Ap = argparse.ArgumentParser()
    Ap.add_argument("--audit-dir", required=True)
    Ap.add_argument("--only", default=",".join(CATEGORIES), help="comma list of " + ",".join(CATEGORIES))
    Ap.add_argument("--commit", action="store_true")
    Ap.add_argument("--delete-disk", action="store_true")
    Ap.add_argument("--skip-review", action="store_true", help="leave pairs the keep rule could not decide")
    Args = Ap.parse_args()
    if Args.delete_disk and not Args.commit:
        print("ERROR: --delete-disk requires --commit", file=sys.stderr)
        sys.exit(2)
    Only = {C.strip() for C in Args.only.split(",")}
    Bad = Only - set(CATEGORIES)
    if Bad:
        print(f"ERROR: unknown category {Bad}", file=sys.stderr)
        sys.exit(2)

    Mode = "COMMIT" if Args.commit else "DRY-RUN"
    print(f"=== CullXxxAuditFindings [{Mode}] only={','.join(sorted(Only))} ===")

    Findings = LoadFindings(Args.audit_dir, Only)
    if Args.skip_review:
        Findings = [F for F in Findings if F[3] != "REVIEW"]
    Seen = set()
    Findings = [F for F in Findings if not (F[1] in Seen or Seen.add(F[1]))]

    Repo = MediaFilesRepository()
    Rels = [F[1] for F in Findings]
    Rows = Repo.DatabaseService.ExecuteQuery(
        "SELECT Id, RelativePath FROM MediaFiles WHERE StorageRootId = %s AND RelativePath = ANY(%s)",
        (STORAGE_ROOT_ID_XXX, Rels),
    ) if Rels else []
    IdByRel = {(R.get("RelativePath") or R.get("relativepath")): int(R.get("Id") or R.get("id")) for R in Rows}

    ByCat = defaultdict(lambda: [0, 0, 0])
    for Cat, Rel, Size, Note in Findings:
        ByCat[Cat][0] += 1
        ByCat[Cat][1] += Size
        ByCat[Cat][2] += 1 if Rel in IdByRel else 0
        Flag = f"  [{Note}]" if Note else ""
        print(f"  {Cat:13} {'db' if Rel in IdByRel else '--':2} {Size / 2**30:6.2f} GiB  {Rel}{Flag}")
    print()
    for Cat, (N, Bytes, InDb) in ByCat.items():
        print(f"  {Cat:13} files={N:3}  {Bytes / 2**30:7.1f} GiB  with MediaFiles row={InDb}")
    Total = sum(V[1] for V in ByCat.values())
    print(f"  {'TOTAL':13} files={len(Findings):3}  {Total / 2**30:7.1f} GiB")
    Ids = sorted(IdByRel.values())
    if Ids:
        print()
        print("  Per-table row counts for MediaFiles ids:")
        for Table, N in Repo.CountMediaFileReferences(Ids).items():
            print(f"    {Table:<32} rows={N}")

    if not Args.commit:
        print()
        print("DRY-RUN complete. No changes made. Re-run with --commit [--delete-disk] to execute.")
        return

    if Ids:
        print()
        print("Executing DB deletes in a single transaction...")
        try:
            for Table, N in Repo.PurgeMediaFilesById(Ids).items():
                print(f"  DELETE {Table:<32} rows={N}")
        except Exception as E:
            print(f"ERROR: {E}", file=sys.stderr)
            sys.exit(1)

    if Args.delete_disk:
        Canon = [ToCanonical(F[1]) for F in Findings]
        print()
        print(f"Unlinking {len(Canon)} files on disk...")
        Ok, Missing, Errors = UnlinkDiskFiles(Canon)
        print(f"  deleted: {Ok}")
        print(f"  missing: {Missing}")
        print(f"  errors:  {len(Errors)}")
        for P, Msg in Errors[:20]:
            print(f"    {P}: {Msg}")
        NotifyJellyfin([{"Path": P, "UpdateType": "Deleted"} for P in Canon])
        print(f"  Jellyfin notified: {len(Canon)} Deleted")


if __name__ == "__main__":
    Main()
