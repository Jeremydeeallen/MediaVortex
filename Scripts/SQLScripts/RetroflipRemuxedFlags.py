"""Retro-flip MediaFiles incorrectly marked TranscodedByMediaVortex.

See Features/FileReplacement/remuxed-flag.feature.md criteria 6, 7, 8.

Heuristic: rows where TranscodedByMediaVortex=TRUE AND Codec NOT IN ('av1')
were never actually transcoded by MediaVortex (all profiles emit av1).
They were either container-fixed (Remux) or audio-normalized (AudioFix /
SubtitleFix). Flip TranscodedByMediaVortex=FALSE + RemuxedByMediaVortex=TRUE
+ RemuxedByMediaVortexDate=NOW(). Also clear the paired
TranscodeFiles.SuccessfullyTranscoded=FALSE so SmartPopulate sees consistent
state.

Idempotent. Pass --dry-run to preview without writing.

Usage:
    py Scripts/SQLScripts/RetroflipRemuxedFlags.py --dry-run
    py Scripts/SQLScripts/RetroflipRemuxedFlags.py
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


def Run(DryRun: bool = False) -> int:
    Db = DatabaseService()

    PreviewRows = Db.ExecuteQuery(
        "SELECT COUNT(*) AS Total, COALESCE(SUM(SizeMB)::bigint, 0) AS TotalMB "
        "FROM MediaFiles WHERE TranscodedByMediaVortex = TRUE AND Codec NOT IN ('av1')",
        (),
    )
    Total = int(PreviewRows[0].get('Total', 0)) if PreviewRows else 0
    TotalMB = int(PreviewRows[0].get('TotalMB', 0)) if PreviewRows else 0
    print(f"Candidates: {Total} files, {TotalMB / 1024:.1f} GB total")

    if Total == 0:
        print("Nothing to do.")
        return 0

    SampleRows = Db.ExecuteQuery(
        "SELECT FilePath, SizeMB, Codec, Resolution FROM MediaFiles "
        "WHERE TranscodedByMediaVortex = TRUE AND Codec NOT IN ('av1') "
        "ORDER BY SizeMB DESC LIMIT 5",
        (),
    )
    print("Top 5 by size:")
    for R in SampleRows:
        print(f"  {R.get('SizeMB'):>8.1f} MB  {R.get('Codec'):<5}  {R.get('Resolution'):<12}  {R.get('FilePath')}")

    if DryRun:
        print("\n[DRY RUN] No rows written. Re-run without --dry-run to apply.")
        return 0

    MfAffected = Db.ExecuteNonQuery(
        "UPDATE MediaFiles "
        "SET TranscodedByMediaVortex = FALSE, "
        "    RemuxedByMediaVortex = TRUE, "
        "    RemuxedByMediaVortexDate = COALESCE(RemuxedByMediaVortexDate, NOW()) "
        "WHERE TranscodedByMediaVortex = TRUE AND Codec NOT IN ('av1')",
        (),
    )
    print(f"MediaFiles flipped: {MfAffected}")

    TfAffected = Db.ExecuteNonQuery(
        "UPDATE TranscodeFiles "
        "SET SuccessfullyTranscoded = FALSE "
        "WHERE SuccessfullyTranscoded = TRUE "
        "  AND MediaFileId IN ("
        "    SELECT Id FROM MediaFiles "
        "    WHERE RemuxedByMediaVortex = TRUE AND TranscodedByMediaVortex = FALSE AND Codec NOT IN ('av1')"
        "  )",
        (),
    )
    print(f"TranscodeFiles cleared: {TfAffected}")

    print("Done.")
    return 0


def main():
    Parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    Parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    Args = Parser.parse_args()
    return Run(DryRun=Args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
