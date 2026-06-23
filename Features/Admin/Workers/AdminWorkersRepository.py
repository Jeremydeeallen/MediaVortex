from typing import List, Dict, Any, Optional

from Core.Database.DatabaseService import DatabaseService


# directive: worker-runtime-state | # see admin-workers.C6
class AdminWorkersRepository:

    # directive: worker-runtime-state | # see admin-workers.C6
    def __init__(self, Db: Optional[DatabaseService] = None):
        self._Db = Db or DatabaseService()

    # directive: worker-runtime-state | # see admin-workers.C6
    def GetTiles(self) -> List[Dict[str, Any]]:
        Rows = self._Db.ExecuteQuery(
            "SELECT WorkerName, Platform, Status, LastHeartbeat, MaxConcurrentJobs, "
            "MaxConcurrentTranscodeJobs, MaxConcurrentRemuxJobs, MaxConcurrentQualityTestJobs, "
            "TranscodeEnabled, RemuxEnabled, QualityTestEnabled, ScanEnabled, NvencCapable, "
            "Version, BuildInfo, MountValidationError, Enabled, "
            "RuntimeState, CurrentAttemptId, LastRuntimeStateUpdate, "
            "EXTRACT(EPOCH FROM (NOW() - LastHeartbeat))::int AS HeartbeatAgeSec, "
            "EXTRACT(EPOCH FROM (NOW() - LastRuntimeStateUpdate))::int AS RuntimeStateAgeSec "
            "FROM Workers WHERE Enabled = TRUE "
            "ORDER BY WorkerName ASC"
        )
        Threshold = self.GetDivergenceThresholdSec()
        Tiles = []
        for R in (Rows or []):
            Tile = dict(R)
            Tile['IntentDiverges'] = _DeriveDivergence(
                Tile.get('status'),
                Tile.get('runtimestate'),
                Tile.get('runtimestateagesec'),
                Threshold,
            )
            Tiles.append(Tile)
        return Tiles

    # directive: worker-runtime-state | # see admin-workers.C4
    def GetStaleThresholdSec(self) -> int:
        Rows = self._Db.ExecuteQuery(
            "SELECT SettingValue FROM SystemSettings WHERE SettingKey = 'HeartbeatStaleThresholdSec' LIMIT 1"
        )
        try:
            return int(Rows[0]['settingvalue']) if Rows else 300
        except (KeyError, ValueError, TypeError):
            return 300

    # directive: worker-runtime-state | # see admin-workers.C6
    def GetDivergenceThresholdSec(self) -> int:
        Rows = self._Db.ExecuteQuery(
            "SELECT SettingValue FROM SystemSettings WHERE SettingKey = 'WorkerIntentDivergenceSec' LIMIT 1"
        )
        try:
            return int(Rows[0]['settingvalue']) if Rows else 60
        except (KeyError, ValueError, TypeError):
            return 60


# directive: worker-runtime-state | # see admin-workers.C6
def _DeriveDivergence(Status, RuntimeState, RuntimeStateAgeSec, ThresholdSec):
    """Operator-Status vs worker-RuntimeState. Returns True when disagreement has persisted past threshold."""
    if not Status:
        return False
    Threshold = int(ThresholdSec)
    Age = None if RuntimeStateAgeSec is None else int(RuntimeStateAgeSec)
    if Status == 'Online' and (RuntimeState is None or Age is None or Age > Threshold):
        return True
    if not RuntimeState:
        return False
    WorkerActive = RuntimeState in ('Idle', 'ClaimingJob', 'Encoding', 'Scanning', 'Initializing')
    Compatible = (
        (Status == 'Online' and WorkerActive)
        or (Status == 'Paused' and (RuntimeState in ('Paused', 'Draining')))
    )
    if Compatible:
        return False
    return Age is not None and Age > Threshold
