from typing import List, Tuple, Optional
from Core.Database.BaseRepository import BaseRepository
from Core.Logging.LoggingService import LoggingService


# directive: compliance-writeback-invariant | # see compliance.C8
class ComplianceWriteRepository(BaseRepository):
    """Owns the bulk UPDATE that persists per-row recompute results to MediaFiles; Layer 2 of the writeback invariant (compliance.C8 / ST9)."""

    # directive: compliance-writeback-invariant | # see compliance.C8
    def BulkWriteRecomputeResults(self, Updates: List[Tuple]) -> Tuple[int, int]:
        """Validate each tuple against the C6 three-way disjunction; persist valid rows via UPDATE FROM VALUES; refuse + WARN-log invalid rows. Tuple shape: (Id, AssignedProfile, PriorityScore, IsCompliant, DeferReason, WorkBucket, OperationsNeededCsv, ComplianceGateBlocked). Returns (written, refused) per compliance.C8."""
        if not Updates:
            return (0, 0)
        Valid: List[Tuple] = []
        Refused = 0
        for Row in Updates:
            if not self._IsCompliantTuple(Row):
                LoggingService.LogWarning(
                    "compliance.C8 layer-2 refusal: contradictory ComplianceDecision tuple MediaFileId=" + str(Row[0]) + " tuple=" + repr(Row),
                    "ComplianceWriteRepository", "BulkWriteRecomputeResults"
                )
                Refused += 1
                continue
            Valid.append(Row)
        if not Valid:
            return (0, Refused)
        try:
            ValuesClause = ','.join(
                "(" + str(int(Id)) + "," + self._SqlText(P) + "," + str(int(S)) + "," + self._SqlBool(Ic) + "," + self._SqlText(Dr) + "," + self._SqlText(Wb) + "," + self._SqlText(Ops) + "," + self._SqlText(Gb) + ")"
                for Id, P, S, Ic, Dr, Wb, Ops, Gb in Valid
            )
            Query = (
                "UPDATE MediaFiles "
                "SET AssignedProfile = v.profile, "
                "PriorityScore = v.score, "
                "IsCompliant = v.compliant::boolean, "
                "AdmissionDeferReason = v.defer_reason, "
                "OperationsNeededCsv = v.ops_csv, "
                "ComplianceGateBlocked = v.gate_blocked, "
                "ComplianceEvaluatedAt = NOW() "
                "FROM (VALUES " + ValuesClause + ") "
                "AS v(id, profile, score, compliant, defer_reason, work_bucket, ops_csv, gate_blocked) "
                "WHERE MediaFiles.Id = v.id"
            )
            self.ExecuteNonQuery(Query)
            return (len(Valid), Refused)
        except Exception as Ex:
            LoggingService.LogException("BulkWriteRecomputeResults failed", Ex, "ComplianceWriteRepository", "BulkWriteRecomputeResults")
            return (0, Refused)

    @staticmethod
    # directive: compliance-writeback-invariant | # see compliance.C8
    def _IsCompliantTuple(Row: Tuple) -> bool:
        """Apply the C6 three-way disjunction to a tuple shaped (Id, Profile, Score, IsCompliant, DeferReason, WorkBucket, OperationsNeededCsv, GateBlocked)."""
        try:
            _Id, _P, _S, Ic, _Dr, Wb, Ops, Gb = Row
        except (ValueError, TypeError):
            return False
        OpsEmpty = (Ops is None) or (Ops == '')
        CompliantClean = (Ic is True) and (Wb is None) and OpsEmpty
        NonCompliantBucketed = (Ic is False) and (Wb is not None) and (not OpsEmpty)
        GateBlockedNone = (Ic is None) and (Gb is not None) and (Wb is None) and OpsEmpty
        return CompliantClean or NonCompliantBucketed or GateBlockedNone

    @staticmethod
    # directive: compliance-writeback-invariant | # see compliance.C8
    def _SqlText(V: Optional[str]) -> str:
        """Escape single quotes; NULL when value is None."""
        if V is None:
            return 'NULL'
        return "'" + str(V).replace("'", "''") + "'"

    @staticmethod
    # directive: compliance-writeback-invariant | # see compliance.C8
    def _SqlBool(V: Optional[bool]) -> str:
        """Three-valued: True/False/NULL."""
        if V is None:
            return 'NULL'
        return 'true' if V else 'false'
