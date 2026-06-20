from typing import List, Optional, Tuple

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


# directive: container-vertical
class ContainerVertical:
    """Container compliance vertical: writes (ContainerCompliant, ContainerCompliantReason) per MediaFileId. Reads ContainerComplianceRules fresh per call."""

    # directive: container-vertical
    def __init__(self, Db: Optional[DatabaseService] = None):
        self._Db = Db or DatabaseService()

    # directive: container-vertical
    def RecomputeFor(self, MediaFileIds: List[int]) -> None:
        """Per-id: evaluate container compliance + write columns. No try/except: failures propagate."""
        Rules = self._LoadRules()
        for Id in MediaFileIds:
            Compliant, Reason = self._EvaluateOne(Id, Rules)
            self._WriteResult(Id, Compliant, Reason)

    # directive: container-vertical
    def _LoadRules(self) -> Tuple[set, set]:
        """Fresh DB read per call (db-is-authority). Returns (acceptable_containers, acceptable_audio_codecs)."""
        Rows = self._Db.ExecuteQuery(
            "SELECT AcceptableContainersCsv, AcceptableAudioCodecsCsv "
            "FROM ContainerComplianceRules ORDER BY Id LIMIT 1"
        )
        if not Rows:
            raise RuntimeError("ContainerComplianceRules has no rows -- migration not applied")
        Row = Rows[0]
        return (self._ParseCsv(Row['AcceptableContainersCsv']), self._ParseCsv(Row['AcceptableAudioCodecsCsv']))

    # directive: container-vertical
    def _EvaluateOne(self, MediaFileId: int, Rules):
        AcceptableContainers, AcceptableAudio = Rules
        Rows = self._Db.ExecuteQuery(
            "SELECT ContainerFormat, AudioCodec FROM MediaFiles WHERE Id = %s",
            (MediaFileId,),
        )
        if not Rows:
            raise ValueError(f"MediaFileId {MediaFileId} not found")
        Mf = Rows[0]
        Container = (Mf.get('ContainerFormat') or '').lower()
        ContainerParts = {Tok.strip() for Tok in Container.split(',') if Tok.strip()}
        AudioCodec = (Mf.get('AudioCodec') or '').lower()
        if ContainerParts and not (ContainerParts & AcceptableContainers):
            return (False, f"container_not_acceptable:{sorted(ContainerParts)[0] if ContainerParts else '?'}")
        if AudioCodec and AudioCodec not in AcceptableAudio:
            return (False, f"audio_codec_not_acceptable:{AudioCodec}")
        return (True, None)

    # directive: container-vertical
    def _WriteResult(self, MediaFileId: int, Compliant, Reason):
        self._Db.ExecuteNonQuery(
            "UPDATE MediaFiles SET ContainerCompliant = %s, ContainerCompliantReason = %s WHERE Id = %s",
            (Compliant, Reason, MediaFileId),
        )

    # directive: container-vertical
    @staticmethod
    def _ParseCsv(Csv: str) -> set:
        if not Csv:
            return set()
        return {Tok.strip().lower() for Tok in Csv.split(',') if Tok.strip()}
