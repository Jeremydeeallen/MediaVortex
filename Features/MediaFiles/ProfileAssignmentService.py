# directive: tv-tier1-classifier-pin | # see writer-owns-cascade.md
from typing import List, Optional

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.MediaFiles.MediaFilesRepository import MediaFilesRepository


class ProfileAssignmentService:
    """SSoT writer of MediaFiles.AssignedProfile. Every write cascades compliance recompute before returning."""

    # directive: tv-tier1-classifier-pin
    def __init__(self, Db: Optional[DatabaseService] = None, Repo: Optional[MediaFilesRepository] = None):
        self.Db = Db or DatabaseService()
        self.Repo = Repo or MediaFilesRepository(self.Db)

    # directive: tv-tier1-classifier-pin | # see writer-owns-cascade.md
    def Assign(self, MediaFileIds: List[int], ProfileName: Optional[str], Source: str, IfUnsetOnly: bool = False) -> List[int]:
        """Write AssignedProfile + AssignedProfileSource then cascade RecomputeForFiles on actually-written Ids."""
        WrittenIds = self.Repo.WriteAssignedProfile(MediaFileIds, ProfileName, Source, IfUnsetOnly=IfUnsetOnly)
        if WrittenIds:
            # Local import: RecomputeForFiles reaches back into MediaFilesRepository via QueueManagementBusinessService.
            from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
            QueueManagementBusinessService().RecomputeForFiles(WrittenIds)
        LoggingService.LogInfo(
            f"ProfileAssignmentService.Assign wrote {len(WrittenIds)}/{len(MediaFileIds or [])} rows profile={ProfileName!r} source={Source!r} sticky={IfUnsetOnly}",
            "ProfileAssignmentService",
            "Assign",
        )
        return WrittenIds
