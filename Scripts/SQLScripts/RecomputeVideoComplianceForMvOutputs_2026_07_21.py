# directive: e2e-bug-fixes | # see e2e-bug-fixes.C31
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService
from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService


def Main():
    Db = DatabaseService()
    Rows = Db.ExecuteQuery(
        "SELECT Id FROM MediaFiles WHERE TranscodedByMediaVortex = TRUE ORDER BY Id"
    )
    Ids = [int(R.get('id')) for R in Rows]
    print(f"Recomputing full compliance (Audio + Video + Container + WorkBucket) for {len(Ids)} MediaVortex-transcoded rows.")
    Service = QueueManagementBusinessService()
    Batch = 500
    Total = 0
    for I in range(0, len(Ids), Batch):
        Chunk = Ids[I:I + Batch]
        Service.RecomputeForFiles(Chunk)
        Total += len(Chunk)
        print(f"  Progress: {Total}/{len(Ids)}")
    StuckVideo = Db.ExecuteQuery(
        "SELECT COUNT(*) AS n FROM MediaFiles WHERE TranscodedByMediaVortex = TRUE "
        "AND (VideoCompliant = FALSE OR VideoCompliantReason IS NULL "
        "     OR VideoCompliantReason NOT LIKE 'mediavortex_output_accepted%%')"
    )
    StuckBucket = Db.ExecuteQuery(
        "SELECT COUNT(*) AS n FROM MediaFiles WHERE TranscodedByMediaVortex = TRUE AND WorkBucket = 'Transcode'"
    )
    RemainingVideo = int(StuckVideo[0].get('n')) if StuckVideo else 0
    RemainingBucket = int(StuckBucket[0].get('n')) if StuckBucket else 0
    print(f"Rows failing video-exempt invariant: {RemainingVideo}")
    print(f"Rows still in Transcode bucket: {RemainingBucket}")
    if RemainingVideo != 0:
        raise SystemExit(f"Migration incomplete: {RemainingVideo} rows still non-exempt on video")
    if RemainingBucket != 0:
        raise SystemExit(f"Migration incomplete: {RemainingBucket} rows still in Transcode bucket")


if __name__ == '__main__':
    Main()
