# directive: video-compliance-multiplier | # see video-encoding.C6
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Core.Database.DatabaseService import DatabaseService
from Features.VideoEncoding.VideoVertical import VideoVertical


# directive: tv-video-rule-tier1 | # see video-encoding.C1
def Main():
    Db = DatabaseService()
    StorageRootId = int(sys.argv[1]) if len(sys.argv) > 1 else None
    Before = Db.ExecuteQuery("SELECT WorkBucket, COUNT(*) AS n FROM MediaFiles GROUP BY WorkBucket ORDER BY WorkBucket")
    print("Before:")
    for R in Before:
        print(f"  {R.get('workbucket') or '(null)'}: {R.get('n')}")

    if StorageRootId is None:
        Rows = Db.ExecuteQuery("SELECT Id FROM MediaFiles ORDER BY Id")
    else:
        Rows = Db.ExecuteQuery("SELECT Id FROM MediaFiles WHERE StorageRootId = %s ORDER BY Id", (StorageRootId,))
    Ids = [int(R.get('id')) for R in Rows]
    print(f"Recomputing {len(Ids)} MediaFile rows via VideoVertical.RecomputeFor...")

    Vertical = VideoVertical(Db=Db)
    ChunkSize = 500
    for I in range(0, len(Ids), ChunkSize):
        Vertical.RecomputeFor(Ids[I:I + ChunkSize])
        print(f"  {min(I + ChunkSize, len(Ids))}/{len(Ids)}")

    After = Db.ExecuteQuery("SELECT WorkBucket, COUNT(*) AS n FROM MediaFiles GROUP BY WorkBucket ORDER BY WorkBucket")
    print("After:")
    for R in After:
        print(f"  {R.get('workbucket') or '(null)'}: {R.get('n')}")


if __name__ == '__main__':
    Main()
