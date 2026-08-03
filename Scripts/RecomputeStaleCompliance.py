import argparse
import sys

sys.path.insert(0, ".")

from Features.MediaFiles.MediaFilesRepository import MediaFilesRepository
from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService


def Main():
    Parser = argparse.ArgumentParser(description="Recompute compliance for rows stuck on missing_input:*")
    Parser.add_argument("--DryRun", action="store_true", help="List affected rows without recomputing")
    Parser.add_argument("--Limit", type=int, default=None, help="Cap number of rows processed")
    Args = Parser.parse_args()

    Repo = MediaFilesRepository()
    Rows = Repo.GetStaleComplianceRows(Limit=Args.Limit)

    print(f"Found {len(Rows)} stuck rows.")
    for R in Rows:
        print(f"  Id={R['id']} reason={R['videocompliantreason']!r} filename={R['filename']}")

    if Args.DryRun:
        print("Dry run -- no writes.")
        return 0

    if not Rows:
        return 0

    Ids = [R["id"] for R in Rows]
    Updated = QueueManagementBusinessService().RecomputeForFiles(Ids)
    print(f"Recomputed {Updated} rows.")
    return 0


if __name__ == "__main__":
    sys.exit(Main())
