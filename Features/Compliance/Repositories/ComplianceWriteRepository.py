from typing import List, Tuple, Optional
from Core.Database.BaseRepository import BaseRepository
from Core.Logging.LoggingService import LoggingService


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C23
class ComplianceWriteRepository(BaseRepository):
    """Owns the bulk UPDATE that persists per-row recompute results to MediaFiles -- SRP write-only complement to the read-only repositories."""

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C23
    def BulkWriteRecomputeResults(self, Updates: List[Tuple]) -> int:
        """Persist N recompute results in a single UPDATE FROM VALUES. Tuple shape: (Id, AssignedProfile, PriorityScore, IsCompliant, DeferReason, WorkBucket, OperationsNeededCsv, ComplianceGateBlocked). Returns rows updated."""
        if not Updates:
            return 0
        try:
            ValuesClause = ','.join(
                "(" + str(int(Id)) + "," + self._SqlText(P) + "," + str(int(S)) + "," + self._SqlBool(Ic) + "," + self._SqlText(Dr) + "," + self._SqlText(Wb) + "," + self._SqlText(Ops) + "," + self._SqlText(Gb) + ")"
                for Id, P, S, Ic, Dr, Wb, Ops, Gb in Updates
            )
            Query = (
                "UPDATE MediaFiles "
                "SET AssignedProfile = v.profile, "
                "PriorityScore = v.score, "
                "IsCompliant = v.compliant::boolean, "
                "AdmissionDeferReason = v.defer_reason, "
                "WorkBucket = v.work_bucket, "
                "OperationsNeededCsv = v.ops_csv, "
                "ComplianceGateBlocked = v.gate_blocked, "
                "ComplianceEvaluatedAt = NOW() "
                "FROM (VALUES " + ValuesClause + ") "
                "AS v(id, profile, score, compliant, defer_reason, work_bucket, ops_csv, gate_blocked) "
                "WHERE MediaFiles.Id = v.id"
            )
            self.ExecuteNonQuery(Query)
            return len(Updates)
        except Exception as Ex:
            LoggingService.LogException("BulkWriteRecomputeResults failed", Ex, "ComplianceWriteRepository", "BulkWriteRecomputeResults")
            return 0

    @staticmethod
    def _SqlText(V: Optional[str]) -> str:
        """Escape single quotes; NULL when value is None. Inputs come from MediaFiles columns and ComplianceDecision fields (all bounded vocabulary), but defense-in-depth still escapes."""
        if V is None:
            return 'NULL'
        return "'" + str(V).replace("'", "''") + "'"

    @staticmethod
    def _SqlBool(V: Optional[bool]) -> str:
        """Three-valued: True/False/NULL."""
        if V is None:
            return 'NULL'
        return 'true' if V else 'false'
