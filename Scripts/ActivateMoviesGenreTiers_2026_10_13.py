# directive: movies-video-rule | # see video-encoding.C1
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Core.Database.DatabaseService import DatabaseService
from Features.ContentClassifier.ContentClassifierService import ContentClassifierService
from Features.ContentClassifier.MovieGenreSyncService import MovieGenreSyncService
from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService


MOVIES_LIBRARY_NAME = 'movies'
MOVIES_DEFAULT_TIER = 2
MOVIES_GENRE_SOURCE = 'radarr'
RECOMPUTE_BATCH = 500


# directive: movies-video-rule | # see video-encoding.C1
def Run():
    Db = DatabaseService()
    Db.ExecuteNonQuery(
        "UPDATE StorageRoots SET GenreSource = %s WHERE Name = %s AND GenreSource IS NULL",
        (MOVIES_GENRE_SOURCE, MOVIES_LIBRARY_NAME),
    )
    Db.ExecuteNonQuery(
        "UPDATE StorageRoots SET DefaultQualityTier = %s WHERE Name = %s AND DefaultQualityTier IS NULL",
        (MOVIES_DEFAULT_TIER, MOVIES_LIBRARY_NAME),
    )
    for R in Db.ExecuteQuery("SELECT Id, Name, DefaultQualityTier, GenreSource FROM StorageRoots ORDER BY Id"):
        print(f"  StorageRoot {R.get('Id')} {R.get('Name')}: DefaultQualityTier={R.get('DefaultQualityTier')} GenreSource={R.get('GenreSource')}")
    Synced = MovieGenreSyncService(Db).SyncMissing()
    print(f"  genres recorded for {Synced} files")
    Rows = Db.ExecuteQuery(
        "SELECT mf.Id FROM MediaFiles mf JOIN StorageRoots sr ON sr.Id = mf.StorageRootId "
        "WHERE sr.Name = %s ORDER BY mf.Id",
        (MOVIES_LIBRARY_NAME,),
    )
    Ids = [int(R.get('Id')) for R in Rows]
    Reassigned = ContentClassifierService().ReassignTierProfiles(Ids)
    print(f"  {Reassigned} profiles reassigned to the genre tier")
    Recompute = QueueManagementBusinessService()
    for I in range(0, len(Ids), RECOMPUTE_BATCH):
        Recompute.RecomputeForFiles(Ids[I:I + RECOMPUTE_BATCH])
    print(f"  {len(Ids)} files re-evaluated")
    return 0


if __name__ == '__main__':
    raise SystemExit(Run())
