from typing import List, Optional, Tuple

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


# directive: compliance-rip
class ContainerVertical:
    """Container compliance vertical. Pure `Evaluate(mf)` returns the verdict without writing; `RecomputeFor(ids)` evaluates and writes."""

    # directive: compliance-rip
    def __init__(self, Db: Optional[DatabaseService] = None):
        self._Db = Db or DatabaseService()

    # directive: compliance-rip
    def Evaluate(self, Mf) -> Tuple[Optional[bool], Optional[str]]:
        """Pure verdict: (Compliant, Reason). No DB write."""
        Rules = self._LoadRules()
        return self._EvaluateInternal(Mf, Rules)

    # directive: compliance-rip
    def RecomputeFor(self, MediaFileIds: List[int]) -> None:
        Rules = self._LoadRules()
        for Id in MediaFileIds:
            Mf = self._FetchMediaFileColumns(Id)
            Compliant, Reason = self._EvaluateInternal(Mf, Rules)
            self._WriteResult(Id, Compliant, Reason)

    # directive: compliance-rip
    def _LoadRules(self) -> Tuple[set, set]:
        """Fresh DB read per call (db-is-authority)."""
        Rows = self._Db.ExecuteQuery(
            "SELECT AcceptableContainersCsv, AcceptableAudioCodecsCsv "
            "FROM ContainerComplianceRules ORDER BY Id LIMIT 1"
        )
        if not Rows:
            raise RuntimeError("ContainerComplianceRules has no rows -- migration not applied")
        Row = Rows[0]
        return (self._ParseCsv(Row['AcceptableContainersCsv']), self._ParseCsv(Row['AcceptableAudioCodecsCsv']))

    # directive: compliance-rip
    def _FetchMediaFileColumns(self, MediaFileId: int):
        """Fetch a thin record (Container + AudioCodec) for the pure evaluator."""
        Rows = self._Db.ExecuteQuery(
            "SELECT ContainerFormat, AudioCodec FROM MediaFiles WHERE Id = %s",
            (MediaFileId,),
        )
        if not Rows:
            raise ValueError(f"MediaFileId {MediaFileId} not found")
        return Rows[0]

    # directive: compliance-rip
    def _EvaluateInternal(self, Mf, Rules) -> Tuple[Optional[bool], Optional[str]]:
        AcceptableContainers, AcceptableAudio = Rules
        Container = ''
        if hasattr(Mf, 'get'):
            Container = (Mf.get('ContainerFormat') or '').lower()
            AudioCodec = (Mf.get('AudioCodec') or '').lower()
        else:
            Container = (getattr(Mf, 'ContainerFormat', None) or '').lower()
            AudioCodec = (getattr(Mf, 'AudioCodec', None) or '').lower()
        ContainerParts = {Tok.strip() for Tok in Container.split(',') if Tok.strip()}
        if ContainerParts and not (ContainerParts & AcceptableContainers):
            return (False, f"container_not_acceptable:{sorted(ContainerParts)[0] if ContainerParts else '?'}")
        if AudioCodec and AudioCodec not in AcceptableAudio:
            return (False, f"audio_codec_not_acceptable:{AudioCodec}")
        return (True, None)

    # directive: compliance-rip
    def _WriteResult(self, MediaFileId: int, Compliant, Reason):
        self._Db.ExecuteNonQuery(
            "UPDATE MediaFiles SET ContainerCompliant = %s, ContainerCompliantReason = %s WHERE Id = %s",
            (Compliant, Reason, MediaFileId),
        )

    @staticmethod
    # directive: compliance-rip
    def _ParseCsv(Csv: Optional[str]) -> set:
        if not Csv:
            return set()
        return {Tok.strip().lower() for Tok in Csv.split(',') if Tok.strip()}
