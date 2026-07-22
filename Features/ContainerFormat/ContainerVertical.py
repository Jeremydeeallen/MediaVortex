from typing import List, Optional, Tuple

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.MediaFile.Domain.MediaFileScope import IsAudioOnlyContainer
from Repositories.DatabaseManager import DatabaseManager


# directive: transcode-flow-canonical -- C33 profile-independent baseline
_CONTAINER_ALIASES = {
    'mp4': {'mp4', 'mov', 'm4a', 'm4v', '3gp', '3g2', 'mj2'},
    'mov': {'mp4', 'mov', 'm4a', 'm4v', '3gp', '3g2', 'mj2'},
    'm4v': {'mp4', 'mov', 'm4a', 'm4v', '3gp', '3g2', 'mj2'},
    'mkv': {'mkv', 'matroska', 'webm'},
}


# directive: transcode-flow-canonical -- C33 profile-independent baseline
class ContainerVertical:

    # directive: transcode-flow-canonical -- C33
    def __init__(self, Db: Optional[DatabaseService] = None, RepoMgr: Optional[DatabaseManager] = None):
        self._Db = Db or DatabaseService()
        self._RepoMgr = RepoMgr or DatabaseManager()

    # directive: transcode-flow-canonical -- C33 baseline rules only, no profile lookup
    def _LoadRules(self):
        Rows = self._Db.ExecuteQuery(
            "SELECT AcceptableContainersCsv FROM ContainerComplianceRules ORDER BY Id LIMIT 1"
        )
        if not Rows:
            raise RuntimeError('ContainerComplianceRules has no rows -- migration not applied')
        Csv = (Rows[0].get('AcceptableContainersCsv') or Rows[0].get('acceptablecontainerscsv') or '').strip()
        return [C.strip().lower() for C in Csv.split(',') if C.strip()]

    # directive: transcode-flow-canonical -- C34 audio-only containers short-circuit before rules load
    def Evaluate(self, Mf) -> Tuple[Optional[bool], Optional[str]]:
        if IsAudioOnlyContainer(Mf):
            return (None, 'non_video_scope')
        AllowedContainers = self._LoadRules()
        if not AllowedContainers:
            raise RuntimeError('ContainerComplianceRules.AcceptableContainersCsv is empty')

        SourceParts = self._ExtractContainerParts(Mf)
        if not SourceParts:
            return (None, 'no_source_container')

        AcceptableSet = set()
        for Allowed in AllowedContainers:
            AcceptableSet |= _CONTAINER_ALIASES.get(Allowed, {Allowed})

        if not (SourceParts & AcceptableSet):
            return (False, f'container:{sorted(SourceParts)[0]}')
        return (True, None)

    # directive: transcode-flow-canonical -- C33
    @staticmethod
    def _ExtractContainerParts(Mf) -> set:
        if hasattr(Mf, 'get'):
            Raw = Mf.get('ContainerFormat')
        else:
            Raw = getattr(Mf, 'ContainerFormat', None)
        if not Raw:
            return set()
        return {Tok.strip().lower() for Tok in str(Raw).split(',') if Tok.strip()}

    # directive: transcode-flow-canonical -- C33
    def RecomputeFor(self, MediaFileIds: List[int]) -> None:
        for Id in MediaFileIds:
            Mf = self._RepoMgr.GetMediaFileById(Id)
            if Mf is None:
                raise ValueError(f"MediaFileId {Id} not found")
            Compliant, Reason = self.Evaluate(Mf)
            self._WriteResult(Id, Compliant, Reason)

    # directive: transcode-flow-canonical -- C33
    def _WriteResult(self, MediaFileId: int, Compliant, Reason):
        self._Db.ExecuteNonQuery(
            "UPDATE MediaFiles SET ContainerCompliant = %s, ContainerCompliantReason = %s WHERE Id = %s",
            (Compliant, Reason, MediaFileId),
        )
