import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from Core.Database.DatabaseService import DatabaseService
from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService


# directive: transcode-flow-canonical -- one-shot bulk recompute for MediaFiles rows whose compliance flags are NULL (never evaluated) OR whose TranscodedByMediaVortex was just self-healed to TRUE (metadata drift). Idempotent + chunked.
def Main():
    Db = DatabaseService()
    Rows = Db.ExecuteQuery(
        "SELECT id FROM MediaFiles "
        "WHERE videocompliant IS NULL OR containercompliant IS NULL OR audiocompliant IS NULL "
        "ORDER BY id"
    )
    Ids = [int(R['id']) for R in Rows]
    Total = len(Ids)
    if Total == 0:
        print("No NULL-compliance rows to recompute.")
        return 0
    Chunk = 500
    print(f"Recomputing compliance for {Total} MediaFiles in chunks of {Chunk}...")
    Svc = QueueManagementBusinessService()
    Done = 0
    for I in range(0, Total, Chunk):
        Batch = Ids[I:I + Chunk]
        Updated = Svc.RecomputeForFiles(Batch)
        Done += len(Batch)
        print(f"  {Done}/{Total} recomputed (last batch UPDATE count={Updated})")
    print(f"Done: {Total} MediaFiles recomputed.")
    return 0


if __name__ == '__main__':
    sys.exit(Main())
