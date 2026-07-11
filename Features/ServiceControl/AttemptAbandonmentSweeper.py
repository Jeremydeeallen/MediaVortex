# directive: transcode-flow-canonical
from typing import Dict, Any

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


ABANDONMENT_MINUTES_DEFAULT = 5


# directive: transcode-flow-canonical
class AttemptAbandonmentSweeper:
    """Cross-worker terminal write path for TranscodeAttempts whose owning Worker is heartbeat-stale + not Online. Idempotent; safe to run on every worker tick."""

    # directive: transcode-flow-canonical
    def __init__(self, DatabaseServiceInstance: DatabaseService = None):
        self.Db = DatabaseServiceInstance or DatabaseService()

    # directive: transcode-flow-canonical
    def SweepStaleOwners(self, AbandonmentMinutes: int = ABANDONMENT_MINUTES_DEFAULT) -> Dict[str, Any]:
        """Mark Success=FALSE + ErrorMessage='owner_abandoned' on every in-flight attempt whose owning Worker is heartbeat-stale + Status != 'Online'. Releases the ta_one_inflight_per_mfid slot so the next claim can proceed."""
        Query = (
            "UPDATE TranscodeAttempts "
            "SET Success = FALSE, ErrorMessage = 'owner_abandoned' "
            "WHERE Success IS NULL "
            "  AND WorkerName IN ( "
            "    SELECT WorkerName FROM Workers "
            "    WHERE Status <> 'Online' "
            "      AND LastHeartbeat < NOW() - (%s * INTERVAL '1 minute') "
            "  )"
        )
        Affected = self.Db.ExecuteNonQuery(Query, (int(AbandonmentMinutes),))
        if Affected:
            LoggingService.LogWarning(
                f"AttemptAbandonmentSweeper released {Affected} in-flight attempt(s) owned by stale/offline workers (threshold={AbandonmentMinutes}min)",
                "AttemptAbandonmentSweeper", "SweepStaleOwners",
            )
        return {"Success": True, "AbandonedCount": int(Affected or 0), "ThresholdMinutes": int(AbandonmentMinutes)}
