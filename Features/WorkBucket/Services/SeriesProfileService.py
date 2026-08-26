# directive: tv-tier1-classifier-pin | # see work-bucket.feature.md C3
from typing import Optional
from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.MediaFiles.MediaFilesRepository import MediaFilesRepository
from Features.MediaFiles.ProfileAssignmentService import ProfileAssignmentService
from Features.WorkBucket.Domain.ProfileName import ProfileName
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity
from Features.WorkBucket.Repositories.SeriesProfileRepository import SeriesProfileRepository


class SeriesProfileService:

    # directive: tv-tier1-classifier-pin
    def __init__(
        self,
        Db: Optional[DatabaseService] = None,
        ProfileRepo: Optional[SeriesProfileRepository] = None,
        MediaFilesRepo: Optional[MediaFilesRepository] = None,
        ProfileWriter: Optional[ProfileAssignmentService] = None,
    ):
        self.Db = Db or DatabaseService()
        self.ProfileRepo = ProfileRepo or SeriesProfileRepository(self.Db)
        self.MediaFilesRepo = MediaFilesRepo or MediaFilesRepository(self.Db)
        self.ProfileWriter = ProfileWriter or ProfileAssignmentService(Db=self.Db, Repo=self.MediaFilesRepo)

    # directive: tv-tier1-classifier-pin | # see writer-owns-cascade.md
    def SetProfile(self, Identity: SeriesIdentity, RawProfileName: str) -> int:
        Profile = ProfileName(RawProfileName, Db=self.Db)
        self.ProfileRepo.UpsertProfile(Identity, Profile.Value)
        Ids = self.MediaFilesRepo.SelectUntranscodedInSeries(Identity)
        WrittenIds = self.ProfileWriter.Assign(Ids, Profile.Value, 'series', IfUnsetOnly=False)
        LoggingService.LogInfo(
            f"Series profile set: {Identity.ToCompositeKey()} -> {Profile.Value}, {len(WrittenIds)} files updated",
            "SeriesProfileService",
            "SetProfile",
        )
        return len(WrittenIds)

    # directive: tv-tier1-classifier-pin
    def ClearProfile(self, Identity: SeriesIdentity) -> None:
        self.ProfileRepo.DeleteProfile(Identity)
        LoggingService.LogInfo(
            f"Series profile cleared: {Identity.ToCompositeKey()}",
            "SeriesProfileService",
            "ClearProfile",
        )
