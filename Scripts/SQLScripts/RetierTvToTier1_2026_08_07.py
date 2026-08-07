import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


TARGET_PROFILE = 'AV1 Tier 1 Efficient'
TV_STORAGE_ROOT_ID = 1


# directive: adhoc-tv-retier -- move every StorageRootId=1 (media_tv) MediaFile off Tier 2/3/none onto Tier 1 + cascade compliance recompute per writer-owns-cascade.
def Run():
    Db = DatabaseService()
    Rows = Db.ExecuteQuery(
        "SELECT Id FROM MediaFiles WHERE StorageRootId = %s "
        "AND (AssignedProfile IS NULL OR AssignedProfile <> %s)",
        (TV_STORAGE_ROOT_ID, TARGET_PROFILE),
    )
    Ids = [int(R['id']) for R in (Rows or [])]
    if not Ids:
        print("No TV files to retier. Nothing to do.")
        return 0

    Db.ExecuteNonQuery(
        "UPDATE MediaFiles SET AssignedProfile = %s, LastModifiedDate = NOW() "
        "WHERE Id = ANY(%s)",
        (TARGET_PROFILE, Ids),
    )
    print(f"Retiered {len(Ids)} TV MediaFiles to {TARGET_PROFILE!r}.")

    from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
    QueueManagementBusinessService().RecomputeForFiles(Ids)
    print(f"Cascade complete: RecomputeForFiles({len(Ids)}) OK.")
    return 0


if __name__ == '__main__':
    raise SystemExit(Run())
