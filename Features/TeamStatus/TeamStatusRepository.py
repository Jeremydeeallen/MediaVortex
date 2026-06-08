# directive: worker-routing | # see worker-routing.C15

from typing import Any, Dict, List, Optional

from Core.Database.BaseRepository import BaseRepository


CAPABILITY_COLUMNS = ('TranscodeEnabled', 'QualityTestEnabled', 'ScanEnabled', 'RemuxEnabled', 'NvencCapable')


# directive: worker-routing | # see worker-routing.C15
class TeamStatusRepository(BaseRepository):
    """SQL boundary for the TeamStatus controller. All Workers reads/writes used by /api/TeamStatus live here."""

    # directive: worker-routing | # see worker-routing.C15
    def GetAllWorkerRows(self, IncludeDisabled: bool) -> List[Dict[str, Any]]:
        """Main worker list query for /Activity. Returns one row per Workers row including nvenccapable."""
        Where = '' if IncludeDisabled else 'WHERE Enabled = TRUE'
        Query = (
            "SELECT WorkerName, Platform, Status, LastHeartbeat, "
            "MaxConcurrentJobs, MaxCpuThreads, AcceptsInterlaced, "
            "TranscodeEnabled, QualityTestEnabled, ScanEnabled, RemuxEnabled, "
            "nvenccapable, "
            "MaxConcurrentTranscodeJobs, MaxConcurrentQualityTestJobs, MaxConcurrentRemuxJobs, "
            "Enabled, Version, BuildInfo, MountValidationError, "
            "EXTRACT(EPOCH FROM (NOW() - LastHeartbeat)) AS HeartbeatAgeSec "
            "FROM Workers " + Where + " ORDER BY WorkerName"
        )
        return self.DatabaseService.ExecuteQuery(Query) or []

    # directive: worker-routing | # see worker-routing.C15
    def WorkerExists(self, WorkerName: str) -> bool:
        """True iff a Workers row with this WorkerName exists."""
        Rows = self.DatabaseService.ExecuteQuery(
            "SELECT 1 FROM Workers WHERE WorkerName = %s", (WorkerName,)
        )
        return bool(Rows)

    # directive: worker-routing | # see worker-routing.C15
    def UpdateWorkerCapability(self, WorkerName: str, UpdateColumns: Dict[str, Optional[bool]]) -> None:
        """Update one or more capability flags on a Workers row. Caller validates keys against CAPABILITY_COLUMNS."""
        if not UpdateColumns:
            return
        SetClauses = ', '.join(Col + ' = %s' for Col in UpdateColumns.keys())
        Params = tuple(UpdateColumns.values()) + (WorkerName,)
        self.DatabaseService.ExecuteNonQuery(
            "UPDATE Workers SET " + SetClauses + " WHERE WorkerName = %s", Params
        )

    # directive: worker-routing | # see worker-routing.C15
    def GetWorkerCapabilities(self, WorkerName: str) -> Dict[str, Any]:
        """Return the capability flags for a single worker (used by SetWorkerCapability response)."""
        Rows = self.DatabaseService.ExecuteQuery(
            "SELECT WorkerName, TranscodeEnabled, QualityTestEnabled, ScanEnabled, RemuxEnabled, nvenccapable "
            "FROM Workers WHERE WorkerName = %s", (WorkerName,)
        )
        return Rows[0] if Rows else {}
