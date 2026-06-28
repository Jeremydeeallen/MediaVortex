from typing import Optional
from Core.Database.DatabaseService import DatabaseService
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity


# directive: work-transcode-unified | # see work-bucket.C3
class SeriesProfileRepository:
    """Read/write SeriesProfiles -- per-series sticky AssignedProfile only."""

    # directive: work-transcode-unified | # see work-bucket.C3
    def __init__(self, Db: DatabaseService = None):
        self.Db = Db or DatabaseService()

    # directive: work-transcode-unified | # see work-bucket.C3
    def GetProfile(self, Identity: SeriesIdentity) -> Optional[str]:
        Rows = self.Db.ExecuteQuery(
            "SELECT AssignedProfile FROM SeriesProfiles "
            "WHERE StorageRootId = %s AND RelativePath = %s LIMIT 1",
            (Identity.StorageRootId, Identity.RelativePath),
        )
        if not Rows:
            return None
        return Rows[0].get('assignedprofile')

    # directive: work-transcode-unified | # see work-bucket.C3
    def UpsertProfile(self, Identity: SeriesIdentity, AssignedProfile: str) -> None:
        self.Db.ExecuteNonQuery(
            "INSERT INTO SeriesProfiles (StorageRootId, RelativePath, AssignedProfile, CreatedDate, LastModifiedDate) "
            "VALUES (%s, %s, %s, NOW(), NOW()) "
            "ON CONFLICT (StorageRootId, RelativePath) DO UPDATE "
            "SET AssignedProfile = EXCLUDED.AssignedProfile, LastModifiedDate = NOW()",
            (Identity.StorageRootId, Identity.RelativePath, AssignedProfile),
        )

    # directive: work-transcode-unified | # see work-bucket.C3
    def DeleteProfile(self, Identity: SeriesIdentity) -> None:
        self.Db.ExecuteNonQuery(
            "DELETE FROM SeriesProfiles WHERE StorageRootId = %s AND RelativePath = %s",
            (Identity.StorageRootId, Identity.RelativePath),
        )
