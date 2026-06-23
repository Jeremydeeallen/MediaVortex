from typing import List, Dict, Any, Optional

from Core.Database.DatabaseService import DatabaseService


# directive: activity-admin-and-worker-telemetry
class AdminWorkersRepository:

    # directive: activity-admin-and-worker-telemetry
    def __init__(self, Db: Optional[DatabaseService] = None):
        self._Db = Db or DatabaseService()

    # directive: activity-admin-and-worker-telemetry
    def GetTiles(self) -> List[Dict[str, Any]]:
        Rows = self._Db.ExecuteQuery(
            "SELECT WorkerName, Platform, Status, LastHeartbeat, MaxConcurrentJobs, "
            "MaxConcurrentTranscodeJobs, MaxConcurrentRemuxJobs, MaxConcurrentQualityTestJobs, "
            "TranscodeEnabled, RemuxEnabled, QualityTestEnabled, ScanEnabled, NvencCapable, "
            "Version, BuildInfo, MountValidationError, Enabled, "
            "EXTRACT(EPOCH FROM (NOW() - LastHeartbeat))::int AS HeartbeatAgeSec "
            "FROM Workers WHERE Enabled = TRUE "
            "ORDER BY WorkerName ASC"
        )
        return [dict(R) for R in (Rows or [])]

    # directive: activity-admin-and-worker-telemetry
    def GetStaleThresholdSec(self) -> int:
        Rows = self._Db.ExecuteQuery(
            "SELECT SettingValue FROM SystemSettings WHERE SettingKey = 'HeartbeatStaleThresholdSec' LIMIT 1"
        )
        try:
            return int(Rows[0]['settingvalue']) if Rows else 300
        except (KeyError, ValueError, TypeError):
            return 300
