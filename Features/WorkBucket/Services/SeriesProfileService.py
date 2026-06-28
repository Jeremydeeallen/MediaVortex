from typing import Optional
from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.WorkBucket.Domain.ProfileName import ProfileName
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity
from Features.WorkBucket.Repositories.SeriesProfileRepository import SeriesProfileRepository


# directive: work-transcode-unified | # see work-bucket.C3
class SeriesProfileService:
    """Orchestrates per-series profile assignment -- validate -> persist sticky -> propagate to untranscoded MediaFiles."""

    # directive: work-transcode-unified | # see work-bucket.C3
    def __init__(
        self,
        Db: Optional[DatabaseService] = None,
        ProfileRepo: Optional[SeriesProfileRepository] = None,
    ):
        # see work-bucket.C3
        self.Db = Db or DatabaseService()
        self.ProfileRepo = ProfileRepo or SeriesProfileRepository(self.Db)

    # directive: work-transcode-unified | # see work-bucket.C3
    def SetProfile(self, Identity: SeriesIdentity, RawProfileName: str) -> int:
        # see work-bucket.C3
        Profile = ProfileName(RawProfileName, Db=self.Db)
        self.ProfileRepo.UpsertProfile(Identity, Profile.Value)
        Affected = self.Db.ExecuteNonQuery(
            "UPDATE MediaFiles "
            "   SET AssignedProfile = %s, "
            "       AssignedProfileSource = 'series', "
            "       LastModifiedDate = NOW() "
            " WHERE StorageRootId = %s "
            "   AND split_part(RelativePath, '/', 1) = %s "
            "   AND TranscodedByMediaVortex IS NOT TRUE",
            (Profile.Value, Identity.StorageRootId, Identity.RelativePath),
        )
        Affected = int(Affected) if Affected is not None else 0
        LoggingService.LogInfo(
            f"Series profile set: {Identity.ToCompositeKey()} -> {Profile.Value}, {Affected} files updated",
            "SeriesProfileService",
            "SetProfile",
        )
        return Affected

    # directive: work-transcode-unified | # see work-bucket.C3
    def ClearProfile(self, Identity: SeriesIdentity) -> None:
        """Remove the sticky series profile. Does NOT clear MediaFiles.AssignedProfile -- those rows keep the historical assignment."""
        # see work-bucket.C3
        self.ProfileRepo.DeleteProfile(Identity)
        LoggingService.LogInfo(
            f"Series profile cleared: {Identity.ToCompositeKey()}",
            "SeriesProfileService",
            "ClearProfile",
        )
