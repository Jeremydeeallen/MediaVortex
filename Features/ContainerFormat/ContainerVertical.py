from typing import List, Optional, Tuple

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Repositories.DatabaseManager import DatabaseManager
from Features.Profiles.EffectiveProfileResolver import EffectiveProfileResolver


# directive: compliance-symmetry
_CONTAINER_ALIASES = {
    'mp4': {'mp4', 'mov', 'm4a', 'm4v', '3gp', '3g2', 'mj2'},
    'mov': {'mp4', 'mov', 'm4a', 'm4v', '3gp', '3g2', 'mj2'},
    'm4v': {'mp4', 'mov', 'm4a', 'm4v', '3gp', '3g2', 'mj2'},
    'mkv': {'mkv', 'matroska', 'webm'},
}


# directive: compliance-symmetry
class ContainerVertical:

    # directive: compliance-symmetry
    def __init__(self, Db: Optional[DatabaseService] = None, RepoMgr: Optional[DatabaseManager] = None, ProfileResolver: Optional[EffectiveProfileResolver] = None):
        self._Db = Db or DatabaseService()
        self._RepoMgr = RepoMgr or DatabaseManager()
        self._Resolver = ProfileResolver or EffectiveProfileResolver()

    # directive: compliance-symmetry
    def Evaluate(self, Mf) -> Tuple[Optional[bool], Optional[str]]:
        Profile = self._Resolver.Resolve(Mf)
        if Profile is None:
            return (None, 'no_effective_profile')
        if not Profile.Container:
            return (None, 'no_profile_container')

        SourceParts = self._ExtractContainerParts(Mf)
        if not SourceParts:
            return (None, 'no_source_container')

        TargetContainer = Profile.Container.lower()
        AcceptableSet = _CONTAINER_ALIASES.get(TargetContainer, {TargetContainer})
        if not (SourceParts & AcceptableSet):
            return (False, f'container:{sorted(SourceParts)[0]}')
        return (True, None)

    # directive: compliance-symmetry
    @staticmethod
    def _ExtractContainerParts(Mf) -> set:
        if hasattr(Mf, 'get'):
            Raw = Mf.get('ContainerFormat')
        else:
            Raw = getattr(Mf, 'ContainerFormat', None)
        if not Raw:
            return set()
        return {Tok.strip().lower() for Tok in str(Raw).split(',') if Tok.strip()}

    # directive: compliance-symmetry
    def RecomputeFor(self, MediaFileIds: List[int]) -> None:
        for Id in MediaFileIds:
            Mf = self._RepoMgr.GetMediaFileById(Id)
            if Mf is None:
                raise ValueError(f"MediaFileId {Id} not found")
            Compliant, Reason = self.Evaluate(Mf)
            self._WriteResult(Id, Compliant, Reason)

    # directive: compliance-symmetry
    def _WriteResult(self, MediaFileId: int, Compliant, Reason):
        self._Db.ExecuteNonQuery(
            "UPDATE MediaFiles SET ContainerCompliant = %s, ContainerCompliantReason = %s WHERE Id = %s",
            (Compliant, Reason, MediaFileId),
        )
