from typing import Optional
from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.MediaFiles.MediaFilesRepository import MediaFilesRepository
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
        MediaFilesRepo: Optional[MediaFilesRepository] = None,
    ):
        # see work-bucket.C3
        self.Db = Db or DatabaseService()
        self.ProfileRepo = ProfileRepo or SeriesProfileRepository(self.Db)
        self.MediaFilesRepo = MediaFilesRepo or MediaFilesRepository(self.Db)

    # directive: work-transcode-unified | # see work-bucket.C3
    def SetProfile(self, Identity: SeriesIdentity, RawProfileName: str) -> int:
        # see work-bucket.C3
        Profile = ProfileName(RawProfileName, Db=self.Db)
        self.ProfileRepo.UpsertProfile(Identity, Profile.Value)
        Affected = self.MediaFilesRepo.PropagateSeriesProfile(Identity, Profile.Value)
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
