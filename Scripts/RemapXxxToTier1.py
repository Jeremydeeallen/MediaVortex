import sys

sys.path.insert(0, ".")

from Core.Database.DatabaseService import DatabaseService
from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService


# directive: ingest-pipeline-kiss (follow-up)
def Main():
    Db = DatabaseService()
    Rows = Db.ExecuteQuery(
        "SELECT Id FROM MediaFiles "
        "WHERE AssignedProfile = %s "
        "  AND ResolutionCategory IN ('1080p','720p','480p')",
        ('STREAMING QSV AV1 P1 HQ -2160p',),
    )
    Ids = [R['id'] for R in Rows]
    if not Ids:
        print("No rows to remap.")
        return 0

    Affected = Db.ExecuteNonQuery(
        "UPDATE MediaFiles "
        "SET AssignedProfile = %s, AssignedProfileSource = 'operator' "
        "WHERE Id = ANY(%s)",
        ('AV1 Tier 1 Efficient', Ids),
    )
    print(f"Reassigned {Affected} rows to 'AV1 Tier 1 Efficient'.")

    Updated = QueueManagementBusinessService().RecomputeForFiles(Ids)
    print(f"Cascade recomputed compliance for {Updated} rows.")
    return 0


if __name__ == "__main__":
    sys.exit(Main())
