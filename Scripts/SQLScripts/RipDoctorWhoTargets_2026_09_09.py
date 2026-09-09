import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService
from Core.Path.LocalPath import LocalExists
from Core.Path.Path import Path
from Core.Path.Worker import Worker


_TARGET_QUERY = (
    "SELECT mf.Id, mf.StorageRootId, mf.RelativePath, mf.SizeMB "
    "FROM MediaFiles mf "
    "WHERE mf.RelativePath ILIKE %s "
    "AND ( "
    "  mf.ResolutionCategory NOT IN ('720p','1080p','4k','2160p') "
    "  OR mf.HasDoubleBoostSuspect = TRUE "
    ") "
    "ORDER BY mf.Id"
)


def Main():
    Db = DatabaseService()
    Rows = Db.ExecuteQuery(_TARGET_QUERY, ('%Doctor Who%',))
    print(f"Targets: {len(Rows)} files")
    Wk = Worker(Name='I9-2024', Platform='windows', Db=Db)
    Deleted = 0
    Missing = 0
    Errors = []
    for R in Rows:
        Sid = int(R['storagerootid'])
        Rel = str(R['relativepath'])
        Local = Path(Sid, Rel).Resolve(Wk)
        if LocalExists(Local):
            try:
                os.remove(Local)
                Deleted += 1
                print(f"[del] {Local}")
            except Exception as Ex:
                Errors.append((Local, str(Ex)))
                print(f"[ERR] {Local}: {Ex}")
        else:
            Missing += 1
            print(f"[miss] {Local}")
    print(f"\nDisk summary: {len(Rows)} targets, {Deleted} deleted, {Missing} missing, {len(Errors)} errors")
    if Errors:
        print("Errors:")
        for P, E in Errors[:20]:
            print(f"  {P}: {E}")

    Ids = [int(R['id']) for R in Rows]
    IdList = ','.join(str(I) for I in Ids)
    PendingDeleted = Db.ExecuteNonQuery(
        "DELETE FROM TranscodeQueue WHERE Status='Pending' AND MediaFileId IN (" + IdList + ")"
    )
    MfDeleted = Db.ExecuteNonQuery(
        "DELETE FROM MediaFiles WHERE Id IN (" + IdList + ")"
    )
    print(f"\nDB summary: {PendingDeleted} Pending queue rows deleted, {MfDeleted} MediaFiles rows deleted")


if __name__ == '__main__':
    Main()
